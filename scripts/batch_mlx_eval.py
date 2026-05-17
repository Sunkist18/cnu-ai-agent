"""실 KORUS task batch — Mac MLX + 우리 LoRA, N개 sequentially.

핵심:
- ChatMLX 한 번만 load (모델 ~30s, 한 번이면 됨)
- 매 task fresh Browser + fresh-login (isolation, session leak 방지)
- Per-task result append → JSONL
- Running success rate + ETA 콘솔 출력
- Ctrl+C 시 안전 종료 (기록은 보존)
- --resume: 이미 끝낸 task 건너뜀
- --limit N: 첫 N개만

Run:
  PYTHONPATH=. python scripts/batch_mlx_eval.py \\
    --tasks tasks/korus_100.json \\
    --out   eval_mlx_v2 \\
    --limit 20 \\
    --max-steps 15
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

from cnu_agent.student.chat_mlx import ChatMLX

REPO_ROOT = Path(__file__).resolve().parent.parent


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
	"""기존 결과에서 완료된 task_id 추출 (resume용)."""
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
	llm: ChatMLX,
	korus_url: str,
	username: str,
	password: str,
	out_root: Path,
	max_steps: int,
	use_vision: bool,
) -> dict:
	"""Single task 실행 → 결과 dict."""
	t0 = time.time()
	out_dir = out_root / task_id
	out_dir.mkdir(parents=True, exist_ok=True)

	browser = Browser(
		headless=False,
		user_data_dir=None,
		allowed_domains=["*.korus.ac.kr", "*.cnu.ac.kr"],
	)

	sensitive_data = {
		"https://*.korus.ac.kr": {
			"korus_username": username,
			"korus_password": password,
		}
	}

	login_instruction = (
		"\n## 로그인 절차 (첫 단계)\n"
		f"1. {korus_url} 진입 → sso.korus.ac.kr로 redirect.\n"
		"2. 사용자명 필드에 `<secret>korus_username</secret>` 입력.\n"
		"3. 비밀번호 필드에 `<secret>korus_password</secret>` 입력.\n"
		"4. 로그인 버튼 클릭 → 대시보드 도달 후 task 진행.\n"
	)

	full_task = (
		f"KORUS({korus_url})에서 다음 작업을 수행하세요. **read-only 모드**: "
		f"메뉴 클릭·페이지 이동·조회까지만, 절대 제출/저장/승인/반려/상신 버튼 누르지 않습니다.\n"
		f"{login_instruction}\n"
		f"task: {task_text}\n\n"
		"## Done 평가 규칙\n"
		"- 의도한 페이지 도달 + 결과 확인 → done(success=True). 데이터 0건도 OK.\n"
		"- read-only 조회의 본질은 조회 동작 완료지, 데이터 유무 아님."
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
			use_vision=use_vision,
			use_judge=False,
			calculate_cost=False,
			max_actions_per_step=2,
			directly_open_url=False,
			sensitive_data=sensitive_data,
			llm_timeout=600,
			step_timeout=900,
			max_history_items=6,
			max_clickable_elements_length=5000,
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

	tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
	if args.limit:
		tasks = tasks[: args.limit]
	if args.start:
		tasks = tasks[args.start :]

	args.out.mkdir(parents=True, exist_ok=True)
	results_path = args.out / "results.jsonl"
	done_ids = _load_done(results_path) if args.resume else set()

	pending = [t for t in tasks if t["id"] not in done_ids]
	print(f"[INFO] Total: {len(tasks)}  Done(resume skip): {len(done_ids)}  To run: {len(pending)}")
	if not pending:
		print("[INFO] 할 게 없음 — exit")
		return 0

	# Single ChatMLX (model 로딩 한 번)
	llm = ChatMLX(
		model=args.model,
		adapter_path=None if args.no_adapter else args.adapter,
		max_tokens=1024,
		temperature=0.0,
	)

	overall_t0 = time.time()
	done = 0
	succ = 0

	stop_requested = False

	def _on_sigint(signum, frame):
		nonlocal stop_requested
		stop_requested = True
		print("\n[WARN] Ctrl+C — finishing current task then exit.", file=sys.stderr)

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
				use_vision=not args.no_vision,
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

		# Append result line
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
	parser.add_argument("--tasks", type=Path, default=REPO_ROOT / "tasks" / "korus_100.json")
	parser.add_argument("--out", type=Path, default=REPO_ROOT / "eval_mlx_v2")
	parser.add_argument("--adapter", type=str, default="/tmp/our_ckpt_mlx")
	parser.add_argument("--no-adapter", action="store_true")
	parser.add_argument("--model", default="mlx-community/Qwen2.5-VL-32B-Instruct-4bit")
	parser.add_argument("--max-steps", type=int, default=15)
	parser.add_argument("--limit", type=int, default=None, help="첫 N개만")
	parser.add_argument("--start", type=int, default=0, help="앞에서 N개 skip")
	parser.add_argument("--resume", action="store_true", help="results.jsonl에 있는 task_id skip")
	parser.add_argument("--no-vision", action="store_true", default=True,
	                    help="이미지 토큰 제거 (Mac 속도 ↑). 기본 켜져있음.")
	parser.add_argument("--with-vision", action="store_true",
	                    help="명시적으로 vision 활성화 (느림)")
	args = parser.parse_args(argv)
	if args.with_vision:
		args.no_vision = False
	return asyncio.run(main_async(args))


if __name__ == "__main__":
	sys.exit(main())
