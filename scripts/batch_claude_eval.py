"""KORUS 20-task 측정 — ChatClaudeCode (claude -p) + 우리 prompt + browser-use (Mac).

Friday 데모 A.1.3: 프롬프트 엔지니어링 적용한 Claude로 KORUS 성공률 측정.
Mac에서 직접 실행 (학내망 → KORUS). vLLM/proxy 불필요.

결과 CSV: 시스템 / 시스템_연번 / task / 성공 여부 / 응답 / 스텝 수 / 걸린 시간 / 스텝당 평균 시간 / 비고

Run:
  PYTHONPATH=. python scripts/batch_claude_eval.py \\
    --ids-file analysis/korus_eval20_ids.txt \\
    --out eval_claude_korus
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from browser_use import Agent, Browser

from cnu_agent.teacher.claude_code_llm import ChatClaudeCode

REPO_ROOT = Path(__file__).resolve().parent.parent

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


def _fmt(sec: float) -> str:
	return f"{sec:.0f}s" if sec < 60 else f"{sec/60:.1f}m"


def _build_full_task(task_text: str, korus_url: str, seed_id: str | None,
                     username: str, password: str) -> tuple[str, dict]:
	sensitive_data = {
		"https://*.korus.ac.kr": {"korus_username": username, "korus_password": password}
	}
	login_instruction = (
		"\n## 로그인 절차 (URL에 'login'/'lginView' 포함 시)\n"
		"1. 한 step에 2-action: <input id=userId01>에 `<secret>korus_username</secret>`, "
		"<input id=emplyrSecretNo type=password>에 `<secret>korus_password</secret>`\n"
		"2. 다음 step: <a title=로그인> 클릭 (NOT 아이디찾기). 그 후 wait(3).\n"
		"3. URL에서 'lginView' 빠지면 로그인 완료.\n"
	)
	menu_hint = ""
	if seed_id and seed_id in _PATHS_BY_SEED:
		menu_hint = (
			f"\n## 메뉴 힌트 (검증된 경로 — 우선 시도)\n"
			f"- 목적 페이지 경로: **{_PATHS_BY_SEED[seed_id]}**\n"
			"- 비슷한 이름 메뉴에 헤매지 말 것.\n"
		)
	full_task = (
		f"KORUS({korus_url})에서 다음 작업을 수행하세요. **read-only 모드**: "
		f"메뉴 클릭·페이지 이동·조회까지만, 절대 제출/저장/승인/반려/상신 버튼 누르지 않습니다.\n"
		f"{login_instruction}{menu_hint}\n"
		"## KORUS 특징\n"
		"- iframe 구조 (사이드 메뉴 + 본문 분리), 일부 메뉴는 새 탭 열림.\n"
		"- skeleton/로딩 화면: wait(3) 한 번만, 그래도 그대로면 클릭 진행 (wait 무한반복 ❌).\n"
		"- 만족도 조사 팝업: '다음 변경 전까지 보지 않기' 체크 후 X.\n"
		"## 무한 루프 방지\n"
		"- 같은 index 3번+ 클릭 ❌, wait만 4번+ ❌. 5 step 헤매면 done(success=False).\n"
		f"\ntask: {task_text}\n\n"
		"## Done 규칙\n"
		"- 목적 페이지 도달 + 결과 확인 → 즉시 done(success=True). 데이터 0건도 OK.\n"
	)
	return full_task, sensitive_data


async def _run_one(task_id: str, task_text: str, seed_id: str | None, llm: ChatClaudeCode,
                   korus_url: str, username: str, password: str,
                   out_root: Path, max_steps: int, headless: bool = False) -> dict:
	t0 = time.time()
	out_dir = out_root / task_id
	out_dir.mkdir(parents=True, exist_ok=True)

	browser = Browser(headless=headless, user_data_dir=None,
	                  allowed_domains=["*.korus.ac.kr", "*.cnu.ac.kr"])
	full_task, sensitive_data = _build_full_task(task_text, korus_url, seed_id, username, password)

	err = None; success = False; steps = 0; final_text = ""
	try:
		agent = Agent(
			task=full_task, llm=llm, browser=browser,
			use_vision=True, use_judge=False, calculate_cost=False,
			max_actions_per_step=2, directly_open_url=False,
			sensitive_data=sensitive_data, llm_timeout=300, step_timeout=300,
			max_history_items=10, max_clickable_elements_length=20000,
		)
		history = await agent.run(max_steps=max_steps)
		steps = len(history.history)
		if steps:
			last = history.history[-1]
			mo = getattr(last, "model_output", None) or {}
			if hasattr(mo, "model_dump"): mo = mo.model_dump()
			for act in (mo.get("action") if isinstance(mo, dict) else []) or []:
				if isinstance(act, dict) and "done" in act:
					success = bool(act["done"].get("success"))
					final_text = (act["done"].get("text") or "")[:200]
					break
		try: history.save_to_file(out_dir / "history.json")
		except Exception: pass
	except Exception as e:  # noqa: BLE001
		err = f"{type(e).__name__}: {e}"
	finally:
		try: await browser.kill()
		except Exception: pass

	dur = time.time() - t0
	return {
		"task_id": task_id, "task": task_text, "success": success,
		"steps": steps, "duration_sec": round(dur, 1),
		"avg_step_sec": round(dur / steps, 1) if steps else 0,
		"final_text": final_text, "error": err,
		"ts": datetime.now().isoformat(timespec="seconds"),
	}


async def main_async(args):
	env = _load_env()
	url = env.get("KORUS_URL", "https://cnu.korus.ac.kr/")
	username = env.get("KORUS_USERNAME"); password = env.get("KORUS_PASSWORD")
	if not (username and password):
		print("[FAIL] .env KORUS_USERNAME/PASSWORD 필요", file=sys.stderr); return 2

	all_tasks = {t["id"]: t for t in json.loads((REPO_ROOT / "tasks" / "korus_100.json").read_text(encoding="utf-8"))}
	ids = [l.strip() for l in Path(args.ids_file).read_text(encoding="utf-8").splitlines() if l.strip()]
	selected = [(tid, all_tasks[tid]) for tid in ids if tid in all_tasks]
	print(f"[INFO] {len(selected)} tasks (claude -p 측정)")

	args.out.mkdir(parents=True, exist_ok=True)
	results_path = args.out / "results.jsonl"
	done_ids = set()
	if args.resume and results_path.exists():
		for l in results_path.read_text(encoding="utf-8").splitlines():
			if l.strip():
				try: done_ids.add(json.loads(l)["task_id"])
				except Exception: pass
	pending = [(tid, t) for tid, t in selected if tid not in done_ids]
	print(f"[INFO] to run: {len(pending)} (resume skip {len(done_ids)})")

	llm = ChatClaudeCode()
	t0 = time.time(); done = 0; succ = 0
	stop = False
	def _sig(s, f):
		nonlocal stop; stop = True
		print("\n[WARN] Ctrl+C — 현재 task 끝내고 종료", file=sys.stderr)
	signal.signal(signal.SIGINT, _sig)

	for i, (tid, t) in enumerate(pending, 1):
		if stop: break
		print(f"\n===== [{i}/{len(pending)}] {tid} =====\n  task: {t['task']}")
		rec = await _run_one(tid, t["task"], t.get("seed_id"), llm, url, username, password,
		                     args.out, args.max_steps, headless=args.headless)
		with results_path.open("a", encoding="utf-8") as f:
			f.write(json.dumps(rec, ensure_ascii=False) + "\n")
		done += 1
		if rec["success"]: succ += 1
		el = time.time() - t0; avg = el / done
		print(f"  → success={rec['success']} steps={rec['steps']} dur={_fmt(rec['duration_sec'])} "
		      f"avg_step={rec['avg_step_sec']}s")
		print(f"  [PROGRESS] {done}/{len(pending)} succ={succ} ({succ/done*100:.0f}%) "
		      f"ETA={_fmt((len(pending)-done)*avg)}")

	# CSV 출력 (Task.xlsx 취합용)
	recs = [json.loads(l) for l in results_path.read_text(encoding="utf-8").splitlines() if l.strip()]
	csv_path = args.out / "korus_results.csv"
	cols = ["시스템", "시스템_연번", "task", "성공 여부", "응답", "스텝 수", "걸린 시간", "스텝당 평균 시간", "비고"]
	with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
		w = csv.writer(f); w.writerow(cols)
		for n, r in enumerate(recs, 1):
			w.writerow(["KORUS", n, r["task"], "성공" if r["success"] else "실패",
			            r["final_text"], r["steps"], f"{r['duration_sec']}s",
			            f"{r['avg_step_sec']}s", all_tasks.get(r["task_id"], {}).get("category", "")])
	print(f"\n{'='*50}\nDONE. {succ}/{done} ({succ/max(done,1)*100:.0f}%)  wall={_fmt(time.time()-t0)}")
	print(f"CSV: {csv_path}")
	return 0


def main(argv=None):
	p = argparse.ArgumentParser()
	p.add_argument("--ids-file", type=Path, required=True)
	p.add_argument("--out", type=Path, default=REPO_ROOT / "eval_claude_korus")
	p.add_argument("--max-steps", type=int, default=25)
	p.add_argument("--resume", action="store_true")
	p.add_argument("--headless", action="store_true", help="Mac 화면 잠김 시 필요")
	return asyncio.run(main_async(p.parse_args(argv)))


if __name__ == "__main__":
	sys.exit(main())
