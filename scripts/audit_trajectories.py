"""Phase 1 trajectory audit — false-positive 정리 + 진짜 mutating 클릭 검사.

수집 시점의 mutating-guard는 action_dump 텍스트만 봤는데, 실제 클릭된 element label은
history.json의 `state.interacted_element[*].ax_name`/attributes/node_value에서 확인 가능.
이 정보가 ground truth.

수행:
1. 모든 trajectories/<task_id>/history.json 순회
2. 각 step의 interacted_element 검사 — ax_name·node_value·attribute에 mutating button label
   매치되면 진짜 mutating 클릭으로 보고
3. _MUTATING_BLOCKED.json 파일을 새 검사 기준으로 갱신:
   - 기존 false-positive(observation·search·placeholder만 잡힌 거)는 파일 삭제
   - 진짜 hit 있으면 파일 유지 + 사유 명시
4. 종합 리포트 출력

Run: `python scripts/audit_trajectories.py`
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRAJ_ROOT = REPO_ROOT / "trajectories"

# 새 mutating button regex — collect.py와 동기화
import re

KOREAN_MUTATING_BUTTON_RE = re.compile(
	r"(승인|반려|상신|제출|저장(?![된되함소])|삭제|회수|재상신|결재완료|발송|전송)"
)
MUTATING_ACTION_NAMES = {"submit", "submit_form", "approve", "reject", "delete", "publish", "send_form"}


def _audit_step_action(action_dump: dict) -> list[str]:
	"""Same logic as collect._scan_mutating (kept in sync)."""
	hits: list[str] = []
	read_only = {
		"done", "extract", "extract_structured_data", "search_page", "send_keys", "input",
		"navigate", "go_back", "scroll", "wait", "switch", "switch_tab", "hover", "screenshot",
	}
	for action_name, params in action_dump.items():
		if action_name in MUTATING_ACTION_NAMES:
			hits.append(f"action_name='{action_name}' params={json.dumps(params, ensure_ascii=False)[:120]}")
			continue
		if action_name in read_only:
			continue
		if action_name == "click":
			text_blob = f"{params.get('description') or ''}|{params.get('text') or ''}"
			m = KOREAN_MUTATING_BUTTON_RE.search(text_blob)
			if m:
				hits.append(f"click button label='{m.group(0)}' in {text_blob[:120]}")
	return hits


def _audit_interacted_element(ie: dict | None) -> list[str]:
	"""실제 클릭된 element의 label에 mutating keyword가 있는지 검사."""
	if not ie:
		return []
	# label 후보 모음 — accessibility name + visible text + attribute values
	parts = []
	if ie.get("ax_name"):
		parts.append(str(ie["ax_name"]))
	if ie.get("node_value"):
		parts.append(str(ie["node_value"]))
	attrs = ie.get("attributes") or {}
	for key in ("aria-label", "title", "alt", "value", "placeholder"):
		if attrs.get(key):
			parts.append(str(attrs[key]))
	blob = " | ".join(parts)
	hits: list[str] = []
	m = KOREAN_MUTATING_BUTTON_RE.search(blob)
	if m:
		# 클릭한 element가 mutating button — but only if node is button/link
		node = (ie.get("node_name") or "").upper()
		hits.append(f"clicked <{node}> label='{m.group(0)}' in {blob[:120]}")
	return hits


def audit_one(task_dir: Path) -> dict:
	hist_path = task_dir / "history.json"
	if not hist_path.exists():
		return {"task_id": task_dir.name, "status": "no_history"}

	hist = json.loads(hist_path.read_text(encoding="utf-8"))
	steps = hist.get("history", [])
	action_hits: list[dict] = []
	element_hits: list[dict] = []

	for i, step in enumerate(steps):
		# action 검사
		mo = step.get("model_output") or {}
		for j, act in enumerate(mo.get("action") or []):
			a_hits = _audit_step_action(act)
			for h in a_hits:
				action_hits.append({"step": i + 1, "action_idx": j, "hit": h})

		# interacted_element 검사
		state = step.get("state") or {}
		for j, ie in enumerate(state.get("interacted_element") or []):
			ie_hits = _audit_interacted_element(ie)
			for h in ie_hits:
				element_hits.append({"step": i + 1, "elem_idx": j, "hit": h})

	return {
		"task_id": task_dir.name,
		"status": "ok",
		"n_steps": len(steps),
		"action_hits": action_hits,
		"element_hits": element_hits,
		"true_mutating": bool(action_hits or element_hits),
	}


def main() -> int:
	if not TRAJ_ROOT.exists():
		print("trajectories/ 없음", file=sys.stderr)
		return 2

	results = []
	for task_dir in sorted(TRAJ_ROOT.iterdir()):
		if not task_dir.is_dir():
			continue
		r = audit_one(task_dir)
		if r["status"] == "no_history":
			continue
		results.append(r)

	# Old _MUTATING_BLOCKED.json 정리
	cleaned = 0
	kept = 0
	for r in results:
		flag_path = TRAJ_ROOT / r["task_id"] / "_MUTATING_BLOCKED.json"
		if flag_path.exists():
			if r["true_mutating"]:
				kept += 1
			else:
				flag_path.unlink()
				cleaned += 1

	# 진짜 mutating trajectory 별도 파일로 표시
	for r in results:
		if r["true_mutating"]:
			audit_path = TRAJ_ROOT / r["task_id"] / "_MUTATING_AUDIT.json"
			audit_path.write_text(
				json.dumps(
					{"action_hits": r["action_hits"], "element_hits": r["element_hits"]},
					indent=2,
					ensure_ascii=False,
				),
				encoding="utf-8",
			)

	# 종합 리포트
	total = len(results)
	true_mut = sum(1 for r in results if r["true_mutating"])
	total_steps = sum(r["n_steps"] for r in results)

	print(f"=== Trajectory audit ===")
	print(f"  trajectories: {total}")
	print(f"  total steps:  {total_steps}")
	print(f"  진짜 mutating: {true_mut}/{total}")
	print(f"  false-positive 정리됨: {cleaned}")
	print(f"  유지된 _MUTATING_BLOCKED: {kept}")

	if true_mut > 0:
		print("\n진짜 mutating trajectory:")
		for r in results:
			if r["true_mutating"]:
				print(f"  - {r['task_id']}: action_hits={len(r['action_hits'])} element_hits={len(r['element_hits'])}")
				for h in r["action_hits"][:3]:
					print(f"      step {h['step']}: {h['hit']}")
				for h in r["element_hits"][:3]:
					print(f"      step {h['step']}: {h['hit']}")

	# 통계
	steps_dist = Counter()
	for r in results:
		bucket = (r["n_steps"] // 5) * 5
		steps_dist[bucket] += 1
	print("\n step 수 분포:")
	for bucket in sorted(steps_dist):
		print(f"  {bucket:3d}-{bucket+4:3d}: {'#' * steps_dist[bucket]} ({steps_dist[bucket]})")

	return 0 if true_mut == 0 else 1


if __name__ == "__main__":
	sys.exit(main())
