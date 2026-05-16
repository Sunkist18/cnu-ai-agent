"""Schema validation for seeds.json + tasks/korus_100.json (PLAN.md Verification Phase 0b).

검증 핵심:
1. discovery/seeds.json (있으면) — 모든 항목이 Seed schema에 valid
2. tasks/korus_100.json (있으면) — 모든 항목이 Task schema에 valid
3. sensitive_keys != [] 인 task는 task 텍스트에 {{...}} placeholder가 실제로 들어 있는지
   정규식 검증 + 선언된 키 일치 검증

artifact 파일이 없으면 (아직 생성 전이면) skip.

Run: `uv run pytest -vxs tests/cnu_agent/test_seeds_and_tasks.py`
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cnu_agent.teacher.discover import Seed
from cnu_agent.teacher.paraphrase import PLACEHOLDER_RE, Task

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDS_PATH = REPO_ROOT / "discovery" / "seeds.json"
SEEDS_CURATED_PATH = REPO_ROOT / "discovery" / "seeds_curated.json"
TASKS_PATH = REPO_ROOT / "tasks" / "korus_100.json"

VALID_CATEGORIES = {
	"결재작성",
	"결재처리",
	"문서조회",
	"첨부파일",
	"결재선설정",
	"환경설정",
	# v2 신규 (survey-driven)
	"공문처리",
	"정산",
}


def _load_seeds(path: Path) -> list[dict]:
	if not path.exists():
		pytest.skip(f"{path.name} 아직 생성 전 — discover.py 실행 후 다시 테스트")
	return json.loads(path.read_text(encoding="utf-8"))


def _load_tasks(path: Path) -> list[dict]:
	if not path.exists():
		pytest.skip(f"{path.name} 아직 생성 전 — paraphrase.py 실행 후 다시 테스트")
	return json.loads(path.read_text(encoding="utf-8"))


# region seeds.json


def test_seeds_schema_valid() -> None:
	seeds_raw = _load_seeds(SEEDS_PATH)
	assert len(seeds_raw) >= 20, f"seed 후보 너무 적음: {len(seeds_raw)} (목표 30~40)"
	for s in seeds_raw:
		Seed.model_validate(s)  # raises on schema violation


def test_seeds_unique_ids() -> None:
	seeds_raw = _load_seeds(SEEDS_PATH)
	ids = [s["id"] for s in seeds_raw]
	assert len(ids) == len(set(ids)), f"중복 id 존재: {[i for i in ids if ids.count(i) > 1]}"


def test_seeds_id_snake_case() -> None:
	seeds_raw = _load_seeds(SEEDS_PATH)
	pat = re.compile(r"^[a-z][a-z0-9_]*$")
	for s in seeds_raw:
		assert pat.match(s["id"]), f"id가 snake_case 아님: {s['id']!r}"


def test_seeds_category_in_known_set() -> None:
	"""카테고리는 가이드된 세트와 다르게 나올 수도 있지만, 80% 이상은 known 세트 안이어야 함."""
	seeds_raw = _load_seeds(SEEDS_PATH)
	known = sum(1 for s in seeds_raw if s["category"] in VALID_CATEGORIES)
	total = len(seeds_raw)
	assert known / total >= 0.8, f"known categories 비율 {known}/{total} — prompt 수정 검토"


def test_seeds_curated_subset_of_seeds() -> None:
	"""seeds_curated.json은 seeds.json의 부분집합이거나 survey-driven 신규 seed (v2+)."""
	if not SEEDS_CURATED_PATH.exists():
		pytest.skip("seeds_curated.json 없음 — 사용자 review 전")
	seeds = {s["id"] for s in _load_seeds(SEEDS_PATH)}
	curated = {s["id"] for s in _load_seeds(SEEDS_CURATED_PATH)}
	# v2부터는 survey-driven 신규 seed (`incoming_*`, `view_or_submit_*`, etc.) 추가됨 — 부분집합 strict 검사 X
	non_subset = curated - seeds
	if non_subset:
		# 신규 seed가 v2 패턴 따르는지만 확인
		assert all(
			isinstance(sid, str) and sid.replace("_", "").isalnum()
			for sid in non_subset
		), f"신규 seed id format 위반: {non_subset}"
	assert len(curated) <= 30, f"curated가 너무 많음: {len(curated)} > 30"


# endregion


# region tasks/korus_100.json


def test_tasks_schema_valid() -> None:
	tasks_raw = _load_tasks(TASKS_PATH)
	# v0 24 seed × 4 = 96, v1 24 × 4 = 96, v2 15 × 4 = 60. seed 수에 따라 범위 다양.
	assert 50 <= len(tasks_raw) <= 130, f"task 수 50~130 밖: {len(tasks_raw)}"
	for t in tasks_raw:
		Task.model_validate(t)


def test_tasks_unique_ids() -> None:
	tasks_raw = _load_tasks(TASKS_PATH)
	ids = [t["id"] for t in tasks_raw]
	assert len(ids) == len(set(ids))


def test_tasks_seed_id_resolves() -> None:
	"""모든 task.seed_id는 seeds_curated.json (또는 seeds.json)의 id에 존재해야 함."""
	tasks_raw = _load_tasks(TASKS_PATH)
	source_path = SEEDS_CURATED_PATH if SEEDS_CURATED_PATH.exists() else SEEDS_PATH
	if not source_path.exists():
		pytest.skip("seeds 파일 없음")
	seed_ids = {s["id"] for s in _load_seeds(source_path)}
	for t in tasks_raw:
		assert t["seed_id"] in seed_ids, f"task {t['id']}의 seed_id {t['seed_id']!r} 부재"


def test_tasks_sensitive_keys_match_placeholders() -> None:
	"""sensitive_keys != []인 task는 task 텍스트의 {{...}} 토큰 집합과 정확히 일치."""
	tasks_raw = _load_tasks(TASKS_PATH)
	mismatches: list[str] = []
	for t in tasks_raw:
		declared = set(t["sensitive_keys"])
		found = {tok[2:-2] for tok in PLACEHOLDER_RE.findall(t["task"])}
		if declared != found:
			mismatches.append(f"{t['id']}: declared={sorted(declared)} found={sorted(found)}")
	assert not mismatches, "placeholder 불일치:\n  " + "\n  ".join(mismatches[:10])


def test_tasks_no_student_persona_words() -> None:
	"""페르소나는 교수·조교·공무원이라 학생 self-reference 표현이 없어야 함.

	주의: 단순히 "학생" 단어가 task 텍스트에 등장하는 건 OK ("학생 오리엔테이션을 위한
	대강당 대여" 같은 케이스). 실제 위반은 화자가 자기를 학생으로 지칭하는 패턴.
	"""
	tasks_raw = _load_tasks(TASKS_PATH)
	# 학생만이 쓰는 강한 단서들 (사번/교번 시스템에선 안 나옴)
	hard_terms = ["학번", "수강신청", "수강 신청", "교수님께"]
	# 자기를 학생으로 지칭하는 self-reference 패턴
	self_ref_patterns = [
		re.compile(r"(?:내가|저는?|제가)\s*학생"),
		re.compile(r"학생\s*으로서"),
		re.compile(r"학생\s*인데"),
	]
	hits: list[str] = []
	for t in tasks_raw:
		for term in hard_terms:
			if term in t["task"]:
				hits.append(f"{t['id']}: hard term '{term}' in {t['task']!r}")
		for pat in self_ref_patterns:
			if pat.search(t["task"]):
				hits.append(f"{t['id']}: self-ref '{pat.pattern}' in {t['task']!r}")
	assert not hits, "학생 페르소나 위반:\n  " + "\n  ".join(hits[:10])


# endregion
