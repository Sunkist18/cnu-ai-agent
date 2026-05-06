"""Phase 3 — Qwen2.5-VL-32B LoRA SFT on B200 (PLAN.md §6).

기본은 LoRA bf16 (B200 191GB 메모리 여유 → quantization 불필요). `--quantize`로
QLoRA 4bit fallback 가능 (메모리 압박 시).

Phase 1 v0 dataset: 234 train + 74 eval samples. multimodal (DOM 텍스트 + screenshot).

Run on B200 (smoke test — 작은 셋 + 1 epoch로 파이프라인 검증):
  python -m cnu_agent.training.qlora_sft \\
    --train data/korus_train.jsonl \\
    --eval  data/korus_eval.jsonl \\
    --out   ckpt/qwen25vl-korus-lora-smoke \\
    --epochs 1 \\
    --max-train-samples 16 \\
    --max-eval-samples 8 \\
    --max-seq 4096

Run on B200 (full v0):
  python -m cnu_agent.training.qlora_sft \\
    --train data/korus_train.jsonl \\
    --eval  data/korus_eval.jsonl \\
    --out   ckpt/qwen25vl-korus-lora \\
    --epochs 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from PIL import Image
from transformers import AutoProcessor, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_jsonl(path: Path) -> list[dict]:
	if not path.exists():
		raise FileNotFoundError(f"{path} not found")
	out = []
	for line in path.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if line:
			out.append(json.loads(line))
	return out


def _resolve_images(messages: list[dict], data_root: Path) -> list[Image.Image]:
	"""Walk message content, load any `{"type":"image","image":"<repo-rel path>"}` from disk."""
	images: list[Image.Image] = []
	for m in messages:
		content = m.get("content")
		if isinstance(content, list):
			for p in content:
				if isinstance(p, dict) and p.get("type") == "image":
					rel = p.get("image", "")
					img_path = data_root / rel
					if img_path.exists():
						try:
							images.append(Image.open(img_path).convert("RGB"))
						except Exception as e:  # noqa: BLE001
							print(f"  ⚠️ failed to open {img_path}: {e}", file=sys.stderr)
	return images


def _strip_image_parts(messages: list[dict]) -> list[dict]:
	"""text-only mode: drop image content parts from each message."""
	out = []
	for m in messages:
		content = m.get("content")
		if isinstance(content, list):
			text_parts = [p for p in content if not (isinstance(p, dict) and p.get("type") == "image")]
			if not text_parts:
				out.append({**m, "content": ""})
			elif len(text_parts) == 1 and isinstance(text_parts[0], dict) and text_parts[0].get("type") == "text":
				# 단일 text 파트면 그냥 string으로 평탄화
				out.append({**m, "content": text_parts[0].get("text", "")})
			else:
				out.append({**m, "content": text_parts})
		else:
			out.append(m)
	return out


def make_collator(processor, data_root: Path, text_only: bool, max_length: int):
	"""Custom data collator for multimodal Qwen2.5-VL SFT.

	Per batch:
	1. apply chat template to each sample's messages → text prompt string
	2. resolve image content parts from disk → list of PIL.Image per sample
	3. processor() to tokenize text + encode images → input_ids, attention_mask, pixel_values, image_grid_thw
	4. labels = input_ids with pad masked to -100
	"""

	def collate(examples: list[dict]) -> dict[str, Any]:
		texts: list[str] = []
		images_per: list[list[Image.Image]] = []
		for ex in examples:
			msgs = ex["messages"]
			if text_only:
				msgs = _strip_image_parts(msgs)
				imgs: list[Image.Image] = []
			else:
				imgs = _resolve_images(msgs, data_root)
			text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
			texts.append(text)
			images_per.append(imgs)

		any_images = any(len(img_list) > 0 for img_list in images_per)
		if text_only or not any_images:
			batch = processor(
				text=texts,
				padding=True,
				truncation=True,
				max_length=max_length,
				return_tensors="pt",
			)
		else:
			# processor는 images 가 None이거나 list[list[Image]] 형식 둘 다 받음
			batch = processor(
				text=texts,
				images=images_per,
				padding=True,
				truncation=True,
				max_length=max_length,
				return_tensors="pt",
			)

		labels = batch["input_ids"].clone()
		pad_id = processor.tokenizer.pad_token_id
		if pad_id is not None:
			labels[labels == pad_id] = -100
		batch["labels"] = labels
		return batch

	return collate


def _load_model_and_processor(base_model: str, quantize: bool, no_flash_attn: bool):
	"""Load Qwen2.5-VL — try the new 2.5-VL class first, fall back to 2-VL if older transformers."""
	processor = AutoProcessor.from_pretrained(base_model, trust_remote_code=True)

	model_kwargs: dict[str, Any] = {
		"torch_dtype": torch.bfloat16,
		"device_map": "auto",
	}
	if not no_flash_attn:
		model_kwargs["attn_implementation"] = "flash_attention_2"

	if quantize:
		model_kwargs["quantization_config"] = BitsAndBytesConfig(
			load_in_4bit=True,
			bnb_4bit_compute_dtype=torch.bfloat16,
			bnb_4bit_use_double_quant=True,
			bnb_4bit_quant_type="nf4",
		)

	# Qwen2.5-VL은 transformers 4.50+에서 Qwen2_5_VLForConditionalGeneration 클래스로 노출됨.
	# 그 이전 버전은 Qwen2VLForConditionalGeneration 사용.
	try:
		from transformers import Qwen2_5_VLForConditionalGeneration as _Cls  # type: ignore
	except ImportError:
		from transformers import Qwen2VLForConditionalGeneration as _Cls  # type: ignore
	model = _Cls.from_pretrained(base_model, **model_kwargs)
	return model, processor


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Qwen2.5-VL LoRA SFT (Phase 3)")
	parser.add_argument("--train", type=Path, required=True, help="train JSONL (Phase 2 output)")
	parser.add_argument("--eval", type=Path, required=True, help="eval JSONL (Phase 2 output)")
	parser.add_argument("--out", type=Path, required=True, help="ckpt 출력 디렉토리")
	parser.add_argument("--base-model", default="Qwen/Qwen2.5-VL-32B-Instruct")
	parser.add_argument(
		"--data-root",
		type=Path,
		default=REPO_ROOT,
		help="JSONL의 image 경로 (`trajectories/...`) resolve 기준 (기본: repo root)",
	)

	# Training hyperparameters
	parser.add_argument("--epochs", type=float, default=3)
	parser.add_argument("--lr", type=float, default=2e-4)
	parser.add_argument("--batch", type=int, default=1, help="per-device batch size (32B는 1 권장)")
	parser.add_argument("--grad-accum", type=int, default=8)
	parser.add_argument("--max-seq", type=int, default=8192, help="max sequence length (image tokens 포함)")
	parser.add_argument("--warmup-ratio", type=float, default=0.05)

	# LoRA hyperparameters
	parser.add_argument("--lora-r", type=int, default=16)
	parser.add_argument("--lora-alpha", type=int, default=32)
	parser.add_argument("--lora-dropout", type=float, default=0.05)

	# Modes
	parser.add_argument("--quantize", action="store_true", help="QLoRA 4bit fallback (메모리 압박 시)")
	parser.add_argument(
		"--text-only",
		action="store_true",
		help="이미지 무시하고 텍스트만 학습 — 파이프라인 빠른 검증용",
	)
	parser.add_argument("--no-flash-attn", action="store_true")

	# Smoke test helpers
	parser.add_argument("--max-train-samples", type=int, default=None)
	parser.add_argument("--max-eval-samples", type=int, default=None)
	parser.add_argument("--logging-steps", type=int, default=5)
	parser.add_argument("--save-steps", type=int, default=None, help="기본은 epoch 단위 저장")
	parser.add_argument("--seed", type=int, default=42)

	args = parser.parse_args(argv)

	# 1. 데이터 로드
	train_data = _load_jsonl(args.train)
	eval_data = _load_jsonl(args.eval)
	if args.max_train_samples:
		train_data = train_data[: args.max_train_samples]
	if args.max_eval_samples:
		eval_data = eval_data[: args.max_eval_samples]
	print(f"[INFO] train: {len(train_data)} samples")
	print(f"[INFO] eval:  {len(eval_data)} samples")
	print(f"[INFO] data_root: {args.data_root.resolve()}")
	print(f"[INFO] text_only: {args.text_only}")

	train_ds = Dataset.from_list(train_data)
	eval_ds = Dataset.from_list(eval_data)

	# 2. 모델 + processor
	print(f"[INFO] Loading {args.base_model} (quantize={args.quantize}, flash_attn={not args.no_flash_attn})...")
	model, processor = _load_model_and_processor(
		base_model=args.base_model,
		quantize=args.quantize,
		no_flash_attn=args.no_flash_attn,
	)
	if args.quantize:
		model = prepare_model_for_kbit_training(model)
	print(f"[INFO] Model loaded. Total params: {sum(p.numel() for p in model.parameters()) / 1e9:.2f}B")

	# 3. LoRA config
	lora = LoraConfig(
		r=args.lora_r,
		lora_alpha=args.lora_alpha,
		lora_dropout=args.lora_dropout,
		target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
		task_type="CAUSAL_LM",
	)

	# 4. SFT config
	sft_kwargs: dict[str, Any] = {
		"output_dir": str(args.out),
		"per_device_train_batch_size": args.batch,
		"per_device_eval_batch_size": args.batch,
		"gradient_accumulation_steps": args.grad_accum,
		"learning_rate": args.lr,
		"num_train_epochs": args.epochs,
		"warmup_ratio": args.warmup_ratio,
		"bf16": True,
		"gradient_checkpointing": True,
		"logging_steps": args.logging_steps,
		"report_to": [],
		"remove_unused_columns": False,
		"dataset_kwargs": {"skip_prepare_dataset": True},
		"seed": args.seed,
	}
	if args.save_steps:
		sft_kwargs["save_strategy"] = "steps"
		sft_kwargs["save_steps"] = args.save_steps
	else:
		sft_kwargs["save_strategy"] = "epoch"
	sft_kwargs["eval_strategy"] = "epoch"
	# trl 0.12+에서 max_seq_length는 SFTConfig 필드. 일부 버전에서는 dataset_text_field 와 같이 다룸.
	try:
		sft_cfg = SFTConfig(max_seq_length=args.max_seq, **sft_kwargs)
	except TypeError:
		# 더 신버전: model_init_kwargs / max_length 등으로 분리됐을 수 있음
		sft_cfg = SFTConfig(**sft_kwargs)

	# 5. Collator
	collator = make_collator(
		processor=processor,
		data_root=args.data_root.resolve(),
		text_only=args.text_only,
		max_length=args.max_seq,
	)

	# 6. Trainer
	trainer = SFTTrainer(
		model=model,
		args=sft_cfg,
		train_dataset=train_ds,
		eval_dataset=eval_ds,
		peft_config=lora,
		data_collator=collator,
		processing_class=processor.tokenizer,
	)

	# 7. Train
	print(f"[INFO] Starting training → {args.out}")
	trainer.train()
	print(f"[INFO] Saving final adapter to {args.out}")
	trainer.save_model(str(args.out))
	# Save processor too for easy reload
	try:
		processor.save_pretrained(str(args.out))
	except Exception as e:  # noqa: BLE001
		print(f"[WARN] processor.save_pretrained failed: {e}", file=sys.stderr)

	print("[DONE]")
	return 0


if __name__ == "__main__":
	sys.exit(main())
