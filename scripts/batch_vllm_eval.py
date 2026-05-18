"""실 KORUS task batch — vLLM serve (학교 서버) + browser-use Agent (Mac).

차이점 (vs batch_mlx_eval):
- LLM은 ChatOpenAI(base_url=vllm_endpoint) — fast inference, MLX 양자화 없음
- 학습 분포 매칭: use_vision=True, max_clickable_elements_length=20000, max_history_items=10
- model="korus-v2" — vLLM이 LoRA 적용한 모델명
- step_timeout 기본 (180s) 유지 — 서버 추론 충분히 빠름

Run:
  PYTHONPATH=. python scripts/batch_vllm_eval.py \\
    --endpoint http://192.168.1.121:8000/v1 \\
    --limit 20 \\
    --out eval_vllm_v2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from browser_use import Agent, Browser
from browser_use.llm import ChatOpenAI

REPO_ROOT = Path(__file__).resolve().parent.parent

# v2_paths.json — discovery 단계에서 검증된 메뉴 경로 (seed별 정답)
_PATHS_PATH = REPO_ROOT / "discovery" / "v2_paths.json"
_PATHS_BY_SEED: dict[str, str] = {}
if _PATHS_PATH.exists():
	for p in json.loads(_PATHS_PATH.read_text(encoding="utf-8")):
		mp = (p.get("menu_path") or "").strip()
		if mp:
			_PATHS_BY_SEED[p["seed_id"]] = mp


def _load_env() -> dict[str, str]:
	env = REPO_ROOT / ".env"
	out = {}
	if env.exists():
		for line in env.read_text(encoding="utf-8").splitlines():
			line = line.strip()
			if not line or line.startswith("#") or "=" not in line:
				continue
			k, v = line.split("=", 1)
			out[k.strip()] = v.strip()
	return out


def _format_dur(sec: float) -> str:
	if sec < 60:
		return f"{sec:.0f}s"
	if sec < 3600:
		return f"{sec/60:.1f}m"
	return f"{sec/3600:.2f}h"


def _load_done(results_path: Path) -> set[str]:
	done = set()
	if not results_path.exists():
		return done
	for line in results_path.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if not line:
			continue
		try:
			rec = json.loads(line)
			done.add(rec["task_id"])
		except Exception:
			pass
	return done


async def _run_one(
	task_id: str,
	task_text: str,
	llm: ChatOpenAI,
	korus_url: str,
	username: str,
	password: str,
	out_root: Path,
	max_steps: int,
	auth_path: Path | None,
	seed_id: str | None = None,
) -> dict:
	t0 = time.time()
	out_dir = out_root / task_id
	out_dir.mkdir(parents=True, exist_ok=True)

	use_storage_state = auth_path is not None and auth_path.exists()

	browser_kwargs = dict(
		headless=False,
		user_data_dir=None,
		allowed_domains=["*.korus.ac.kr", "*.cnu.ac.kr"],
	)
	if use_storage_state:
		browser_kwargs["storage_state"] = str(auth_path)

	browser = Browser(**browser_kwargs)

	sensitive_data = None
	login_instruction = ""
	if not use_storage_state:
		sensitive_data = {
			"https://*.korus.ac.kr": {
				"korus_username": username,
				"korus_password": password,
			}
		}
		# v3: 더 imperative + popup 대응 + 무한 retry 금지
		login_instruction = (
			"\n## 로그인 (반드시 순서대로 — 위반 시 task 실패)\n"
			"1. URL에 'login' 또는 'lginView' 포함 시: 한 step에 **2개 input action**을 동시 emit:\n"
			"   - 사용자명 필드(placeholder='아이디' 또는 id 'userId'/'username') → `<secret>korus_username</secret>`\n"
			"   - 비밀번호 필드(placeholder='비밀번호' 또는 id 'password'/'pwd') → `<secret>korus_password</secret>`\n"
			"2. 다음 step에서 로그인 버튼(텍스트 '로그인', NOT '아이디 찾기')만 1번 클릭. 그 후 wait(seconds=3).\n"
			"3. popup/dialog 뜨면 X 또는 닫기 클릭. 동일 동작 무한 반복 금지 — 같은 index 3번 이상 클릭했으면 다른 방식 시도.\n"
			"4. URL이 'login'/'lginView' 빠지고 메뉴가 보이면 로그인 성공 — 다음 단계로.\n"
		)

	# v3: seed별 메뉴 경로 힌트 주입
	menu_hint = ""
	if seed_id and seed_id in _PATHS_BY_SEED:
		menu_hint = (
			f"\n## 메뉴 힌트 (검증된 경로 — 우선 시도)\n"
			f"- 목적 페이지 경로: **{_PATHS_BY_SEED[seed_id]}**\n"
			"- 한국어 메뉴를 한 단계씩 정확히 따라가세요. 다른 비슷한 이름 메뉴에 헤매지 말 것.\n"
		)

	full_task = (
		f"KORUS({korus_url})에서 다음 작업을 수행하세요. **read-only 모드**: "
		f"메뉴 클릭·페이지 이동·조회까지만, 절대 제출/저장/승인/반려/상신 버튼 누르지 않습니다.\n"
		f"{login_instruction}"
		f"{menu_hint}\n"
		f"task: {task_text}\n\n"
		"## Done 호출 규칙 (중요)\n"
		"- 목적 페이지(또는 form)에 도달하면 즉시 done(success=True). 추가 탐색 욕심 ❌.\n"
		"- 데이터 0건이라도 도달했으면 success=True. 'no items'은 정상 응답.\n"
		"- 같은 메뉴를 4번 이상 못 찾았으면 done(success=False)로 깔끔히 종료. 무한 반복 ❌.\n"
		"- read-only 본질은 '조회 동작 완료'지 데이터 유무 아님."
	)

	err = None
	success = False
	is_done = False
	steps = 0
	final_text = ""

	try:
		agent = Agent(
			task=full_task,
			llm=llm,
			browser=browser,
			# === 학습 분포(collect.py)와 동일 ===
			use_vision=True,
			use_judge=False,
			calculate_cost=False,
			max_actions_per_step=2,
			directly_open_url=False,
			sensitive_data=sensitive_data,
			llm_timeout=180,
			step_timeout=300,
			max_history_items=10,
			max_clickable_elements_length=20000,
		)
		history = await agent.run(max_steps=max_steps)

		steps = len(history.history)
		is_done = history.is_done()
		if steps:
			last = history.history[-1]
			mo = getattr(last, "model_output", None) or {}
			if hasattr(mo, "model_dump"):
				mo = mo.model_dump()
			for act in (mo.get("action") if isinstance(mo, dict) else []) or []:
				if isinstance(act, dict) and "done" in act:
					success = bool(act["done"].get("success"))
					final_text = (act["done"].get("text") or "")[:300]
					break

		try:
			history.save_to_file(out_dir / "history.json")
		except Exception:
			pass
	except Exception as e:  # noqa: BLE001
		err = f"{type(e).__name__}: {e}"
	finally:
		try:
			await browser.kill()
		except Exception:
			pass

	dur = time.time() - t0
	return {
		"task_id": task_id,
		"task": task_text,
		"steps": steps,
		"is_done": is_done,
		"success": success,
		"error": err,
		"duration_sec": round(dur, 1),
		"final_text": final_text,
		"ts": datetime.now().isoformat(timespec="seconds"),
	}


async def main_async(args):
	env = _load_env()
	url = env.get("KORUS_URL", "https://cnu.korus.ac.kr/")
	username = env.get("KORUS_USERNAME")
	password = env.get("KORUS_PASSWORD")
	if not (username and password):
		print("[FAIL] .env에 KORUS_USERNAME/PASSWORD 필요", file=sys.stderr)
		return 2

	auth_path: Path | None = None
	if args.use_storage_state:
		auth_path = REPO_ROOT / "auth" / "korus_storage_state.json"
		if not auth_path.exists():
			print(f"[WARN] storage_state 파일 없음 ({auth_path}) — fresh-login으로 진행", file=sys.stderr)
			auth_path = None

	# vLLM endpoint smoke
	import httpx
	try:
		with httpx.Client(timeout=5) as cli:
			r = cli.get(f"{args.endpoint}/models")
			r.raise_for_status()
			models = [m["id"] for m in r.json().get("data", [])]
			print(f"[INFO] vLLM endpoint OK — models: {models}")
			if args.model not in models:
				print(f"[FAIL] model '{args.model}' not in {models}", file=sys.stderr)
				return 3
	except Exception as e:  # noqa: BLE001
		print(f"[FAIL] vLLM endpoint unreachable: {e}", file=sys.stderr)
		return 3

	tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
	if args.task:
		tasks = [{"id": "adhoc", "task": args.task, "seed_id": "adhoc"}]
	if args.start:
		tasks = tasks[args.start :]
	if args.limit:
		tasks = tasks[: args.limit]

	args.out.mkdir(parents=True, exist_ok=True)
	results_path = args.out / "results.jsonl"
	done_ids = _load_done(results_path) if args.resume else set()

	pending = [t for t in tasks if t["id"] not in done_ids]
	print(f"[INFO] Total: {len(tasks)}  Done(resume skip): {len(done_ids)}  To run: {len(pending)}")
	if not pending:
		print("[INFO] 할 게 없음 — exit")
		return 0

	llm = ChatOpenAI(
		model=args.model,
		base_url=args.endpoint,
		api_key="not-needed",  # vLLM doesn't check
		temperature=0.0,
		max_completion_tokens=2048,  # JSON output 충분히, 입력은 DOM 3K로 압축됨
	)

	overall_t0 = time.time()
	done = 0
	succ = 0
	stop_requested = False

	def _on_sigint(signum, frame):
		nonlocal stop_requested
		stop_requested = True
		print("\n[WARN] Ctrl+C — 현재 task 끝낸 뒤 exit.", file=sys.stderr)

	signal.signal(signal.SIGINT, _on_sigint)

	for i, t in enumerate(pending, 1):
		if stop_requested:
			break
		tid = t["id"]
		task_text = t["task"]
		print(f"\n========== [{i}/{len(pending)}] {tid} ==========")
		print(f"  task: {task_text}")
		try:
			rec = await _run_one(
				task_id=tid,
				task_text=task_text,
				llm=llm,
				korus_url=url,
				username=username,
				password=password,
				out_root=args.out,
				max_steps=args.max_steps,
				auth_path=auth_path,
				seed_id=t.get("seed_id"),
			)
		except Exception as e:  # noqa: BLE001
			rec = {
				"task_id": tid,
				"task": task_text,
				"steps": 0,
				"is_done": False,
				"success": False,
				"error": f"{type(e).__name__}: {e}",
				"duration_sec": 0,
				"final_text": "",
				"ts": datetime.now().isoformat(timespec="seconds"),
			}

		with results_path.open("a", encoding="utf-8") as f:
			f.write(json.dumps(rec, ensure_ascii=False) + "\n")

		done += 1
		if rec["success"]:
			succ += 1

		elapsed = time.time() - overall_t0
		avg = elapsed / done
		remaining = (len(pending) - done) * avg
		print(
			f"  → success={rec['success']} steps={rec['steps']} "
			f"dur={_format_dur(rec['duration_sec'])} err={rec['error'] or '-'}"
		)
		print(
			f"  [PROGRESS] {done}/{len(pending)} done  "
			f"succ={succ} ({succ/done*100:.1f}%)  "
			f"elapsed={_format_dur(elapsed)}  avg={_format_dur(avg)}  "
			f"ETA={_format_dur(remaining)}"
		)

	overall_elapsed = time.time() - overall_t0
	print(f"\n=========================")
	print(f"DONE. Total: {done}, Success: {succ} ({succ/max(done,1)*100:.1f}%)")
	print(f"Wall: {_format_dur(overall_elapsed)}")
	print(f"results: {results_path}")
	return 0


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--endpoint", required=True, help="vLLM OpenAI-compatible URL (예: http://192.168.1.121:8000/v1)")
	parser.add_argument("--model", default="korus-v2", help="vLLM model name (LoRA module name)")
	parser.add_argument("--tasks", type=Path, default=REPO_ROOT / "tasks" / "korus_100.json")
	parser.add_argument("--out", type=Path, default=REPO_ROOT / "eval_vllm_v2")
	parser.add_argument("--task", type=str, default=None, help="단일 task — tasks 파일 무시")
	parser.add_argument("--max-steps", type=int, default=15)
	parser.add_argument("--limit", type=int, default=None, help="첫 N개만")
	parser.add_argument("--start", type=int, default=0)
	parser.add_argument("--resume", action="store_true")
	parser.add_argument("--use-storage-state", action="store_true",
	                    help="auth/korus_storage_state.json 사용 (학습 분포 매칭). 없으면 fresh-login fallback")
	args = parser.parse_args(argv)
	return asyncio.run(main_async(args))


if __name__ == "__main__":
	sys.exit(main())
