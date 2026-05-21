"""통합 테스트 프레임워크 — 여러 시스템 task 합친 표를 Claude(-p)로 일괄 측정.

흐름:
1. 입력: 통합 task 표 (xlsx 또는 csv). 열: 시스템 / (시스템_연번) / task ...
2. 시스템별 config (systems_config.json): url / 프롬프트 / 로그인 / 도메인
3. 각 row: 해당 시스템 프롬프트 + task → ChatClaudeCode + browser-use (headless) 실행
4. 출력: 같은 표 + 채워진 [성공 여부 / 응답 / 스텝 수 / 걸린 시간 / 스텝당 평균 시간]

Run:
  PYTHONPATH=. python scripts/integration_test.py \\
    --input tasks_combined.xlsx \\
    --config scripts/systems_config.json \\
    --out integration_results \\
    --model sonnet --headless

  # 특정 시스템만:
  ... --only KORUS,도서관
  # 이어하기 (이미 채운 행 skip):
  ... --resume
"""

from __future__ import annotations

# browser_use import 시 get_monitors()가 X display/잠긴 화면 때문에 hang나는 것 방지.
# headless로만 쓰므로 항상 fake monitor 주입 (DISPLAY 유무 무관 — 잠긴 Mac 화면도 hang함).
try:
	import screeninfo as _si
	class _FM:
		x = 0; y = 0; width = 1920; height = 1080; width_mm = 0; height_mm = 0; name = "fake"
	_si.get_monitors = lambda *a, **k: [_FM()]
except Exception:
	pass

import argparse
import asyncio
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from browser_use import Agent, Browser
from browser_use.agent.views import ActionResult
from browser_use.tools.service import Tools
from cnu_agent.teacher.claude_code_llm import ChatClaudeCode

REPO_ROOT = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────
# 커스텀 액션: extract_tables (통합정보시스템 등 표 데이터 추출)
# DOM 기반 (table + iframe table + ARIA grid). CDP Runtime.evaluate 사용.
# ──────────────────────────────────────────────
_EXTRACT_JS = r"""
(() => {
  function fromDoc(doc, prefix) {
    const out = [];
    doc.querySelectorAll('table').forEach((tbl, ti) => {
      const headers = [], rows = [];
      const hdrRow = tbl.querySelector('thead tr, tr:first-child');
      if (hdrRow) hdrRow.querySelectorAll('th,td').forEach(c => { const t=(c.innerText||'').trim(); if(t) headers.push(t); });
      tbl.querySelectorAll('tbody tr, tr:not(:first-child)').forEach(tr => {
        const row=[]; tr.querySelectorAll('td,th').forEach(c => row.push((c.innerText||'').trim()));
        if (row.some(v=>v)) rows.push(row);
      });
      if (rows.length) out.push({title: prefix+'표'+(ti+1), headers, rows});
    });
    // ARIA grid (eXbuilder6 등)
    doc.querySelectorAll('[role="grid"],[role="treegrid"]').forEach((g, gi) => {
      const headers=[]; g.querySelectorAll('[role="columnheader"]').forEach(c=>{const t=(c.innerText||'').trim(); if(t) headers.push(t);});
      const rows=[];
      g.querySelectorAll('[role="row"]').forEach(r=>{
        if (r.querySelector('[role="columnheader"]')) return;
        const cells=[...r.querySelectorAll('[role="gridcell"]')].map(c=>(c.innerText||'').trim());
        if (cells.length && cells.some(v=>v)) rows.push(cells);
      });
      if (rows.length) out.push({title: prefix+'그리드'+(gi+1), headers, rows});
    });
    return out;
  }
  let all = fromDoc(document, '');
  document.querySelectorAll('iframe').forEach((f, fi) => {
    try { const d=f.contentDocument||f.contentWindow?.document; if(d&&d.body) fromDoc(d,'iframe'+(fi+1)+'_').forEach(t=>all.push(t)); } catch(e){}
  });
  return JSON.stringify(all);
})()
"""


def _build_tools() -> Tools:
	tools = Tools()

	@tools.action(
		"페이지의 모든 표(table/grid)를 추출해 구조화 JSON으로 반환. "
		"성적·수강목록·교육과정·시간표 등 표 데이터가 필요할 때 사용. "
		"반환값을 바로 사용하고 write_file/read_file 쓰지 말 것."
	)
	async def extract_tables(browser_session) -> ActionResult:  # noqa: ANN001
		try:
			cdp = await browser_session.get_or_create_cdp_session()
			res = await cdp.cdp_client.send.Runtime.evaluate(
				params={"expression": _EXTRACT_JS, "returnByValue": True},
				session_id=cdp.session_id,
			)
			raw = (res or {}).get("result", {}).get("value")
			tables = json.loads(raw) if isinstance(raw, str) else (raw or [])
		except Exception as e:  # noqa: BLE001
			return ActionResult(
				error=f"extract_tables 실패: {type(e).__name__}: {e}. 화면에서 직접 표를 읽으세요.",
				long_term_memory="extract_tables 실패 — 수동 추출로 전환",
			)
		if not tables:
			return ActionResult(
				extracted_content="표를 찾지 못함. 조회 버튼을 눌러 데이터를 먼저 로드하거나 화면에서 직접 확인.",
				long_term_memory="extract_tables: 표 0개",
			)
		summary = f"{len(tables)}개 표 추출: " + ", ".join(f"{t['title']}({len(t['rows'])}행)" for t in tables)
		blob = json.dumps({"summary": summary, "tables": tables}, ensure_ascii=False)
		return ActionResult(
			extracted_content=blob[:6000],
			long_term_memory=summary,
			include_extracted_content_only_once=True,
		)

	_ = extract_tables
	return tools

# 결과 열 (표준)
METRIC_COLS = ["성공 여부", "응답", "스텝 수", "걸린 시간", "스텝당 평균 시간"]


# ──────────────────────────────────────────────
# 표 I/O (xlsx 우선, 없으면 csv)
# ──────────────────────────────────────────────
def _read_table(path: Path) -> tuple[list[str], list[dict]]:
	"""(header, rows[dict]) 반환."""
	if path.suffix.lower() in (".xlsx", ".xlsm"):
		import openpyxl
		wb = openpyxl.load_workbook(path, data_only=True)
		ws = wb.active
		rows_iter = ws.iter_rows(values_only=True)
		header = [str(c).strip() if c is not None else "" for c in next(rows_iter)]
		rows = []
		for r in rows_iter:
			if all(c is None for c in r):
				continue
			rows.append({header[i]: ("" if v is None else str(v)) for i, v in enumerate(r) if i < len(header)})
		return header, rows
	else:  # csv
		with path.open(encoding="utf-8-sig") as f:
			reader = csv.DictReader(f)
			rows = [dict(r) for r in reader]
			header = reader.fieldnames or []
		return list(header), rows


def _write_table(path: Path, header: list[str], rows: list[dict]) -> None:
	# 항상 csv로 출력 (xlsx는 별도 변환 가능). header에 METRIC_COLS 보장.
	for c in METRIC_COLS:
		if c not in header:
			header.append(c)
	with path.open("w", newline="", encoding="utf-8-sig") as f:
		w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
		w.writeheader()
		for r in rows:
			w.writerow(r)


# ──────────────────────────────────────────────
# 시스템 config
# ──────────────────────────────────────────────
def _load_env() -> dict[str, str]:
	env = REPO_ROOT / ".env"
	out = {}
	if env.exists():
		for line in env.read_text(encoding="utf-8").splitlines():
			line = line.strip()
			if line and not line.startswith("#") and "=" in line:
				k, v = line.split("=", 1)
				out[k.strip()] = v.strip()
	return out


def _build_full_task(system_cfg: dict, task_text: str, env: dict) -> tuple[str, dict | None]:
	"""시스템 프롬프트 + 로그인 + task → full_task, sensitive_data."""
	url = system_cfg["url"]
	# 시스템 프롬프트 (파일 또는 inline)
	prompt = ""
	if system_cfg.get("prompt_file"):
		pf = REPO_ROOT / system_cfg["prompt_file"]
		if pf.exists():
			prompt = pf.read_text(encoding="utf-8")
	elif system_cfg.get("prompt"):
		prompt = system_cfg["prompt"]

	# 로그인 sensitive_data
	sensitive = None
	login = system_cfg.get("login")
	if login:
		u = env.get(login["username_env"], "")
		p = env.get(login["password_env"], "")
		if u and p:
			dom = login.get("secret_domain", "https://*.cnu.ac.kr")
			sensitive = {dom: {login["username_key"]: u, login["password_key"]: p}}

	login_instruction = system_cfg.get("login_instruction", "")

	full_task = (
		f"{prompt}\n"
		f"{login_instruction}\n"
		f"대상 시스템: {system_cfg.get('name','')} (시작 URL: {url})\n"
		f"task: {task_text}\n"
	)
	return full_task, sensitive


# ──────────────────────────────────────────────
# 단일 task 실행
# ──────────────────────────────────────────────
async def _run_one(system_cfg: dict, task_text: str, llm: ChatClaudeCode,
                   env: dict, max_steps: int, headless: bool, out_dir: Path) -> dict:
	t0 = time.time()
	full_task, sensitive = _build_full_task(system_cfg, task_text, env)
	browser = Browser(
		headless=headless, user_data_dir=None,
		allowed_domains=system_cfg.get("allowed_domains", ["*.cnu.ac.kr"]),
	)
	success = False; steps = 0; final_text = ""; err = None
	try:
		agent = Agent(
			task=full_task, llm=llm, browser=browser,
			tools=_build_tools(),  # extract_tables 커스텀 액션
			use_vision=True, use_judge=False, calculate_cost=False,
			max_actions_per_step=2, directly_open_url=False,
			sensitive_data=sensitive, llm_timeout=300, step_timeout=300,
			max_history_items=10, max_clickable_elements_length=20000,
		)
		history = await agent.run(max_steps=max_steps)
		steps = len(history.history)
		if steps:
			mo = getattr(history.history[-1], "model_output", None) or {}
			if hasattr(mo, "model_dump"): mo = mo.model_dump()
			for act in (mo.get("action") if isinstance(mo, dict) else []) or []:
				if isinstance(act, dict) and "done" in act:
					success = bool(act["done"].get("success"))
					final_text = (act["done"].get("text") or "")[:800]
					break
		try:
			if out_dir:
				history.save_to_file(out_dir / "history.json")
		except Exception:
			pass
	except Exception as e:  # noqa: BLE001
		err = f"{type(e).__name__}: {e}"
	finally:
		try: await browser.kill()
		except Exception: pass
	dur = time.time() - t0
	return {
		"success": success, "steps": steps, "final_text": final_text,
		"duration_sec": round(dur, 1),
		"avg_step_sec": round(dur / steps, 1) if steps else 0,
		"error": err,
	}


# ──────────────────────────────────────────────
# main
# ──────────────────────────────────────────────
async def main_async(args):
	env = _load_env()
	config = json.loads(Path(args.config).read_text(encoding="utf-8"))
	header, rows = _read_table(args.input)

	# 시스템 열 이름 추정
	sys_col = next((c for c in header if c.strip() in ("시스템", "system", "System")), None)
	task_col = next((c for c in header if c.strip() in ("task", "Task", "태스크")), None)
	if not sys_col or not task_col:
		print(f"[FAIL] '시스템'/'task' 열 못 찾음. header={header}", file=sys.stderr)
		return 2

	only = set(s.strip() for s in args.only.split(",")) if args.only else None
	args.out.mkdir(parents=True, exist_ok=True)
	out_csv = args.out / "results.csv"

	llm = ChatClaudeCode(model=args.model)
	print(f"[INFO] model={args.model}  rows={len(rows)}  systems={sorted(set(r.get(sys_col,'') for r in rows))}")

	t0 = time.time(); done = 0; succ = 0
	for i, row in enumerate(rows, 1):
		sysname = (row.get(sys_col) or "").strip()
		task_text = (row.get(task_col) or "").strip()
		if not sysname or not task_text:
			continue
		if only and sysname not in only:
			continue
		# resume: 이미 성공여부 채워진 행 skip
		if args.resume and (row.get("성공 여부") or "").strip():
			continue
		if sysname not in config:
			print(f"  [{i}] ⚠️ '{sysname}' config 없음 — skip")
			row["성공 여부"] = "config없음"
			continue

		sys_cfg = config[sysname]; sys_cfg.setdefault("name", sysname)
		print(f"\n===== [{i}/{len(rows)}] {sysname} — {task_text[:50]} =====")
		out_dir = args.out / f"{sysname}_{i}"
		out_dir.mkdir(parents=True, exist_ok=True)
		rec = await _run_one(sys_cfg, task_text, llm, env, args.max_steps, args.headless, out_dir)

		row["성공 여부"] = "성공" if rec["success"] else "실패"
		row["응답"] = rec["final_text"]
		row["스텝 수"] = rec["steps"]
		row["걸린 시간"] = f"{rec['duration_sec']}s"
		row["스텝당 평균 시간"] = f"{rec['avg_step_sec']}s"
		done += 1
		if rec["success"]: succ += 1
		# 매 row 후 중간 저장 (crash 대비)
		_write_table(out_csv, header, rows)
		el = time.time() - t0; avg = el / done
		print(f"  → {row['성공 여부']} steps={rec['steps']} dur={rec['duration_sec']}s")
		print(f"  [PROGRESS] {done} done, {succ} 성공 ({succ/done*100:.0f}%), ETA={(len(rows)-i)*avg/60:.0f}m")

	_write_table(out_csv, header, rows)
	print(f"\n{'='*50}\nDONE. {succ}/{done} 성공 ({succ/max(done,1)*100:.0f}%)")
	print(f"결과: {out_csv}")
	return 0


def main(argv=None):
	p = argparse.ArgumentParser(description="통합 테스트 — 다중 시스템 task를 Claude로 측정")
	p.add_argument("--input", type=Path, required=True, help="통합 task 표 (.xlsx 또는 .csv)")
	p.add_argument("--config", type=Path, default=REPO_ROOT / "scripts" / "systems_config.json")
	p.add_argument("--out", type=Path, default=REPO_ROOT / "integration_results")
	p.add_argument("--model", default="sonnet")
	p.add_argument("--max-steps", type=int, default=25)
	p.add_argument("--headless", action="store_true")
	p.add_argument("--only", default=None, help="특정 시스템만 (쉼표구분, 예: KORUS,도서관)")
	p.add_argument("--resume", action="store_true", help="성공여부 채워진 행 skip")
	return asyncio.run(main_async(p.parse_args(argv)))


if __name__ == "__main__":
	sys.exit(main())
