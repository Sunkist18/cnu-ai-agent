"""Phase 1 — Teacher trajectory 수집 (PLAN.md §4).

ChatClaudeCode를 Teacher로 끼워넣은 browser-use Agent를 task별 1회 실행해서:
- step별 (DOM/screenshot/AgentOutput/input_messages) → `steps.jsonl`
- 전체 history → `history.json`
- 스크린샷 → `screenshots/step_<n>.png`

저장 구조:
    trajectories/<task_id>/
        history.json
        steps.jsonl
        screenshots/step_<n>.png

핵심 안전장치:
- `MUTATING_ACTION_RE`로 action params 텍스트에 결재 mutating 키워드(승인/반려/상신/제출/저장
  /삭제/회수/재상신) 감지 시 즉시 abort + 사유 기록. trajectory는 partial로 남음 (검수용).
- v0는 read-only subset만 — 카테고리 필터 (`--categories 문서조회,결재처리`) 또는 task id
  리스트 (`--ids-file path`) 로 제한.
- 이미 `<task_id>/history.json`이 있으면 skip — 재실행 시 resume.

Run:
  python -m cnu_agent.teacher.collect \\
    --tasks tasks/korus_100.json \\
    --auth  auth/korus_storage_state.json \\
    --out   trajectories \\
    --categories 문서조회,결재처리 \\
    --max-steps 25
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from browser_use import Agent, Browser
from browser_use.agent.views import AgentOutput
from browser_use.browser.views import BrowserStateSummary

from cnu_agent.teacher.claude_code_llm import ChatClaudeCode

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = REPO_ROOT / "tasks" / "korus_100.json"
DEFAULT_AUTH = REPO_ROOT / "auth" / "korus_storage_state.json"
DEFAULT_OUT = REPO_ROOT / "trajectories"

# 한글 mutating 버튼 라벨 — click 액션의 description/text 필드에서만 검사.
# done.text 보고문이나 search_page.pattern, input.text(placeholder) 등에는 적용 안 함.
KOREAN_MUTATING_BUTTON_RE = re.compile(
	# 저장(?![된되함소]) — "저장"/"임시저장" 매치하되 "저장된/저장함/저장소" 등 descriptive suffix 제외
	r"(승인|반려|상신|제출|저장(?![된되함소])|삭제|회수|재상신|결재완료|발송|전송)"
)
# 액션 이름 자체가 mutating인 케이스
MUTATING_ACTION_NAMES = {
	"submit",
	"submit_form",
	"approve",
	"reject",
	"delete",
	"publish",
	"send_form",
}
# 변경 안 일으키는 read 액션들 — guard 적용 대상에서 제외
READ_ONLY_ACTION_NAMES = {
	"done",
	"extract",
	"extract_structured_data",
	"search_page",
	"send_keys",
	"input",
	"navigate",
	"go_back",
	"scroll",
	"wait",
	"switch",
	"switch_tab",
	"hover",
	"screenshot",
}

# read-only safe categories (Phase 1 v0)
DEFAULT_CATEGORIES_V0 = ["문서조회", "결재처리"]


@dataclass
class CollectResult:
	task_id: str
	status: str  # "ok" | "fail" | "skipped" | "mutating_blocked"
	steps: int = 0
	is_done: bool = False
	mutating_hits: list[dict] = None  # type: ignore[assignment]
	error: str | None = None

	def to_dict(self) -> dict[str, Any]:
		return {
			"task_id": self.task_id,
			"status": self.status,
			"steps": self.steps,
			"is_done": self.is_done,
			"mutating_hits": self.mutating_hits or [],
			"error": self.error,
		}


def _scan_mutating(action_dump: dict[str, Any]) -> list[str]:
	"""Detect mutating action invocations.

	Two narrow checks (avoiding false positives on observation/report text):
	1. Action name itself is in MUTATING_ACTION_NAMES (e.g., `submit`, `approve`).
	2. `click` action's `description`/`text` field contains a Korean mutating button label
	   (e.g., "승인", "삭제"). browser-use exposes these only when the action carrier
	   has been pre-resolved with element label; index-only clicks slip past this guard
	   and are caught by post-run audit of `agent.history` instead.

	Explicitly NOT scanned: `done.text` (report), `search_page.pattern` (query),
	`input.text` (placeholder may contain "submit"), `send_keys.keys` (Escape, etc).
	"""
	hits: list[str] = []
	for action_name, params in action_dump.items():
		# 1. Inherent mutating action name
		if action_name in MUTATING_ACTION_NAMES:
			hits.append(f"{action_name}: action name is mutating; params={json.dumps(params, ensure_ascii=False)[:200]}")
			continue
		# 2. Read-only/observation action — skip
		if action_name in READ_ONLY_ACTION_NAMES:
			continue
		# 3. Click action — check description/text for button labels
		if action_name == "click":
			text_blob = f"{params.get('description') or ''}|{params.get('text') or ''}"
			m = KOREAN_MUTATING_BUTTON_RE.search(text_blob)
			if m:
				hits.append(f"click: button label '{m.group(0)}' in {text_blob[:200]}")
		# 4. Other unknown actions — be conservative, do NOT block (avoid blocking on harmless custom actions)
	return hits


def _slim_input_messages(
	dumps: list[dict[str, Any]], screenshot_rel: str | None
) -> list[dict[str, Any]]:
	"""Replace inline base64 images in user-message content with file:// path refs.

	Why: browser-use sends each step's screenshot as a base64 ContentPartImageParam in the
	user message. Dumping that verbatim bloats steps.jsonl by ~400KB per step. The actual
	PNG is already on disk in `screenshots/step_<n>.png`, so we keep only the structure
	and replace the URL with the local path.
	"""
	slimmed: list[dict[str, Any]] = []
	ref_url = f"file://{screenshot_rel}" if screenshot_rel else "<no-screenshot>"
	for m in dumps:
		content = m.get("content")
		if not isinstance(content, list):
			slimmed.append(m)
			continue
		new_parts = []
		for p in content:
			if isinstance(p, dict) and p.get("type") == "image_url":
				url = (p.get("image_url") or {}).get("url", "")
				if url.startswith("data:"):
					new_parts.append(
						{
							"type": "image_url",
							"image_url": {
								**(p.get("image_url") or {}),
								"url": ref_url,
							},
						}
					)
					continue
			new_parts.append(p)
		slimmed.append({**m, "content": new_parts})
	return slimmed


def _step_callback_factory(task_id: str, out_dir: Path, hits_box: list[dict], agent_ref: dict[str, Any]):
	"""Closure for register_new_step_callback. Writes steps.jsonl + saves screenshot.

	`agent_ref` is a 1-element dict so the closure can read the agent after Agent() construction
	(register_new_step_callback is passed before agent exists). Mutated to {"agent": <Agent>}
	once the agent instance is available.
	"""
	steps_log = out_dir / "steps.jsonl"
	steps_log.unlink(missing_ok=True)
	screenshot_dir = out_dir / "screenshots"
	screenshot_dir.mkdir(parents=True, exist_ok=True)

	def _cb(state: BrowserStateSummary, output: AgentOutput, step_n: int) -> None:
		# 1. screenshot
		screenshot_rel: str | None = None
		if state.screenshot:
			path = screenshot_dir / f"step_{step_n}.png"
			try:
				path.write_bytes(base64.b64decode(state.screenshot))
				screenshot_rel = f"screenshots/step_{step_n}.png"
			except Exception as e:  # noqa: BLE001
				print(f"  [{task_id}] step {step_n} screenshot save failed: {e}", file=sys.stderr)

		# 2. mutating guard — scan every action in this step's output
		try:
			actions = output.action or []
		except Exception:
			actions = []
		for act in actions:
			try:
				dump = act.model_dump(exclude_none=True)
			except Exception:
				dump = {}
			step_hits = _scan_mutating(dump)
			if step_hits:
				hits_box.append({"step": step_n, "hits": step_hits, "action": dump})

		# 3. last_input_messages (private but stable) — slim out inline base64 images
		input_messages_dump: list[dict] = []
		ag = agent_ref.get("agent")
		if ag is not None:
			try:
				mm = ag._message_manager  # noqa: SLF001
				for m in getattr(mm, "last_input_messages", []) or []:
					try:
						input_messages_dump.append(m.model_dump())
					except Exception:
						input_messages_dump.append({"role": getattr(m, "role", "?"), "content": str(m)[:2000]})
			except Exception:
				pass
		input_messages_dump = _slim_input_messages(input_messages_dump, screenshot_rel)

		# 4. model output
		try:
			model_output_dump = output.model_dump(exclude_none=True)
		except Exception:
			model_output_dump = {"_repr": str(output)[:2000]}

		line = {
			"task_id": task_id,
			"step": step_n,
			"url": getattr(state, "url", None),
			"title": getattr(state, "title", None),
			"screenshot_path": screenshot_rel,
			"input_messages": input_messages_dump,
			"model_output": model_output_dump,
		}
		with steps_log.open("a", encoding="utf-8") as f:
			f.write(json.dumps(line, ensure_ascii=False) + "\n")

	return _cb


def _load_tasks(path: Path) -> list[dict]:
	return json.loads(path.read_text(encoding="utf-8"))


def _select_tasks(
	tasks: list[dict],
	categories: list[str] | None,
	ids: set[str] | None,
	limit: int | None,
) -> list[dict]:
	out = tasks
	if categories:
		out = [t for t in out if t["category"] in categories]
	if ids is not None:
		out = [t for t in out if t["id"] in ids]
	if limit is not None:
		out = out[:limit]
	return out


def _build_sensitive_data_stub(task: dict, korus_url: str) -> dict[str, str] | None:
	"""Stub sensitive_data for v0 read-only — most placeholders aren't actually exercised
	(read-only tasks don't fill forms). For tasks that DO reference placeholders in text,
	provide harmless dummies so the agent can substitute them in queries/searches.

	Domain-locked dict so browser-use sensitive_data only fires on KORUS hosts.
	"""
	keys = task.get("sensitive_keys") or []
	if not keys:
		return None
	stubs: dict[str, str] = {}
	# 보수적 dummy 값 — read-only 조회용 placeholder만 채움. mutating 폼은 v0에 없음.
	defaults = {
		"my_emp_id": "200310067",
		"my_name": "(본인)",
		"start_date": "2025-12-01",
		"end_date": "2025-12-15",
		"date": "2025-12-01",
		"month": "12",
		"year": "2025",
		"doc_no": "DUMMY-DOC-001",
		"doc_title": "샘플 문서",
		"submitter_name": "(기안자)",
		"amount": "100000",
		"file_path": "/tmp/dummy.pdf",
		"facility_name": "대강당",
		"destination": "서울",
		"purpose": "업무 협의",
	}
	for k in keys:
		stubs[k] = defaults.get(k, f"<{k}>")
	# domain-locked — KORUS 도메인 스코프로만 가시.
	from urllib.parse import urlparse

	host = urlparse(korus_url).hostname or "korus.ac.kr"
	# wildcard로 sso/cnu 둘 다 — '.korus.ac.kr' 패턴
	parent = ".".join(host.split(".")[-3:]) if host.count(".") >= 2 else host
	return {f"https://*.{parent}": stubs}


async def _collect_one(
	task: dict,
	out_root: Path,
	auth_path: Path,
	max_steps: int,
	korus_url: str,
) -> CollectResult:
	task_id = task["id"]
	out_dir = out_root / task_id

	# resume: skip if already collected
	if (out_dir / "history.json").exists():
		return CollectResult(task_id=task_id, status="skipped")

	out_dir.mkdir(parents=True, exist_ok=True)
	hits_box: list[dict] = []
	agent_ref: dict[str, Any] = {}
	step_cb = _step_callback_factory(task_id, out_dir, hits_box, agent_ref)

	browser = Browser(
		# headless=True에서 KORUS 메뉴 렌더 이상 (smoke test에서 완료문서 못 찾음).
		# discover.py는 headless=False에서 정상 동작 — 같은 모드로 통일.
		headless=False,
		storage_state=str(auth_path),
		user_data_dir=None,
		# KORUS 도메인 잠금 — sensitive_data 안전성 + 외부 사이트 우회 차단
		allowed_domains=["*.korus.ac.kr", "*.cnu.ac.kr"],
	)
	llm = ChatClaudeCode()

	sensitive = _build_sensitive_data_stub(task, korus_url)

	error_msg: str | None = None
	steps = 0
	is_done = False
	try:
		# 시작 URL을 task에 prepend — Agent가 자체 navigate 안 하면 첫 step에서 막힘
		full_task = (
			f"KORUS({korus_url})에서 다음 작업을 수행하세요. **read-only 모드**: "
			f"메뉴 클릭·페이지 이동·조회까지만, 절대 제출/저장/승인/반려/상신 버튼 누르지 않습니다.\n\n"
			f"task: {task['task']}\n\n"
			# F1 — read-only 조회 task의 success 기준 명시 (v0 분석에서 페이지 도달 + 빈 결과 정확히\n"
			# 인식했는데도 self-eval에서 fail로 표시한 케이스가 3건 있었음 — analysis/v0_failure_modes.md §3.3)
			"## Done 평가 규칙\n"
			"- 의도한 페이지에 도달해서 결과를 *확인*했다면 결과 데이터 유무와 무관하게 `done(success=True)`.\n"
			"  예: 급여명세서 페이지 도달 + 검색 + '조회 결과 없음' 확인 → success=True (조회 자체는 성공).\n"
			"- read-only 조회 task의 본질은 조회 동작 완료지, 데이터 존재 여부가 아님.\n"
			"- `done(success=False)`는 다음 케이스에만:\n"
			"  (a) 의도한 페이지/메뉴 자체를 못 찾음\n"
			"  (b) search form 등 입력 UI가 동작 안 함\n"
			"  (c) max_steps 도달했는데 결과 페이지에도 못 들어감"
		)
		agent = Agent(
			task=full_task,
			llm=llm,
			browser=browser,
			register_new_step_callback=step_cb,
			use_vision=True,
			use_judge=False,
			calculate_cost=False,
			max_actions_per_step=2,
			directly_open_url=False,
			sensitive_data=sensitive,
			# Phase 0b discovery에서 검증한 설정 — DOM 누적 + LLM timeout 대응
			llm_timeout=300,
			max_history_items=10,
			max_clickable_elements_length=20000,
		)
		agent_ref["agent"] = agent
		history = await agent.run(max_steps=max_steps)
		steps = len(history.history)
		is_done = history.is_done()
		history.save_to_file(out_dir / "history.json", sensitive_data=sensitive)
	except Exception as e:  # noqa: BLE001
		error_msg = f"{type(e).__name__}: {e}"
		traceback.print_exc()
	finally:
		try:
			await browser.kill()
		except Exception:  # noqa: BLE001
			pass

	if hits_box:
		# Mutating 발견 — partial 보존하되 status는 mutating_blocked로
		(out_dir / "_MUTATING_BLOCKED.json").write_text(
			json.dumps(hits_box, indent=2, ensure_ascii=False), encoding="utf-8"
		)
		return CollectResult(
			task_id=task_id,
			status="mutating_blocked",
			steps=steps,
			is_done=is_done,
			mutating_hits=hits_box,
			error=error_msg,
		)

	if error_msg or steps == 0:
		return CollectResult(
			task_id=task_id, status="fail", steps=steps, is_done=is_done, error=error_msg
		)
	return CollectResult(task_id=task_id, status="ok", steps=steps, is_done=is_done)


async def run_collect(
	tasks_path: Path,
	out_root: Path,
	auth_path: Path,
	max_steps: int,
	categories: list[str] | None,
	ids: set[str] | None,
	limit: int | None,
	korus_url: str,
) -> int:
	if not auth_path.exists():
		print(f"[FAIL] storage_state 없음: {auth_path}", file=sys.stderr)
		return 2

	tasks = _load_tasks(tasks_path)
	selected = _select_tasks(tasks, categories, ids, limit)
	print(f"[INFO] tasks selected: {len(selected)}/{len(tasks)} (categories={categories}, ids={len(ids) if ids else 'all'}, limit={limit})")
	print(f"[INFO] out: {out_root}")
	print(f"[INFO] max_steps: {max_steps}")

	out_root.mkdir(parents=True, exist_ok=True)
	results: list[CollectResult] = []

	for i, task in enumerate(selected):
		print(f"\n[{i + 1}/{len(selected)}] {task['id']} — {task['task'][:80]}", flush=True)
		try:
			result = await _collect_one(task, out_root, auth_path, max_steps, korus_url)
		except Exception as e:  # noqa: BLE001
			print(f"  ❌ unexpected exception: {e}", file=sys.stderr)
			traceback.print_exc()
			result = CollectResult(task_id=task["id"], status="fail", error=str(e))
		results.append(result)

		mark = {
			"ok": "✅",
			"skipped": "⏭️",
			"fail": "❌",
			"mutating_blocked": "🚫",
		}.get(result.status, "?")
		extra = ""
		if result.mutating_hits:
			extra = f" mutating={len(result.mutating_hits)}"
		if result.error:
			extra = f" err={result.error[:80]}"
		print(f"  {mark} {result.status} steps={result.steps} done={result.is_done}{extra}")

	# Summary
	summary_path = out_root / "_collect_summary.json"
	summary_path.write_text(
		json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False),
		encoding="utf-8",
	)
	from collections import Counter

	cnt = Counter(r.status for r in results)
	print(f"\n=== Collection summary ===")
	for st, n in cnt.most_common():
		print(f"  {st:18s}  {n}")
	print(f"  → {summary_path}")
	return 0 if cnt.get("fail", 0) == 0 and cnt.get("mutating_blocked", 0) == 0 else 1


def _load_url_from_env() -> str:
	env_path = REPO_ROOT / ".env"
	if env_path.exists():
		for line in env_path.read_text(encoding="utf-8").splitlines():
			line = line.strip()
			if line.startswith("KORUS_URL="):
				return line.split("=", 1)[1].strip()
	return "https://cnu.korus.ac.kr/"


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="KORUS Teacher trajectory 수집 (Phase 1)")
	parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
	parser.add_argument("--auth", type=Path, default=DEFAULT_AUTH)
	parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
	parser.add_argument("--max-steps", type=int, default=25)
	parser.add_argument(
		"--categories",
		type=str,
		default=",".join(DEFAULT_CATEGORIES_V0),
		help="comma-separated 카테고리 화이트리스트 (예: '문서조회,결재처리'). 'all'이면 필터 없음.",
	)
	parser.add_argument("--ids-file", type=Path, default=None, help="task id 리스트 (.txt, 한 줄당 1 id)")
	parser.add_argument("--limit", type=int, default=None, help="처음 N개만 (smoke test용)")
	parser.add_argument("--url", type=str, default=None)
	args = parser.parse_args(argv)

	categories: list[str] | None = None
	if args.categories and args.categories.lower() != "all":
		categories = [c.strip() for c in args.categories.split(",") if c.strip()]

	ids: set[str] | None = None
	if args.ids_file:
		ids = {
			line.strip()
			for line in args.ids_file.read_text(encoding="utf-8").splitlines()
			if line.strip() and not line.startswith("#")
		}

	url = args.url or _load_url_from_env()

	return asyncio.run(
		run_collect(
			tasks_path=args.tasks,
			out_root=args.out,
			auth_path=args.auth,
			max_steps=args.max_steps,
			categories=categories,
			ids=ids,
			limit=args.limit,
			korus_url=url,
		)
	)


if __name__ == "__main__":
	sys.exit(main())
