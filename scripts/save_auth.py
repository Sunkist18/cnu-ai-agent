"""KORUS storage_state 1회 캡처 (Phase 0b 진입 전 1회 수동 실행).

흐름:
1. .env에서 KORUS_URL 읽음
2. headless=False Chromium을 띄워 KORUS 진입
3. 사용자가 브라우저 창에서 직접 로그인 (.env에 USERNAME/PASSWORD 있음 — 본인이 복붙)
4. 로그인 완료 신호:
   - TTY (실제 터미널)면 Enter 키
   - 비-TTY (Claude Code의 `!` prefix 등)면 다른 곳에서 sentinel 파일 생성:
       touch auth/.login_done
5. CDP로 모든 도메인 쿠키 추출 → auth/korus_storage_state.json 저장
6. 브라우저 종료

Why dual signal: `input()`은 stdin이 파이프일 때 EOF로 즉시 종료. Claude Code의
`! python ...` 실행은 stdin TTY 아님 → 무조건 sentinel 파일이 필요.

Run: `python scripts/save_auth.py`  (max 대기 시간: 10분)
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from browser_use import Browser

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
OUT_FILE = REPO_ROOT / "auth" / "korus_storage_state.json"
SENTINEL = REPO_ROOT / "auth" / ".login_done"
WAIT_TIMEOUT_SEC = 600  # 10분


def _load_env(path: Path) -> dict[str, str]:
	"""Tiny .env parser — KEY=VALUE per line, '#' comments, no escapes."""
	if not path.exists():
		raise FileNotFoundError(f".env not found at {path}")
	out: dict[str, str] = {}
	for raw in path.read_text(encoding="utf-8").splitlines():
		line = raw.strip()
		if not line or line.startswith("#"):
			continue
		key, _, value = line.partition("=")
		key = key.strip()
		if not key:
			continue
		out[key] = value.strip()
	return out


async def _wait_for_done(timeout_sec: int) -> bool:
	"""Block until either Enter (TTY) or sentinel file appears, up to `timeout_sec`.

	Returns True on signal, False on timeout.
	Both watchers race; whichever fires first wins.
	"""
	loop = asyncio.get_event_loop()

	async def _wait_input() -> str | None:
		if not sys.stdin.isatty():
			# 비-TTY면 input() 즉시 EOF로 종료 → 이 코루틴은 영원히 끝나지 않게 sleep.
			# (sentinel/timeout이 race를 종료시킴)
			await asyncio.sleep(timeout_sec + 1)
			return None
		try:
			return await loop.run_in_executor(None, input)
		except (EOFError, KeyboardInterrupt):
			return None

	async def _wait_sentinel() -> bool:
		deadline = time.monotonic() + timeout_sec
		while time.monotonic() < deadline:
			if SENTINEL.exists():
				try:
					SENTINEL.unlink()
				except FileNotFoundError:
					pass
				return True
			await asyncio.sleep(1.0)
		return False

	input_task = asyncio.create_task(_wait_input())
	sentinel_task = asyncio.create_task(_wait_sentinel())
	try:
		done, pending = await asyncio.wait(
			{input_task, sentinel_task},
			timeout=timeout_sec,
			return_when=asyncio.FIRST_COMPLETED,
		)
	finally:
		for t in (input_task, sentinel_task):
			if not t.done():
				t.cancel()

	if not done:
		return False
	# 어떤 task가 끝났든 신호로 간주 (sentinel은 True/False 반환, input은 str/None)
	for t in done:
		result = t.result()
		if result is None:
			# input EOF/KeyboardInterrupt — sentinel이 race에서 진 게 아니면 abort
			# 단, sentinel_task가 아직 살아있고 timeout 안이면 계속 기다리진 않음 (race semantic)
			continue
		return True
	return False


async def main() -> int:
	env = _load_env(ENV_FILE)
	url = env.get("KORUS_URL")
	if not url:
		print("[FAIL] KORUS_URL이 .env에 없음", file=sys.stderr)
		return 2

	if env.get("KORUS_USERNAME") and env.get("KORUS_PASSWORD"):
		print(f"[INFO] .env에 KORUS_USERNAME/PASSWORD 있음 — 로그인 폼에서 직접 채워주세요.")

	print(f"[INFO] KORUS 진입: {url}")
	print(f"[INFO] storage_state 저장 위치: {OUT_FILE}")

	browser = Browser(
		headless=False,
		# storage_state=None이라 빈 세션 — 사용자가 처음부터 로그인.
		# user_data_dir=None이면 매번 임시 프로필 — storage_state 충돌 방지.
		user_data_dir=None,
	)
	try:
		await browser.start()
		await browser.navigate_to(url)

		# 신호 대기 — TTY면 Enter, 아니면 sentinel 파일.
		SENTINEL.parent.mkdir(parents=True, exist_ok=True)
		if SENTINEL.exists():
			SENTINEL.unlink()  # stale 제거

		print()
		print("=" * 60)
		print("브라우저에서 로그인을 완료해주세요.")
		print(f"완료 신호 (둘 중 하나):")
		print(f"  (A) 이 터미널이 대화식이면 Enter")
		print(f"  (B) 비대화식 (Claude Code `!` 등)이면 다른 곳에서:")
		print(f"        touch {SENTINEL}")
		print(f"최대 대기 시간: {WAIT_TIMEOUT_SEC // 60}분")
		print("=" * 60)
		print(f"[stdin TTY?] {sys.stdin.isatty()}", flush=True)

		signaled = await _wait_for_done(WAIT_TIMEOUT_SEC)
		if not signaled:
			print(f"\n[TIMEOUT] {WAIT_TIMEOUT_SEC}초 동안 신호 없음", file=sys.stderr)
			return 124

		state = await browser.export_storage_state(output_path=OUT_FILE)
		n_cookies = len(state.get("cookies", []))
		domains = sorted({c["domain"] for c in state.get("cookies", [])})
		print(f"[OK] {n_cookies}개 쿠키 저장 → {OUT_FILE}")
		print(f"[OK] 도메인: {', '.join(domains) if domains else '(없음)'}")
		if n_cookies == 0:
			print("[WARN] 쿠키가 0개 — 로그인 안 끝났거나 쿠키 없는 SSO 일 수 있음.", file=sys.stderr)
			return 1
		return 0
	finally:
		try:
			await browser.kill()
		except Exception:  # noqa: BLE001
			pass


if __name__ == "__main__":
	sys.exit(asyncio.run(main()))
