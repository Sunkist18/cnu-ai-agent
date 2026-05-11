"""Trajectory screenshots → mp4 video (ffmpeg).

browser-use는 CDP-based라 `record_video_dir`이 실제 녹화에 연결 안 됨. 대신 우리가
이미 저장한 `trajectories/<task>/screenshots/step_N.png` 시퀀스를 mp4로 합성.

각 frame에 step 번호 + agent next_goal 자막 오버레이.

Run:
  python scripts/screenshots_to_video.py \\
    --traj-root trajectories_demo \\
    --out-dir   videos/v1_demo \\
    --fps       0.6
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# macOS에 기본 설치된 한글 폰트 (없으면 None — text overlay 생략)
KOREAN_FONT_CANDIDATES = [
	"/System/Library/Fonts/Apple SD Gothic Neo.ttc",
	"/System/Library/Fonts/AppleSDGothicNeo.ttc",
	"/Library/Fonts/AppleGothic.ttf",
	"/System/Library/Fonts/Supplemental/AppleGothic.ttf",
]


def _find_font() -> str | None:
	for p in KOREAN_FONT_CANDIDATES:
		if Path(p).exists():
			return p
	return None


def _load_goals(traj_dir: Path) -> dict[int, str]:
	"""step_n → next_goal 매핑."""
	hist_p = traj_dir / "history.json"
	if not hist_p.exists():
		return {}
	hist = json.loads(hist_p.read_text(encoding="utf-8"))
	out: dict[int, str] = {}
	# history.history는 step별 dict — step number는 1-based로 enumerate
	for i, step in enumerate(hist.get("history", []), start=1):
		goal = (step.get("model_output") or {}).get("next_goal", "") or ""
		out[i] = goal[:120]  # 자막 길이 제한
	return out


def _sanitize_for_drawtext(text: str) -> str:
	"""ffmpeg drawtext: ',', '\\', '\\'' 등 escape."""
	text = text.replace("\\", "\\\\")
	text = text.replace("'", "\\'")
	text = text.replace(":", "\\:")
	text = text.replace(",", "\\,")
	text = text.replace("%", "\\%")
	# control chars 제거
	text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
	return text


def render_one(traj_dir: Path, out_path: Path, fps: float, font: str | None) -> bool:
	screenshots = sorted(
		(traj_dir / "screenshots").glob("step_*.png"),
		key=lambda p: int(re.search(r"step_(\d+)", p.name).group(1)),
	)
	if not screenshots:
		print(f"  ⚠️ {traj_dir.name}: no screenshots", file=sys.stderr)
		return False

	goals = _load_goals(traj_dir)
	task_id = traj_dir.name

	# 임시 concat list (ffmpeg concat demuxer)
	concat_list = out_path.parent / f"_{task_id}_concat.txt"
	out_path.parent.mkdir(parents=True, exist_ok=True)
	duration_per_frame = 1.0 / fps
	lines = []
	for png in screenshots:
		lines.append(f"file '{png.resolve()}'")
		lines.append(f"duration {duration_per_frame:.3f}")
	# concat demuxer는 마지막 frame은 duration 줄을 한 번 더 안 적음
	if lines:
		lines.append(f"file '{screenshots[-1].resolve()}'")
	concat_list.write_text("\n".join(lines), encoding="utf-8")

	# drawtext filter — step 번호 + goal 자막 (옵션)
	vf_parts = ["scale=1400:-2"]  # uniform width, keep aspect
	if font:
		# 각 frame마다 다른 텍스트를 표시하려면 동적 자막 필요. 단순화 — 좌상단에 task_id 만 표시.
		# 좀 더 좋게 하려면 별도 sidecar subtitle 만들어야 함.
		font_esc = font.replace(":", "\\:")
		title_text = _sanitize_for_drawtext(f"{task_id}")
		vf_parts.append(
			f"drawtext=fontfile='{font_esc}':text='{title_text}':"
			f"x=20:y=20:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=8"
		)

	vf = ",".join(vf_parts)

	cmd = [
		"ffmpeg",
		"-y",  # overwrite
		"-f", "concat",
		"-safe", "0",
		"-i", str(concat_list),
		"-vf", vf,
		"-c:v", "libx264",
		"-pix_fmt", "yuv420p",
		"-r", "30",  # output fps (interpolation)
		str(out_path),
	]

	print(f"  ▶️ {task_id}: {len(screenshots)} frames @ {duration_per_frame:.1f}s → {out_path.name}")
	result = subprocess.run(cmd, capture_output=True, text=True)
	if result.returncode != 0:
		print(f"  ❌ ffmpeg failed for {task_id}:\n{result.stderr[-500:]}", file=sys.stderr)
		concat_list.unlink(missing_ok=True)
		return False
	concat_list.unlink(missing_ok=True)
	# Generate per-step subtitle sidecar (SRT) for downstream editing
	srt_path = out_path.with_suffix(".srt")
	srt_lines = []
	for i, png in enumerate(screenshots, start=1):
		start = (i - 1) * duration_per_frame
		end = i * duration_per_frame
		def fmt(t: float) -> str:
			h, rem = divmod(t, 3600)
			m, s = divmod(rem, 60)
			ms = int((s - int(s)) * 1000)
			return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"
		text = goals.get(i, "")
		srt_lines.append(f"{i}\n{fmt(start)} --> {fmt(end)}\nStep {i}: {text[:80]}\n")
	srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
	return True


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--traj-root", type=Path, default=REPO_ROOT / "trajectories")
	parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "videos")
	parser.add_argument("--fps", type=float, default=0.6, help="frames per second (0.6 ≈ 1.67초/frame)")
	parser.add_argument("--ids", nargs="*", default=None, help="특정 task id만 (생략 시 전부)")
	args = parser.parse_args(argv)

	font = _find_font()
	if not font:
		print("[WARN] 한글 폰트 못 찾음 — text overlay 생략", file=sys.stderr)

	args.out_dir.mkdir(parents=True, exist_ok=True)
	rendered: list[Path] = []
	for traj in sorted(args.traj_root.iterdir()):
		if not traj.is_dir():
			continue
		if args.ids and traj.name not in args.ids:
			continue
		if not (traj / "history.json").exists():
			continue
		out = args.out_dir / f"{traj.name}.mp4"
		if render_one(traj, out, args.fps, font):
			rendered.append(out)

	print(f"\n=== {len(rendered)} 영상 생성 ===")
	for p in rendered:
		size = p.stat().st_size / 1024
		print(f"  {p}  ({size:.0f} KB)")

	# 합본 mp4 (선택)
	if len(rendered) > 1:
		concat_list = args.out_dir / "_concat_all.txt"
		concat_list.write_text(
			"\n".join(f"file '{p.resolve()}'" for p in rendered), encoding="utf-8"
		)
		all_out = args.out_dir / "ALL.mp4"
		cmd = [
			"ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
			"-c", "copy", str(all_out),
		]
		r = subprocess.run(cmd, capture_output=True, text=True)
		if r.returncode == 0:
			print(f"  합본 → {all_out} ({all_out.stat().st_size/1024:.0f} KB)")
		else:
			print(f"  합본 실패: {r.stderr[-300:]}", file=sys.stderr)
		concat_list.unlink(missing_ok=True)
	return 0


if __name__ == "__main__":
	sys.exit(main())
