"""Wraps the Claude Agent SDK as a browser-use BaseChatModel.

Implementation guide: PLAN.md §1 ("`cnu_agent/teacher/claude_code_llm.py`").

Single-shot ainvoke pattern:
- system messages → ClaudeAgentOptions.system_prompt (string override)
- non-system messages → folded into a single streamed user turn (content blocks)
- output_format → SDK's --json-schema flag (ResultMessage.structured_output) plus
  a system-prompt instruction; we parse from the final text as a fallback
- tools=[] / allowed_tools=[] / skills=None / setting_sources=None to keep the
  subprocess as a pure text generator (no tool loop, no CLAUDE.md/skills bleed-in)

Reference: browser_use/llm/anthropic/{chat,serializer}.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, TypeVar, overload

from browser_use.llm.base import BaseChatModel
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import (
	AssistantMessage,
	BaseMessage,
	ContentPartImageParam,
	ContentPartTextParam,
	SystemMessage,
	UserMessage,
)
from browser_use.llm.views import ChatInvokeCompletion, ChatInvokeUsage
from claude_agent_sdk import (
	AssistantMessage as SDKAssistantMessage,
)
from claude_agent_sdk import (
	ClaudeAgentOptions,
)
from claude_agent_sdk import (
	ResultMessage as SDKResultMessage,
)
from claude_agent_sdk import (
	TextBlock as SDKTextBlock,
)
from claude_agent_sdk import (
	query as sdk_query,
)
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def _split_data_url(url: str) -> tuple[str, str]:
	if not url.startswith("data:"):
		raise ValueError("ChatClaudeCode only supports inline base64 data: URLs for images")
	header, data = url.split(",", 1)
	media_type = header.split(";")[0].replace("data:", "") or "image/png"
	if media_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
		media_type = "image/png"
	return media_type, data


def _serialize_messages(messages: list[BaseMessage]) -> tuple[list[dict[str, Any]], str]:
	"""Fold messages into (single-turn content blocks, concatenated system prompt).

	Non-system turns are serialized as Anthropic content blocks (text + image)
	prefixed with a `[Role]` label so the model can still see who said what when
	the history is collapsed into one user turn.
	"""
	system_chunks: list[str] = []
	blocks: list[dict[str, Any]] = []

	for msg in messages:
		if isinstance(msg, SystemMessage):
			text = msg.text
			if text:
				system_chunks.append(text)
			continue

		if isinstance(msg, AssistantMessage):
			label = "Assistant"
		elif isinstance(msg, UserMessage):
			label = "User"
		else:
			label = msg.role.title()

		content = msg.content
		if content is None:
			continue
		if isinstance(content, str):
			if content:
				blocks.append({"type": "text", "text": f"[{label}]\n{content}"})
			continue

		# list of parts
		blocks.append({"type": "text", "text": f"[{label}]"})
		for part in content:
			if isinstance(part, ContentPartTextParam):
				if part.text:
					blocks.append({"type": "text", "text": part.text})
			elif isinstance(part, ContentPartImageParam):
				media_type, data = _split_data_url(part.image_url.url)
				blocks.append(
					{
						"type": "image",
						"source": {"type": "base64", "media_type": media_type, "data": data},
					}
				)

	if not blocks:
		blocks.append({"type": "text", "text": "Proceed."})

	return blocks, "\n\n".join(system_chunks)


def _extract_json(text: str) -> str:
	"""Pull the last JSON object/array out of `text`, fenced or bare."""
	for chunk in reversed(_JSON_FENCE_RE.findall(text)):
		stripped = chunk.strip()
		if stripped.startswith(("{", "[")):
			return stripped

	# No fence — find last balanced top-level {...}
	end = -1
	depth = 0
	for i, ch in enumerate(text):
		if ch == "{":
			depth += 1
		elif ch == "}":
			depth -= 1
			if depth == 0:
				end = i + 1
	if end == -1:
		raise ValueError(f"No JSON object found in model output: {text[:300]!r}")

	depth = 0
	for j in range(end - 1, -1, -1):
		ch = text[j]
		if ch == "}":
			depth += 1
		elif ch == "{":
			depth -= 1
			if depth == 0:
				return text[j:end]
	raise ValueError(f"Could not balance JSON braces in model output: {text[:300]!r}")


def _build_usage(usage: dict[str, Any] | None) -> ChatInvokeUsage | None:
	if not usage:
		return None
	# Anthropic-shape: {input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens}
	input_tokens = int(usage.get("input_tokens", 0) or 0)
	output_tokens = int(usage.get("output_tokens", 0) or 0)
	cached = usage.get("cache_read_input_tokens")
	cache_create = usage.get("cache_creation_input_tokens")
	cached_int = int(cached) if cached is not None else None
	return ChatInvokeUsage(
		prompt_tokens=input_tokens + (cached_int or 0),
		prompt_cached_tokens=cached_int,
		prompt_cache_creation_tokens=int(cache_create) if cache_create is not None else None,
		prompt_image_tokens=None,
		completion_tokens=output_tokens,
		total_tokens=input_tokens + output_tokens + (cached_int or 0),
	)


@dataclass
class ChatClaudeCode(BaseChatModel):
	"""browser-use LLM provider that routes through Claude Agent SDK (headless).

	Notes:
	- `bare=True` adds the CLI `--bare` flag (faster startup, skips CLAUDE.md /
	  hooks / skills) but disables OAuth/keychain reads — only safe when
	  `ANTHROPIC_API_KEY` is set. Default is False so Claude Max OAuth keeps
	  working out of the box.
	- `tools=[]` is forced so the subprocess never enters a tool loop, matching
	  the BaseChatModel single-turn contract.
	"""

	model: str = "claude-sonnet-4-5"
	bare: bool = False

	@property
	def provider(self) -> str:
		return "claude_code"

	@property
	def name(self) -> str:
		return f"claude-code/{self.model}"

	def _build_options(
		self,
		system_prompt: str,
		output_format: type[T] | None,
	) -> tuple[ClaudeAgentOptions, dict[str, Any] | None]:
		schema_dict: dict[str, Any] | None = None
		final_system = system_prompt

		if output_format is not None:
			schema = output_format.model_json_schema()
			schema_dict = {"type": "json_schema", "schema": schema}
			schema_blob = json.dumps(schema, ensure_ascii=False)
			instruction = (
				"Respond with a SINGLE JSON object that exactly matches the following JSON Schema. "
				"Do NOT call any tools. Do NOT include explanation, prose, or extra fields — output ONLY the JSON object.\n\n"
				f"JSON Schema:\n{schema_blob}"
			)
			final_system = f"{system_prompt}\n\n{instruction}".strip() if system_prompt else instruction

		extra_args: dict[str, str | None] = {}
		if self.bare:
			extra_args["bare"] = None

		options = ClaudeAgentOptions(
			model=self.model,
			tools=[],  # CLI: --tools "" → all built-in tools disabled
			allowed_tools=[],
			disallowed_tools=[],
			system_prompt=final_system or None,
			output_format=schema_dict,
			extra_args=extra_args,
		)
		return options, schema_dict

	@overload
	async def ainvoke(
		self, messages: list[BaseMessage], output_format: None = None, **kwargs: Any
	) -> ChatInvokeCompletion[str]: ...

	@overload
	async def ainvoke(
		self, messages: list[BaseMessage], output_format: type[T], **kwargs: Any
	) -> ChatInvokeCompletion[T]: ...

	async def ainvoke(
		self,
		messages: list[BaseMessage],
		output_format: type[T] | None = None,
		**kwargs: Any,
	) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
		blocks, system_prompt = _serialize_messages(messages)
		options, _ = self._build_options(system_prompt, output_format)

		async def _stream() -> AsyncIterator[dict[str, Any]]:
			yield {
				"type": "user",
				"session_id": "",
				"message": {"role": "user", "content": blocks},
				"parent_tool_use_id": None,
			}

		text_pieces: list[str] = []
		usage_dict: dict[str, Any] | None = None
		structured_output: Any = None
		stop_reason: str | None = None

		try:
			async for sdk_msg in sdk_query(prompt=_stream(), options=options):
				if isinstance(sdk_msg, SDKAssistantMessage):
					for block in sdk_msg.content:
						if isinstance(block, SDKTextBlock):
							text_pieces.append(block.text)
					if sdk_msg.usage:
						usage_dict = sdk_msg.usage
					if sdk_msg.stop_reason:
						stop_reason = sdk_msg.stop_reason
					if sdk_msg.error:
						raise ModelProviderError(
							message=f"Claude Agent SDK assistant error: {sdk_msg.error}",
							model=self.name,
						)
				elif isinstance(sdk_msg, SDKResultMessage):
					if sdk_msg.is_error:
						raise ModelProviderError(
							message=(
								f"Claude Agent SDK result error: subtype={sdk_msg.subtype} "
								f"errors={sdk_msg.errors}"
							),
							model=self.name,
						)
					if sdk_msg.usage and not usage_dict:
						usage_dict = sdk_msg.usage
					if sdk_msg.stop_reason and not stop_reason:
						stop_reason = sdk_msg.stop_reason
					if sdk_msg.structured_output is not None:
						structured_output = sdk_msg.structured_output
					if sdk_msg.result and not text_pieces:
						text_pieces.append(sdk_msg.result)
		except ModelProviderError:
			raise
		except Exception as e:
			raise ModelProviderError(
				message=f"Claude Agent SDK call failed: {e}", model=self.name
			) from e

		usage = _build_usage(usage_dict)
		full_text = "".join(text_pieces).strip()

		if output_format is None:
			return ChatInvokeCompletion(completion=full_text, usage=usage, stop_reason=stop_reason)

		# Prefer SDK-validated structured_output, fall back to extracting from text.
		if structured_output is not None:
			try:
				return ChatInvokeCompletion(
					completion=output_format.model_validate(structured_output),
					usage=usage,
					stop_reason=stop_reason,
				)
			except Exception:
				pass

		try:
			blob = _extract_json(full_text)
			completion = output_format.model_validate_json(blob)
		except Exception as e:
			raise ModelProviderError(
				message=(
					f"Failed to parse {output_format.__name__} from Claude output: {e}. "
					f"Raw text: {full_text[:500]!r}"
				),
				model=self.name,
			) from e

		return ChatInvokeCompletion(completion=completion, usage=usage, stop_reason=stop_reason)


__all__ = ["ChatClaudeCode"]
