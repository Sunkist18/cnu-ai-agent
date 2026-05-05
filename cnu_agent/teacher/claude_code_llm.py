"""Wraps the Claude Agent SDK as a browser-use BaseChatModel.

Implementation guide: see `PLAN.md` §1 ("`cnu_agent/teacher/claude_code_llm.py`").

Key points:
- browser-use Protocol: `async def ainvoke(messages, output_format) -> ChatInvokeCompletion[T]`
- Single-turn structured output: force `allowed_tools=[]`, inject JSON schema into system prompt.
- claude-agent-sdk: `from claude_agent_sdk import query, ClaudeAgentOptions`
- Reference impl to mirror: `browser_use/llm/anthropic/chat.py`
"""

from __future__ import annotations

from typing import Any, TypeVar

from browser_use.llm.base import BaseChatModel
from browser_use.llm.messages import BaseMessage
from browser_use.llm.views import ChatInvokeCompletion
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ChatClaudeCode(BaseChatModel):
	"""browser-use LLM provider that routes through Claude Agent SDK (headless)."""

	model: str = "claude-sonnet-4-5"
	bare: bool = True  # `--bare`: skip hooks/skills/CLAUDE.md for faster startup

	async def ainvoke(
		self,
		messages: list[BaseMessage],
		output_format: type[T] | None = None,
		**kwargs: Any,
	) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
		raise NotImplementedError("Implement per PLAN.md §1")
