"""Unit tests for ChatClaudeCode (BaseChatModel Protocol 구현 검증).

See `PLAN.md` "검증 자동화" 섹션 + Phase 0a Verification step 1.

테스트 핵심:
1. 단순 Pydantic schema (`class Foo(BaseModel): x: int; reason: str`)로 ainvoke 호출 → valid 결과
2. ChatInvokeCompletion 반환형 (completion, usage 필드) 형식 일치
3. allowed_tools=[] / tools=[] 강제 (tool-loop이 안 돌아야 함) — _build_options 검사로 정적 확인

Run: `uv run pytest -vxs tests/cnu_agent/test_claude_code_llm.py`

NOTE: live tests spawn the Claude Code CLI subprocess — they need either an
authenticated Max session (default) or `ANTHROPIC_API_KEY`.
"""

from __future__ import annotations

import os
import shutil

import pytest
from browser_use.llm.views import ChatInvokeCompletion
from pydantic import BaseModel

from cnu_agent.teacher.claude_code_llm import ChatClaudeCode


class Foo(BaseModel):
	x: int
	reason: str


def _claude_cli_available() -> bool:
	return shutil.which("claude") is not None


pytestmark = pytest.mark.skipif(
	not _claude_cli_available(),
	reason="Claude Code CLI not on PATH; live SDK calls cannot run.",
)


def test_build_options_disables_all_tools_and_injects_schema() -> None:
	"""Static check: tools/allowed_tools are empty and schema lands in --json-schema + system prompt."""
	llm = ChatClaudeCode()
	options, schema_dict = llm._build_options(system_prompt="be terse", output_format=Foo)

	assert options.tools == [], "tools must be the empty list to set CLI --tools \"\""
	assert options.allowed_tools == []
	assert schema_dict is not None and schema_dict["type"] == "json_schema"
	assert schema_dict["schema"]["properties"].keys() >= {"x", "reason"}
	# JSON schema must also be embedded in the system prompt as instruction.
	assert isinstance(options.system_prompt, str)
	assert "JSON Schema" in options.system_prompt
	assert "be terse" in options.system_prompt


def test_build_options_no_output_format() -> None:
	llm = ChatClaudeCode()
	options, schema_dict = llm._build_options(system_prompt="", output_format=None)
	assert schema_dict is None
	assert options.output_format is None


@pytest.mark.skipif(
	os.environ.get("CNU_SKIP_LIVE_LLM") == "1",
	reason="CNU_SKIP_LIVE_LLM=1 — skipping live Claude Code subprocess test.",
)
async def test_ainvoke_returns_valid_pydantic_completion() -> None:
	"""End-to-end: round-trips a Foo schema through the real Claude Code subprocess."""
	from browser_use.llm.messages import SystemMessage, UserMessage

	llm = ChatClaudeCode()
	messages = [
		SystemMessage(content="You produce JSON exactly matching the requested schema."),
		UserMessage(
			content=(
				"Return JSON with x=42 and reason='because the answer to life, the universe, and everything'. "
				"Output only the JSON object, nothing else."
			)
		),
	]
	result = await llm.ainvoke(messages, output_format=Foo)

	assert isinstance(result, ChatInvokeCompletion)
	assert isinstance(result.completion, Foo)
	assert result.completion.x == 42
	assert isinstance(result.completion.reason, str) and result.completion.reason
