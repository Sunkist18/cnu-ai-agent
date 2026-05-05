"""Phase 3: Qwen2.5-VL-32B LoRA SFT on B200 (bf16 default, --quantize fallback for QLoRA 4bit).

Implementation guide: see `PLAN.md` §6.

기본은 LoRA bf16 (B200 183GB 메모리 여유 → quantization 불필요, 학습 안정성 우월).
`--quantize` 플래그로 QLoRA 4bit fallback 가능.

Run:
    python -m cnu_agent.training.qlora_sft \\
        --train data/korus_train.jsonl \\
        --eval  data/korus_eval.jsonl \\
        --out   ckpt/qwen25vl-korus-lora \\
        --epochs 3
"""

from __future__ import annotations


def main() -> None:
	raise NotImplementedError("Implement per PLAN.md §6")


if __name__ == "__main__":
	main()
