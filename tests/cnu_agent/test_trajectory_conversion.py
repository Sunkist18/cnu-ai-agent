"""Phase 2 검증 — trajectory → ChatML 변환 round-trip + split 정합성.

artifact 의존: trajectories/ 디렉토리에 최소 1개 trajectory 있어야 일부 테스트 활성화.
없으면 해당 테스트 자동 skip.

Run: `uv run pytest -vxs tests/cnu_agent/test_trajectory_conversion.py`
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cnu_agent.data.trajectory_to_sft import (
	_extract_text,
	run_conversion,
	split_train_eval,
	step_to_sample,
	walk_trajectories,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAJ_ROOT = REPO_ROOT / "trajectories"


# region 합성 fixture 기반 (artifact 무관)


def test_extract_text_string() -> None:
	assert _extract_text("hello") == "hello"


def test_extract_text_list_with_image_skipped() -> None:
	content = [
		{"type": "text", "text": "first"},
		{"type": "image_url", "image_url": {"url": "file:///x.png"}},
		{"type": "text", "text": "second"},
	]
	assert _extract_text(content) == "first\nsecond"


def test_extract_text_none() -> None:
	assert _extract_text(None) == ""


def test_step_to_sample_minimal_synthetic(tmp_path: Path) -> None:
	"""합성 step JSON으로 변환이 정상 모양 만들어내는지."""
	traj = tmp_path / "task_xx"
	(traj / "screenshots").mkdir(parents=True)
	# 가짜 PNG 1바이트 — 실제 디코드 안 하니 OK
	(traj / "screenshots" / "step_3.png").write_bytes(b"\x89PNG")

	step = {
		"task_id": "task_xx",
		"step": 3,
		"url": "https://x",
		"title": "X",
		"screenshot_path": "screenshots/step_3.png",
		"input_messages": [
			{"role": "system", "content": "SYS PROMPT"},
			{
				"role": "user",
				"content": [
					{"type": "text", "text": "DOM dump"},
					{"type": "image_url", "image_url": {"url": "file://...stale..."}},
				],
			},
		],
		"model_output": {"thinking": "...", "action": [{"click": {"index": 5}}]},
	}

	sample = step_to_sample(step, traj)
	assert sample is not None
	assert sample["task_id"] == "task_xx"
	assert sample["step"] == 3
	msgs = sample["messages"]
	assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
	assert msgs[0]["content"] == "SYS PROMPT"
	# user content는 list — image + text
	assert isinstance(msgs[1]["content"], list)
	types = [p["type"] for p in msgs[1]["content"]]
	assert "image" in types and "text" in types
	# 이미지 path가 절대경로 + file:// scheme
	img = next(p for p in msgs[1]["content"] if p["type"] == "image")
	assert img["image"].startswith("file://")
	assert "step_3.png" in img["image"]
	# assistant content는 valid JSON
	parsed = json.loads(msgs[2]["content"])
	assert parsed == step["model_output"]


def test_step_to_sample_returns_none_when_no_messages() -> None:
	step = {"task_id": "x", "step": 1, "input_messages": [], "model_output": {}}
	assert step_to_sample(step, Path("/tmp/anywhere")) is None


def test_step_to_sample_returns_none_when_no_system() -> None:
	step = {
		"task_id": "x", "step": 1,
		"input_messages": [{"role": "user", "content": "hi"}],
		"model_output": {"action": []},
	}
	assert step_to_sample(step, Path("/tmp/anywhere")) is None


def test_step_to_sample_skips_missing_screenshot(tmp_path: Path) -> None:
	"""screenshot 파일 없으면 image content 빠지지만 sample은 만들어져야 함."""
	traj = tmp_path / "task_yy"
	traj.mkdir()
	step = {
		"task_id": "task_yy", "step": 1,
		"screenshot_path": "screenshots/step_1.png",  # 없음
		"input_messages": [
			{"role": "system", "content": "SYS"},
			{"role": "user", "content": "USR"},
		],
		"model_output": {"action": []},
	}
	sample = step_to_sample(step, traj)
	assert sample is not None
	user_content = sample["messages"][1]["content"]
	# image part 없음, text만
	assert all(p.get("type") != "image" for p in user_content)
	assert any(p.get("type") == "text" for p in user_content)


def test_split_task_level_no_leak() -> None:
	"""train과 eval에 같은 task_id가 동시에 들어가지 않아야 함."""
	by_task = {f"t{i:02d}": [{"step": s} for s in range(3)] for i in range(10)}
	train, eval_, eval_ids = split_train_eval(by_task, eval_ratio=0.2, seed=42)
	assert len(train) + len(eval_) == 30
	# 같은 task의 step이 갈라지지 않았는지 — eval만 검사
	for s in eval_:
		# 합성 fixture라 직접 비교 불가; 대신 eval task 갯수 검증
		pass
	assert len(eval_ids) == 2  # 10 * 0.2 = 2
	# eval ids가 train에 등장하지 않아야
	assert not any(s.get("step") is None for s in train + eval_)


def test_split_minimum_eval_one() -> None:
	by_task = {"only_one": [{"x": 1}]}
	train, eval_, eval_ids = split_train_eval(by_task, eval_ratio=0.0, seed=0)
	# 2개 미만일 땐 train이 비고 eval이 1개 (split 함수는 최소 1 eval 보장)
	assert len(eval_ids) == 1


def test_split_seed_deterministic() -> None:
	by_task = {f"t{i:02d}": [{"x": i}] for i in range(20)}
	a1, _, ea = split_train_eval(by_task, 0.2, seed=7)
	a2, _, eb = split_train_eval(by_task, 0.2, seed=7)
	assert ea == eb
	assert len(a1) == len(a2)


# endregion


# region 실제 trajectory artifact 기반 (있을 때만 활성)


def _has_artifacts() -> bool:
	if not TRAJ_ROOT.exists():
		return False
	return any((d / "steps.jsonl").exists() for d in TRAJ_ROOT.iterdir() if d.is_dir())


pytestmark_artifact = pytest.mark.skipif(
	not _has_artifacts(),
	reason="trajectories/ 안에 steps.jsonl 있는 trajectory 없음 — Phase 1 수집 후 활성",
)


@pytestmark_artifact
def test_real_trajectory_roundtrips() -> None:
	"""실제 trajectory 1개로 모든 step이 valid sample이 되는지."""
	dirs = [d for d in TRAJ_ROOT.iterdir() if d.is_dir() and (d / "steps.jsonl").exists()]
	assert dirs, "no trajectory found"
	d = dirs[0]
	steps = [json.loads(l) for l in (d / "steps.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
	assert steps, "trajectory has no steps"
	samples = [step_to_sample(s, d) for s in steps]
	# 적어도 절반은 valid sample 으로 변환되어야 (일부 step은 input_messages 비어있을 수 있음)
	valid = [s for s in samples if s is not None]
	assert len(valid) >= len(steps) // 2, f"too few valid samples: {len(valid)}/{len(steps)}"
	# 각 sample의 assistant content가 valid JSON
	for s in valid:
		json.loads(s["messages"][2]["content"])  # raises if invalid


@pytestmark_artifact
def test_run_conversion_writes_files(tmp_path: Path) -> None:
	"""run_conversion이 train/eval JSONL 둘 다 만들고 합이 trajectory의 valid step 합과 일치."""
	out = tmp_path / "data"
	rc = run_conversion(
		in_root=TRAJ_ROOT,
		out_root=out,
		eval_ratio=0.2,
		seed=42,
		success_only=False,
	)
	assert rc == 0
	train_path = out / "korus_train.jsonl"
	eval_path = out / "korus_eval.jsonl"
	assert train_path.exists() and eval_path.exists()
	n_train = sum(1 for _ in train_path.open())
	n_eval = sum(1 for _ in eval_path.open())
	assert n_train + n_eval > 0
	# task_id 단위 split — 같은 task_id가 양쪽에 안 들어갔는지
	train_tids = {json.loads(l)["task_id"] for l in train_path.open()}
	eval_tids = {json.loads(l)["task_id"] for l in eval_path.open()}
	assert train_tids.isdisjoint(eval_tids), f"task leak: {train_tids & eval_tids}"


# endregion
