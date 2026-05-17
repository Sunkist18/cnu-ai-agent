"""학교 서버에서 KORUS 접근 가능한지 + 기본 동작 확인.

체크 순서:
1. DNS — cnu.korus.ac.kr 풀리는지
2. HTTPS GET / — 200 + 로그인 페이지인지
3. SSO redirect — sso.korus.ac.kr 도 풀리는지
4. (선택) .env에 KORUS_USERNAME/PASSWORD 있으면 form POST 시도 → 세션 쿠키 받는지

Run:
  python scripts/server_check_korus.py
  # 또는 인증까지:
  python scripts/server_check_korus.py --try-login
"""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import urllib.request
import urllib.error

KORUS_URL = "https://cnu.korus.ac.kr/"
SSO_URL = "https://sso.korus.ac.kr/"


def _load_env() -> dict[str, str]:
	env = Path(__file__).resolve().parent.parent / ".env"
	out = {}
	if env.exists():
		for line in env.read_text(encoding="utf-8").splitlines():
			line = line.strip()
			if not line or line.startswith("#") or "=" not in line:
				continue
			k, v = line.split("=", 1)
			out[k.strip()] = v.strip()
	return out


def _dns(host: str) -> tuple[bool, str]:
	try:
		ip = socket.gethostbyname(host)
		return True, ip
	except socket.gaierror as e:
		return False, str(e)


def _https_get(url: str, timeout: int = 10) -> tuple[bool, int, str, dict]:
	"""GET url. Returns (ok, status, snippet, headers)."""
	req = urllib.request.Request(
		url,
		headers={
			"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
			"Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
		},
	)
	try:
		ctx = ssl.create_default_context()
		t0 = time.time()
		with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
			dur = time.time() - t0
			body = resp.read(8192).decode("utf-8", errors="replace")
			hdrs = dict(resp.getheaders())
			hdrs["_request_ms"] = f"{dur*1000:.0f}"
			return True, resp.status, body, hdrs
	except urllib.error.HTTPError as e:
		return False, e.code, str(e), {}
	except Exception as e:  # noqa: BLE001
		return False, 0, f"{type(e).__name__}: {e}", {}


def _check(label: str, ok: bool, detail: str = "") -> None:
	mark = "✅" if ok else "❌"
	print(f"  {mark} {label}{(' — ' + detail) if detail else ''}")


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--try-login", action="store_true",
	                    help=".env의 KORUS_USERNAME/PASSWORD로 form POST 시도 (cookies 확인)")
	parser.add_argument("--proxy", help="HTTP proxy URL (학내망 우회용)")
	args = parser.parse_args(argv)

	if args.proxy:
		import os
		os.environ["http_proxy"] = args.proxy
		os.environ["https_proxy"] = args.proxy
		print(f"[INFO] proxy: {args.proxy}")

	print(f"\n=== KORUS reachability check ===\n")

	all_ok = True

	# 1. DNS
	print("[1] DNS")
	for host in [urlparse(KORUS_URL).hostname, urlparse(SSO_URL).hostname]:
		ok, info = _dns(host)
		_check(f"{host}", ok, info)
		all_ok &= ok

	# 2. HTTPS GET KORUS root (page는 JS 렌더링이라 body markers는 best-effort)
	print("\n[2] HTTPS GET cnu.korus.ac.kr/")
	ok, status, body, hdrs = _https_get(KORUS_URL)
	_check(f"status={status} ({hdrs.get('_request_ms','?')}ms)", ok, "")
	all_ok &= ok
	if ok:
		login_hint = any(k in body for k in [
			"lginView", "userId01", "비밀번호", "로그인",
			"KORUS", "korus", "<title>", "<html",
		])
		_check("HTML 응답 (KORUS or html marker)", login_hint, "" if login_hint else "본문 비정상 — 확인 필요")

	# 3. SSO endpoint — informational. 보통 직접 probe는 막혀있고 browser redirect로만 동작.
	print("\n[3] TCP 443 sso.korus.ac.kr (informational — fail해도 browser redirect는 됨)")
	sso_host = urlparse(SSO_URL).hostname
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.settimeout(5)
		s.connect((sso_host, 443))
		s.close()
		_check("TCP 443 연결", True, "OK")
	except Exception as e:  # noqa: BLE001
		_check("TCP 443 연결 (informational)", False, f"{type(e).__name__} — 보통 정상, browser는 redirect로 도달")

	# 4. Optional login attempt
	if args.try_login:
		print("\n[4] Login attempt (.env credentials)")
		env = _load_env()
		u = env.get("KORUS_USERNAME")
		p = env.get("KORUS_PASSWORD")
		if not (u and p):
			_check(".env 자격증명", False, "KORUS_USERNAME/PASSWORD 없음")
		else:
			try:
				import http.cookiejar
				cj = http.cookiejar.CookieJar()
				opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
				opener.addheaders = [
					("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"),
				]
				# 1) get login page (세션 쿠키 받기)
				resp = opener.open(KORUS_URL, timeout=10)
				resp.read()
				_check("세션 쿠키 수신", len(cj) > 0, f"{len(cj)} cookies")
				print("    cookies:", [c.name + "@" + c.domain for c in cj])
				# Real login은 KORUS Spring form action 알아야 함 — 여기선 reachability만
				print("    (실제 form POST는 browser-use가 처리 — 여기선 쿠키 reachability까지만)")
			except Exception as e:  # noqa: BLE001
				_check("login probe", False, f"{type(e).__name__}: {e}")

	print("\n=== Summary ===")
	if all_ok:
		print("✅ KORUS 접근 가능 — agent inference 준비 완료")
		return 0
	else:
		print("❌ 일부 실패 — 학내망/방화벽/proxy 확인 필요")
		print("   (학내망에서만 접근 가능. 외부망이면 VPN 또는 --proxy 필요)")
		return 1


if __name__ == "__main__":
	sys.exit(main())
