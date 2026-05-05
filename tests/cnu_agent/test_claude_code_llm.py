"""Unit tests for ChatClaudeCode (BaseChatModel Protocol 구현 검증).

See `PLAN.md` "검증 자동화" 섹션.

테스트 핵심:
1. 단순 Pydantic schema (`class Foo(BaseModel): x: int`)로 ainvoke 호출 → valid 결과
2. ChatInvokeCompletion 반환형 (completion, usage 필드) 형식 일치
3. allowed_tools=[] 강제 (tool-loop이 안 돌아야 함)

Run: `uv run pytest -vxs tests/cnu_agent/test_claude_code_llm.py`
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Implement per PLAN.md §1 — needs claude-agent-sdk auth")
async def test_ainvoke_returns_valid_pydantic_completion() -> None:
	raise NotImplementedError
