"""Unit tests for trajectory → Qwen ChatML 변환.

See `PLAN.md` §5 + "검증 자동화" 섹션.

테스트 핵심:
1. sample steps.jsonl 1개 → ChatML 1개로 round-trip
2. messages 구조 검증 (system / user[image+text] / assistant)
3. assistant content가 valid AgentOutput JSON으로 다시 parse 가능
4. 이미지 path가 절대 경로로 정상화

Run: `uv run pytest -vxs tests/cnu_agent/test_trajectory_conversion.py`
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Implement per PLAN.md §5")
def test_step_to_chatml_roundtrip() -> None:
	raise NotImplementedError
