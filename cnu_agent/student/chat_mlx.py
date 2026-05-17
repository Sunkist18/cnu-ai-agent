"""browser-use BaseChatModel wrapper for MLX-VLM (Mac Apple Silicon inference).

Same shape as ChatClaudeCode — accepts list[BaseMessage], optional output_format,
returns ChatInvokeCompletion. 다만 subprocess 안 띄우고 in-process MLX model로
직접 추론.

쓰임:
- Mac (M1/M2/M3/M4 + 64GB+ unified memory) 에서 fine-tuned 또는 base Qwen2.5-VL
  추론
- Phase 4 실 KORUS task — browser-use Agent에 끼워서 사용
- Optional LoRA adapter (PEFT format)는 `adapter_path` 로 — 단 MLX format 변환
  완료된 것만 (HF PEFT 그대로는 안 됨, 사전 변환 필요)

Run smoke:
  python -c "
  from cnu_agent.student.chat_mlx import ChatMLX
  from browser_use.llm.messages import SystemMessage, UserMessage
  import asyncio
  llm = ChatMLX()
  print(asyncio.run(llm.ainvoke([
      SystemMessage(content='You are helpful.'),
      UserMessage(content='Say hi in Korean.'),
  ])).completion)
  "
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
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
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def _extract_json(text: str) -> str:
	"""Pull last JSON object/array out of text (fenced or bare)."""
	for chunk in reversed(_JSON_FENCE_RE.findall(text)):
		s = chunk.strip()
		if s.startswith(("{", "[")):
			return s
	# bare scan
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
		raise ValueError(f"No JSON in: {text[:300]!r}")
	depth = 0
	for j in range(end - 1, -1, -1):
		ch = text[j]
		if ch == "}":
			depth += 1
		elif ch == "{":
			depth -= 1
			if depth == 0:
				return text[j:end]
	raise ValueError(f"Unbalanced JSON: {text[:300]!r}")


def _save_temp_image(data_url: str) -> str:
	"""data:image/...;base64,... → /tmp/...path"""
	header, data = data_url.split(",", 1)
	ext = "png"
	if "image/" in header:
		ext = header.split("image/")[-1].split(";")[0]
	tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False, prefix="mlx_img_")
	tmp.write(base64.b64decode(data))
	tmp.close()
	return tmp.name


def _serialize_for_mlx(
	messages: list[BaseMessage],
) -> tuple[list[dict[str, Any]], list[str], str]:
	"""Convert browser-use BaseMessage list → MLX chat messages + image paths.

	Returns:
	    mlx_messages: list of {"role": ..., "content": [{"type":"image"|"text", ...}]}
	    image_paths: list of file paths (extracted from ContentPartImageParam)
	    system_text: concatenated system prompt
	"""
	mlx_msgs: list[dict] = []
	image_paths: list[str] = []
	system_chunks: list[str] = []

	for m in messages:
		role = m.role
		content = m.content
		if isinstance(m, SystemMessage):
			text = m.text
			if text:
				system_chunks.append(text)
			continue

		# Build content list
		if isinstance(content, str):
			parts = [{"type": "text", "text": content}] if content else []
		elif isinstance(content, list):
			parts = []
			for p in content:
				if isinstance(p, ContentPartTextParam):
					if p.text:
						parts.append({"type": "text", "text": p.text})
				elif isinstance(p, ContentPartImageParam):
					url = p.image_url.url
					if url.startswith("data:"):
						path = _save_temp_image(url)
					elif url.startswith("file://"):
						path = url[7:]
					else:
						path = url
					image_paths.append(path)
					parts.append({"type": "image"})
		else:
			parts = []

		if parts:
			mlx_msgs.append({"role": role, "content": parts})

	return mlx_msgs, image_paths, "\n\n".join(system_chunks)


@dataclass
class ChatMLX(BaseChatModel):
	"""browser-use LLM provider via MLX-VLM (Apple Silicon, in-process).

	기본은 mlx-community 사전 양자화 32B 4bit. ckpt의 LoRA adapter를 직접 적용하려면
	`adapter_path` 지정 — 단 MLX format이어야 함 (PEFT HF format은 사전 변환 필요).

	Synchronous mlx model.generate는 thread pool에서 await으로 감쌈.
	"""

	model: str = "mlx-community/Qwen2.5-VL-32B-Instruct-4bit"
	adapter_path: str | None = None
	max_tokens: int = 1024
	temperature: float = 0.0

	# internal lazy state — 첫 ainvoke 시 load (모델 로딩 ~30s, 한 번만)
	_loaded: dict = field(default_factory=dict)

	@property
	def provider(self) -> str:
		return "mlx_vlm"

	@property
	def name(self) -> str:
		return f"mlx/{self.model}" + (f"+lora={Path(self.adapter_path).name}" if self.adapter_path else "")

	def _ensure_loaded(self) -> None:
		if self._loaded.get("model") is not None:
			return
		from mlx_vlm import load

		print(f"[ChatMLX] Loading {self.model} (adapter={self.adapter_path}) ...", file=sys.stderr)
		model_obj, processor = load(self.model, adapter_path=self.adapter_path)
		self._loaded["model"] = model_obj
		self._loaded["processor"] = processor
		# Try to access config (used by apply_chat_template)
		self._loaded["config"] = getattr(model_obj, "config", {}) or {}
		print(f"[ChatMLX] Loaded.", file=sys.stderr)

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
		self._ensure_loaded()
		from mlx_vlm import apply_chat_template, generate

		mlx_msgs, image_paths, system_text = _serialize_for_mlx(messages)

		# Inject JSON schema for structured output (output_format)
		if output_format is not None:
			schema = output_format.model_json_schema()
			schema_blob = json.dumps(schema, ensure_ascii=False)
			schema_instr = (
				"Respond with a SINGLE JSON object exactly matching this schema. "
				"Do not call tools, do not add prose or fences, output ONLY the JSON.\n\n"
				f"JSON Schema:\n{schema_blob}"
			)
			system_text = f"{system_text}\n\n{schema_instr}".strip() if system_text else schema_instr

		# Prepend system as first message in MLX format (mlx_vlm가 system은 별도 필드로 안 받음)
		if system_text:
			mlx_msgs = [{"role": "system", "content": [{"type": "text", "text": system_text}]}] + mlx_msgs

		processor = self._loaded["processor"]
		config = self._loaded["config"]
		model_obj = self._loaded["model"]

		# Build prompt string via processor's chat template
		prompt = apply_chat_template(
			processor,
			config,
			mlx_msgs,
			add_generation_prompt=True,
			num_images=len(image_paths),
		)

		# MLX streams are thread-local — run_in_executor (worker thread) 사용 시
		# "There is no Stream(gpu, 1) in current thread" 에러 발생. 동기 직접 호출.
		# generate가 CPU/GPU bound이고 매 step 한 번이라 event loop 잠시 block 무관.
		try:
			result = generate(
				model_obj,
				processor,
				prompt,
				image=image_paths if image_paths else None,
				max_tokens=self.max_tokens,
				temperature=self.temperature,
				verbose=False,
			)
		except Exception as e:  # noqa: BLE001
			raise ModelProviderError(
				message=f"MLX-VLM generate failed: {type(e).__name__}: {e}",
				model=self.name,
			) from e

		# Extract text from GenerationResult
		text = getattr(result, "text", None) or str(result)
		# Usage info if available
		usage = None
		try:
			pt = getattr(result, "prompt_tokens", None)
			ct = getattr(result, "generation_tokens", None) or getattr(result, "completion_tokens", None)
			if pt is not None and ct is not None:
				usage = ChatInvokeUsage(
					prompt_tokens=int(pt),
					prompt_cached_tokens=None,
					prompt_cache_creation_tokens=None,
					prompt_image_tokens=None,
					completion_tokens=int(ct),
					total_tokens=int(pt) + int(ct),
				)
		except Exception:
			usage = None

		stop_reason = getattr(result, "finish_reason", None) or getattr(result, "stop_reason", None)

		if output_format is None:
			return ChatInvokeCompletion(completion=text.strip(), usage=usage, stop_reason=stop_reason)

		# Parse structured output
		try:
			blob = _extract_json(text)
			completion = output_format.model_validate_json(blob)
		except Exception as e:  # noqa: BLE001
			raise ModelProviderError(
				message=(
					f"Failed to parse {output_format.__name__}: {e}. Raw: {text[:500]!r}"
				),
				model=self.name,
			) from e

		return ChatInvokeCompletion(completion=completion, usage=usage, stop_reason=stop_reason)


__all__ = ["ChatMLX"]
