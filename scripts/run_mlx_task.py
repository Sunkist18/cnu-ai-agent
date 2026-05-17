"""실 KORUS task — ChatMLX (우리 fine-tuned LoRA) + browser-use Agent.

Phase 4 online task success rate 측정용. Mac에서 직접 KORUS 자동화.

흐름:
1. ChatMLX 로드 (base 32B 4bit MLX + 우리 변환된 LoRA)
2. Browser(storage_state=...) 로 KORUS 진입
3. Agent(task=..., llm=ChatMLX, ...) 실행
4. trajectory 저장 + success/fail 보고

Run:
  python scripts/run_mlx_task.py \\
    --task "결재대기함 확인해줘" \\
    --out trajectories_mlx_v2
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from browser_use import Agent, Browser

from cnu_agent.student.chat_mlx import ChatMLX

REPO_ROOT = Path(__file__).resolve().parent.parent


async def run(
	task_text: str,
	out_root: Path,
	auth_path: Path | None,
	adapter_path: str | None,
	max_steps: int,
	model_path: str,
	korus_url: str,
	username: str | None,
	password: str | None,
	use_storage_state: bool,
	use_vision: bool = True,
) -> int:
	out_dir = out_root / "single_task"
	out_dir.mkdir(parents=True, exist_ok=True)

	llm = ChatMLX(
		model=model_path,
		adapter_path=adapter_path,
		max_tokens=1024,
		temperature=0.0,
	)

	browser_kwargs = dict(
		headless=False,
		user_data_dir=None,
		allowed_domains=["*.korus.ac.kr", "*.cnu.ac.kr"],
	)
	if use_storage_state and auth_path and auth_path.exists():
		browser_kwargs["storage_state"] = str(auth_path)
		print(f"[INFO] using storage_state: {auth_path}")
	else:
		print(f"[INFO] fresh session — agent will handle login")

	browser = Browser(**browser_kwargs)

	# sensitive_data — agent에는 placeholder만 노출, 브라우저에는 실제 값 입력
	sensitive_data = None
	login_instruction = ""
	if not use_storage_state and username and password:
		from urllib.parse import urlparse
		host = urlparse(korus_url).hostname or "korus.ac.kr"
		# 'cnu.korus.ac.kr'.split('.')[-3:] → ['korus','ac','kr'] = 'korus.ac.kr'
		# (이전엔 [-2:]로 'ac.kr'이 돼서 너무 광범위 + 경고 발생)
		parts = host.split(".")
		parent_dom = ".".join(parts[-3:]) if len(parts) >= 3 else host
		sensitive_data = {
			f"https://*.{parent_dom}": {
				"korus_username": username,
				"korus_password": password,
			}
		}
		login_instruction = (
			"\n## 로그인 절차 (첫 단계)\n"
			f"1. {korus_url} 진입 → KORUS는 sso.korus.ac.kr 로그인 페이지로 redirect함.\n"
			"2. 사용자명 입력 필드에 `<secret>korus_username</secret>` 입력.\n"
			"3. 비밀번호 입력 필드에 `<secret>korus_password</secret>` 입력.\n"
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

	print(f"[INFO] task: {task_text}")
	print(f"[INFO] model: {model_path}")
	print(f"[INFO] adapter: {adapter_path or '(none — base)'}")
	print(f"[INFO] max_steps: {max_steps}")

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
			step_timeout=900,  # MLX 32B 4bit 한 step ~200s+, 안전 마진
			max_history_items=6,
			max_clickable_elements_length=5000,
		)
		history = await agent.run(max_steps=max_steps)
	finally:
		try:
			await browser.kill()
		except Exception:  # noqa: BLE001
			pass

	steps = len(history.history)
	is_done = history.is_done()
	# done success?
	success = False
	final_text = ""
	if steps:
		last = history.history[-1]
		mo = getattr(last, "model_output", None) or {}
		if hasattr(mo, "model_dump"):
			mo = mo.model_dump()
		for act in (mo.get("action") if isinstance(mo, dict) else []) or []:
			if isinstance(act, dict) and "done" in act:
				success = bool(act["done"].get("success"))
				final_text = act["done"].get("text", "")[:300]
				break

	print(f"\n=== Run result ===")
	print(f"  steps: {steps}  is_done: {is_done}  success: {success}")
	print(f"  final: {final_text}")

	# Save history
	history.save_to_file(out_dir / "history.json")
	print(f"  history saved → {out_dir / 'history.json'}")
	return 0 if success else 1


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


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--task", required=True, help="자연어 KORUS task (예: '결재대기함 확인해줘')")
	parser.add_argument("--out", type=Path, default=REPO_ROOT / "trajectories_mlx_v2")
	parser.add_argument("--auth", type=Path, default=REPO_ROOT / "auth" / "korus_storage_state.json")
	parser.add_argument("--adapter", type=str, default="/tmp/our_ckpt_mlx",
	                    help="우리 LoRA 변환 경로 (None이면 base만)")
	parser.add_argument("--no-adapter", action="store_true", help="base만 (LoRA 끔)")
	parser.add_argument("--model", default="mlx-community/Qwen2.5-VL-32B-Instruct-4bit")
	parser.add_argument("--max-steps", type=int, default=25)
	parser.add_argument("--url", type=str, default=None)
	parser.add_argument("--fresh-login", action="store_true",
	                    help="storage_state 안 쓰고 agent가 로그인부터 (실 배포 시나리오). "
	                    ".env의 KORUS_USERNAME/PASSWORD 사용.")
	parser.add_argument("--username", default=None, help=".env override")
	parser.add_argument("--password", default=None, help=".env override")
	parser.add_argument("--no-vision", action="store_true", help="이미지 토큰 제거 (Mac 속도 ↑)")
	args = parser.parse_args(argv)

	env = _load_env()
	url = args.url or env.get("KORUS_URL", "https://cnu.korus.ac.kr/")
	username = args.username or env.get("KORUS_USERNAME")
	password = args.password or env.get("KORUS_PASSWORD")
	adapter = None if args.no_adapter else args.adapter

	use_storage = not args.fresh_login

	if not use_storage:
		if not username or not password:
			print("[FAIL] --fresh-login 모드에는 KORUS_USERNAME/PASSWORD 필요 (.env 또는 --username/--password)", file=sys.stderr)
			return 2

	return asyncio.run(run(
		task_text=args.task,
		out_root=args.out,
		auth_path=args.auth if use_storage else None,
		adapter_path=adapter,
		max_steps=args.max_steps,
		model_path=args.model,
		korus_url=url,
		username=username,
		password=password,
		use_storage_state=use_storage,
		use_vision=not args.no_vision,
	))


if __name__ == "__main__":
	sys.exit(main())
