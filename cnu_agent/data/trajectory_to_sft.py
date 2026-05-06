"""Phase 2 — trajectory → Qwen2.5-VL ChatML JSONL (PLAN.md §5).

각 step → 학습 샘플 1개:
    {
        "messages": [
            {"role": "system",    "content": <browser-use system prompt>},
            {"role": "user",      "content": [
                {"type": "image", "image": "file:///abs/path/screenshots/step_N.png"},
                {"type": "text",  "text": <DOM 직렬화 + 작업 컨텍스트>},
            ]},
            {"role": "assistant", "content": <model_output JSON 문자열>}
        ],
        "task_id": "...",
        "step":    N
    }

핵심 결정:
- system prompt는 step.input_messages[0] (Teacher가 실제로 받은 것 그대로)
- user content는 마지막 user turn (가장 최근 state). browser-use가 이전 turn은
  message_compaction으로 history 텍스트로 압축하므로 마지막 user 만으로 충분.
- assistant target은 model_output dict의 JSON serialization (Student가 따라할 정답)
- screenshot은 top-level `screenshot_path` field 기준 (input_messages 안의 image_url
  보다 안정적). 절대경로 file:// URL로 변환.
- task_id 단위 80/20 split — step 단위 split은 같은 trajectory의 step이 train/eval
  양쪽에 들어가서 데이터 누설.
- 기본은 success/fail 무관하게 모든 step 포함. `--success-only`로 done.success=True
  trajectory만 골라낼 수 있음.

Run:
  python -m cnu_agent.data.trajectory_to_sft \\
    --in  trajectories \\
    --out data \\
    --eval-ratio 0.2 \\
    --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN = REPO_ROOT / "trajectories"
DEFAULT_OUT = REPO_ROOT / "data"


def _extract_text(content: Any) -> str:
	"""Pull plain-text content out of either a string or a list of content parts."""
	if content is None:
		return ""
	if isinstance(content, str):
		return content
	if isinstance(content, list):
		parts: list[str] = []
		for p in content:
			if not isinstance(p, dict):
				continue
			t = p.get("type")
			if t is None or t == "text":
				txt = p.get("text", "")
				if txt:
					parts.append(str(txt))
		return "\n".join(parts).strip()
	return ""


def _resolve_screenshot(traj_dir: Path, rel: str | None) -> str | None:
	"""screenshot_path (relative) → absolute file:// URL, or None if missing/invalid."""
	if not rel:
		return None
	full = (traj_dir / rel).resolve()
	if not full.exists():
		return None
	return f"file://{full}"


def step_to_sample(step: dict[str, Any], traj_dir: Path) -> dict[str, Any] | None:
	"""Convert one step from steps.jsonl into one ChatML training sample.

	Returns None when the step is too incomplete to be useful (missing system
	prompt, no user turn, or empty model_output).
	"""
	msgs = step.get("input_messages") or []
	if not isinstance(msgs, list) or not msgs:
		return None

	# 1. system prompt — first system message
	system_text: str | None = None
	for m in msgs:
		if isinstance(m, dict) and m.get("role") == "system":
			system_text = _extract_text(m.get("content"))
			break
	if not system_text:
		return None

	# 2. last user turn — current state
	last_user: dict | None = None
	for m in reversed(msgs):
		if isinstance(m, dict) and m.get("role") == "user":
			last_user = m
			break
	if not last_user:
		return None
	user_text = _extract_text(last_user.get("content"))
	if not user_text:
		return None

	# 3. screenshot — top-level field is authoritative (path on disk).
	screenshot_url = _resolve_screenshot(traj_dir, step.get("screenshot_path"))

	# 4. assistant target — model_output as canonical JSON
	model_output = step.get("model_output")
	if not model_output:
		return None
	assistant_text = json.dumps(model_output, ensure_ascii=False)

	user_content: list[dict[str, Any]] = []
	if screenshot_url:
		user_content.append({"type": "image", "image": screenshot_url})
	user_content.append({"type": "text", "text": user_text})

	return {
		"messages": [
			{"role": "system", "content": system_text},
			{"role": "user", "content": user_content},
			{"role": "assistant", "content": assistant_text},
		],
		"task_id": step.get("task_id"),
		"step": step.get("step"),
	}


def walk_trajectories(root: Path) -> Iterator[tuple[str, Path, list[dict]]]:
	"""Yield (task_id, trajectory_dir, steps_list) for every directory with steps.jsonl."""
	for d in sorted(root.iterdir()):
		if not d.is_dir():
			continue
		steps_path = d / "steps.jsonl"
		if not steps_path.exists():
			continue
		steps: list[dict] = []
		for line in steps_path.read_text(encoding="utf-8").splitlines():
			line = line.strip()
			if not line:
				continue
			try:
				steps.append(json.loads(line))
			except json.JSONDecodeError:
				continue
		yield d.name, d, steps


def _is_trajectory_successful(traj_dir: Path) -> bool:
	"""Look at history.json's last step for done.success=True.

	If history is malformed or no done action, treat as failed.
	"""
	hp = traj_dir / "history.json"
	if not hp.exists():
		return False
	try:
		hist = json.loads(hp.read_text(encoding="utf-8"))
	except json.JSONDecodeError:
		return False
	steps = hist.get("history") or []
	if not steps:
		return False
	for act in (steps[-1].get("model_output") or {}).get("action", []) or []:
		if isinstance(act, dict) and "done" in act:
			return bool(act["done"].get("success"))
	return False


def split_train_eval(
	samples_by_task: dict[str, list[dict]],
	eval_ratio: float,
	seed: int,
) -> tuple[list[dict], list[dict], list[str]]:
	"""Task-level split. Returns (train_samples, eval_samples, eval_task_ids)."""
	task_ids = sorted(samples_by_task.keys())
	if not task_ids:
		return [], [], []
	rng = random.Random(seed)
	shuffled = task_ids[:]
	rng.shuffle(shuffled)
	# 최소 eval task 1개 보장
	n_eval = max(1, int(round(len(shuffled) * eval_ratio)))
	# 데이터셋이 너무 작아 train이 0 되는 케이스 방지
	n_eval = min(n_eval, len(shuffled) - 1) if len(shuffled) > 1 else n_eval
	eval_tasks = set(shuffled[:n_eval])

	train_samples: list[dict] = []
	eval_samples: list[dict] = []
	for tid, samples in samples_by_task.items():
		dst = eval_samples if tid in eval_tasks else train_samples
		dst.extend(samples)
	return train_samples, eval_samples, sorted(eval_tasks)


def write_jsonl(path: Path, samples: list[dict]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as f:
		for s in samples:
			f.write(json.dumps(s, ensure_ascii=False) + "\n")


def run_conversion(
	in_root: Path,
	out_root: Path,
	eval_ratio: float,
	seed: int,
	success_only: bool,
) -> int:
	if not in_root.exists():
		print(f"[FAIL] {in_root} 없음", file=sys.stderr)
		return 2

	samples_by_task: dict[str, list[dict]] = {}
	n_steps_seen = 0
	n_steps_skipped = 0
	n_traj_skipped_failed = 0

	for tid, tdir, steps in walk_trajectories(in_root):
		if success_only and not _is_trajectory_successful(tdir):
			n_traj_skipped_failed += 1
			continue
		samples: list[dict] = []
		for step in steps:
			n_steps_seen += 1
			s = step_to_sample(step, tdir)
			if s is None:
				n_steps_skipped += 1
				continue
			samples.append(s)
		if samples:
			samples_by_task[tid] = samples

	train, eval_, eval_task_ids = split_train_eval(samples_by_task, eval_ratio, seed)

	out_root.mkdir(parents=True, exist_ok=True)
	train_path = out_root / "korus_train.jsonl"
	eval_path = out_root / "korus_eval.jsonl"
	write_jsonl(train_path, train)
	write_jsonl(eval_path, eval_)

	print(f"=== Phase 2 변환 결과 ===")
	print(f"  trajectory   : {len(samples_by_task)} 개 사용 (success_only={success_only}, skipped_failed={n_traj_skipped_failed})")
	print(f"  step         : {n_steps_seen} 처리, {n_steps_skipped} 스킵 (불완전)")
	print(f"  train        : {len(train):4d} samples → {train_path}")
	print(f"  eval         : {len(eval_):4d} samples → {eval_path}")
	print(f"  eval task ids: {eval_task_ids}")
	return 0


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="trajectory → Qwen ChatML JSONL (Phase 2)")
	parser.add_argument("--in", dest="in_root", type=Path, default=DEFAULT_IN)
	parser.add_argument("--out", dest="out_root", type=Path, default=DEFAULT_OUT)
	parser.add_argument("--eval-ratio", type=float, default=0.2)
	parser.add_argument("--seed", type=int, default=42)
	parser.add_argument(
		"--success-only",
		action="store_true",
		help="done.success=True 인 trajectory만 사용 (기본: 모든 trajectory 포함)",
	)
	args = parser.parse_args(argv)

	return run_conversion(
		in_root=args.in_root,
		out_root=args.out_root,
		eval_ratio=args.eval_ratio,
		seed=args.seed,
		success_only=args.success_only,
	)


if __name__ == "__main__":
	sys.exit(main())
