"""Phase 4: vLLM serve fine-tuned LoRA + browser-use Agent로 KORUS task 실행 (eval 포함).

Implementation guide: see `PLAN.md` §7.

Steps:
1. vLLM serve `Qwen/Qwen2.5-VL-32B-Instruct --enable-lora --lora-modules korus=ckpt/qwen25vl-korus-lora`
2. browser-use Agent에 ChatOpenAILike(base_url="http://localhost:8000/v1") 주입
3. held-out 20 task 실행 → action accuracy + task success rate 기록

Run:
    # Terminal 1: vLLM
    vllm serve Qwen/Qwen2.5-VL-32B-Instruct \\
        --enable-lora \\
        --lora-modules korus=ckpt/qwen25vl-korus-lora \\
        --port 8000 --max-model-len 16384

    # Terminal 2: eval
    python -m cnu_agent.student.serve_and_run \\
        --tasks data/korus_eval.jsonl \\
        --base-url http://localhost:8000/v1
"""

from __future__ import annotations


async def main() -> None:
	raise NotImplementedError("Implement per PLAN.md §7")


if __name__ == "__main__":
	import asyncio

	asyncio.run(main())
