"""학교 GPU 서버 setup용 정보 수집 — 결과 출력을 그대로 채민우에게 보내면 됨.

수집 항목:
1. OS / kernel / shell
2. CPU / RAM
3. GPU (nvidia-smi) — 모델 / VRAM / driver / CUDA
4. Disk free
5. Python / pip / uv / conda
6. 주요 lib 버전 (torch / transformers / peft / vllm / bitsandbytes / flash-attn)
7. HuggingFace cache 경로 + 토큰 여부
8. Git / GitHub PAT
9. KORUS reachability (가장 중요!)
10. External net reachability (huggingface.co, github.com, pypi)
11. Docker / Singularity 유무
12. ssh tunnel 가능 여부 + 외부 노출 포트 정책 (best-effort)

Run on server:
  python scripts/server_info.py > server_info.txt
  # 또는
  curl -fsSL https://... | python  # (옵션 — 우선은 git clone 후 실행)
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SECT = lambda title: print(f"\n=== {title} ===")
KV = lambda k, v: print(f"  {k:32s} {v}")


def _sh(cmd: list[str], timeout: int = 5) -> str:
	try:
		out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
		return (out.stdout + out.stderr).strip()
	except FileNotFoundError:
		return "(not installed)"
	except subprocess.TimeoutExpired:
		return "(timeout)"
	except Exception as e:  # noqa: BLE001
		return f"(error: {e})"


def _which(name: str) -> str:
	p = shutil.which(name)
	return p or "(not found)"


def _http_head(url: str, timeout: int = 5) -> str:
	"""HEAD → 'OK <status> <elapsed_ms>ms' or fail."""
	try:
		import urllib.request
		import urllib.error
		import time as _t
		req = urllib.request.Request(url, method="HEAD",
		                              headers={"User-Agent": "server-info/1.0"})
		t0 = _t.time()
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			dur = (_t.time() - t0) * 1000
			return f"OK {resp.status} ({dur:.0f}ms)"
	except urllib.error.HTTPError as e:  # type: ignore
		return f"HTTP {e.code}"
	except Exception as e:  # noqa: BLE001
		return f"FAIL {type(e).__name__}: {e}"


def main() -> int:
	print(f"# server_info — {datetime.now().isoformat(timespec='seconds')}")
	print(f"# host: {socket.gethostname()}")

	# 1. OS
	SECT("1. OS")
	KV("platform", platform.platform())
	KV("system", f"{platform.system()} {platform.release()}")
	KV("machine", platform.machine())
	KV("python", platform.python_version())
	KV("shell", os.environ.get("SHELL", "?"))
	KV("user", os.environ.get("USER", "?"))
	KV("cwd", os.getcwd())

	# /etc/os-release
	os_rel = Path("/etc/os-release")
	if os_rel.exists():
		for line in os_rel.read_text().splitlines():
			if line.startswith(("NAME=", "VERSION=", "PRETTY_NAME=")):
				k, v = line.split("=", 1)
				KV(f"/etc {k}", v.strip('"'))

	# 2. CPU / RAM
	SECT("2. CPU / RAM")
	cpu_count = os.cpu_count()
	KV("cpu_count (logical)", cpu_count)
	# /proc/cpuinfo model
	cpu_info = Path("/proc/cpuinfo")
	if cpu_info.exists():
		for line in cpu_info.read_text().splitlines()[:20]:
			if line.startswith("model name"):
				KV("cpu model", line.split(":", 1)[1].strip())
				break
	# /proc/meminfo
	mem = Path("/proc/meminfo")
	if mem.exists():
		for line in mem.read_text().splitlines()[:5]:
			KV(line.split(":")[0], line.split(":")[1].strip())

	# 3. GPU
	SECT("3. GPU (nvidia-smi)")
	nv = _sh(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu", "--format=csv"])
	print(nv if nv else "  (nvidia-smi 없음 — CPU only?)")
	cuda = _sh(["nvcc", "--version"])
	if cuda and "(not installed)" not in cuda:
		KV("nvcc", cuda.splitlines()[-1] if cuda else "?")
	# nvidia-smi -L
	gpu_list = _sh(["nvidia-smi", "-L"])
	print(gpu_list)

	# 4. Disk
	SECT("4. Disk")
	for path in ["/", os.path.expanduser("~"), "/tmp", "/NHNHOME", "/scratch", "/data"]:
		try:
			st = os.statvfs(path)
			free_gb = (st.f_bavail * st.f_frsize) / (1024**3)
			total_gb = (st.f_blocks * st.f_frsize) / (1024**3)
			KV(path, f"free {free_gb:.1f}GB / {total_gb:.1f}GB")
		except Exception:
			KV(path, "(not accessible)")

	# 5. Python / package managers
	SECT("5. Python / package managers")
	KV("python", _which("python"))
	KV("python3", _which("python3"))
	KV("pip", _which("pip"))
	KV("uv", _which("uv"))
	KV("conda", _which("conda"))
	KV("mamba", _which("mamba"))
	KV("virtualenv site-packages", str(Path(sys.executable).parent.parent / "lib"))

	# 6. Key lib versions
	SECT("6. Python lib versions (현재 env 기준)")
	for pkg in [
		"torch", "transformers", "peft", "accelerate", "trl",
		"bitsandbytes", "vllm", "flash_attn", "huggingface_hub",
		"pydantic", "browser_use", "mlx", "mlx_vlm",
	]:
		try:
			mod = __import__(pkg)
			KV(pkg, getattr(mod, "__version__", "?"))
		except Exception:
			KV(pkg, "(not installed)")

	# 7. HuggingFace
	SECT("7. HuggingFace")
	hf_home = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
	KV("HF_HOME", hf_home)
	hf_token_env = "HF_TOKEN" in os.environ or "HUGGING_FACE_HUB_TOKEN" in os.environ
	hf_token_file = Path(hf_home) / "token"
	KV("HF_TOKEN env", "set" if hf_token_env else "(none)")
	KV("HF token file", "exists" if hf_token_file.exists() else "(none)")
	# Cache size
	cache_path = Path(hf_home) / "hub"
	if cache_path.exists():
		try:
			out = _sh(["du", "-sh", str(cache_path)], timeout=10)
			KV("hub cache size", out.split()[0] if out else "?")
		except Exception:
			pass

	# 8. Git
	SECT("8. Git / GitHub")
	KV("git", _which("git"))
	KV("git version", _sh(["git", "--version"]))
	KV("gh", _which("gh"))
	gconf = _sh(["git", "config", "--get", "user.email"])
	KV("git user.email", gconf or "(unset)")
	KV("GITHUB_TOKEN env", "set" if os.environ.get("GITHUB_TOKEN") else "(none)")
	ssh_key = Path.home() / ".ssh" / "id_rsa.pub"
	ssh_key_ed = Path.home() / ".ssh" / "id_ed25519.pub"
	KV("ssh public key", str(ssh_key) if ssh_key.exists() else str(ssh_key_ed) if ssh_key_ed.exists() else "(none)")

	# 9. KORUS reachability (가장 중요!)
	SECT("9. KORUS reachability (학내망 필수)")
	def _dns(h):
		try:
			return socket.gethostbyname(h)
		except Exception as e:  # noqa: BLE001
			return f"(failed: {e})"
	KV("DNS cnu.korus.ac.kr", _dns("cnu.korus.ac.kr"))
	KV("DNS sso.korus.ac.kr", _dns("sso.korus.ac.kr"))
	KV("HEAD cnu.korus.ac.kr", _http_head("https://cnu.korus.ac.kr/"))
	KV("HEAD sso.korus.ac.kr", _http_head("https://sso.korus.ac.kr/"))

	# 10. External net
	SECT("10. External net")
	KV("HEAD huggingface.co", _http_head("https://huggingface.co/"))
	KV("HEAD github.com", _http_head("https://github.com/"))
	KV("HEAD pypi.org", _http_head("https://pypi.org/simple/"))

	# 11. Container runtime
	SECT("11. Container runtime")
	KV("docker", _which("docker"))
	KV("podman", _which("podman"))
	KV("singularity", _which("singularity"))
	KV("apptainer", _which("apptainer"))

	# 12. Chromium / Playwright (browser-use 핵심)
	SECT("12. Chromium / Playwright deps")
	KV("chromium", _which("chromium") or _which("chromium-browser") or _which("google-chrome"))
	KV("Xvfb", _which("Xvfb"))
	KV("xdpyinfo", _which("xdpyinfo"))
	KV("DISPLAY env", os.environ.get("DISPLAY", "(unset — headless server)"))
	# libnss3 / libatk required by playwright
	for lib in ["libnss3", "libatk-1.0-0", "libcups2", "libxcomposite1"]:
		out = _sh(["ldconfig", "-p"], timeout=5)
		KV(f"  {lib}", "found" if lib in out else "(missing — apt install 필요)")
		break  # ldconfig once enough check

	# 13. Open ports / firewall (best-effort)
	SECT("13. Network policy")
	KV("ss/netstat exists", _which("ss") or _which("netstat"))
	KV("iptables", _which("iptables"))
	KV("ufw", _which("ufw"))

	print(f"\n=== END ===\n")
	print("📌 이 출력 통째로 채민우에게 전달하면 setup 가이드 작성 가능")
	return 0


if __name__ == "__main__":
	sys.exit(main())
