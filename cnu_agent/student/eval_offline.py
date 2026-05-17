"""Phase 4 offline evaluation — action accuracy on held-out trajectories.

For each eval sample in data_v2/korus_eval.jsonl:
1. Build prompt from system + user (omit gold assistant)
2. Generate completion from Student model (base + LoRA adapter)
3. Parse generated AgentOutput JSON → first action name
4. Compare to gold (assistant message → parse → first action name)

Metric:
- JSON validity rate
- Top-1 action name accuracy (gold vs gen)
- Per-task / per-seed breakdown

vLLM serve + browser-use online eval과는 별개. 빠르고 자원 적게 듦.

Run on B200:
  python -m cnu_agent.student.eval_offline \\
    --eval     data_v2/korus_eval.jsonl \\
    --adapter  ckpt/qwen25vl-korus-lora-v2 \\
    --out      analysis/eval_v2_offline.json \\
    --max-samples 50  # smoke; full 146 ≈ 15분
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import torch
from peft import PeftModel
from PIL import Image
from transformers import AutoProcessor

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_first_action(text: str) -> str | None:
	"""Extract first action's NAME from AgentOutput JSON in text."""
	try:
		obj = json.loads(text)
	except Exception:
		m = re.search(r"\{.*\}", text, re.DOTALL)
		if not m:
			return None
		try:
			obj = json.loads(m.group(0))
		except Exception:
			return None
	if not isinstance(obj, dict):
		return None
	actions = obj.get("action")
	if not actions or not isinstance(actions, list):
		return None
	first = actions[0]
	if not isinstance(first, dict) or not first:
		return None
	return list(first.keys())[0]


def _load_jsonl(path: Path) -> list[dict]:
	out = []
	for line in path.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if line:
			out.append(json.loads(line))
	return out


def _resolve_images(messages: list[dict], data_root: Path) -> list[Image.Image]:
	images: list[Image.Image] = []
	for m in messages:
		c = m.get("content")
		if isinstance(c, list):
			for p in c:
				if isinstance(p, dict) and p.get("type") == "image":
					path = data_root / p["image"]
					if path.exists():
						try:
							images.append(Image.open(path).convert("RGB"))
						except Exception as e:  # noqa: BLE001
							print(f"  ⚠️ image open failed {path}: {e}", file=sys.stderr)
	return images


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--eval", type=Path, required=True)
	parser.add_argument("--adapter", type=Path, required=True)
	parser.add_argument("--out", type=Path, required=True)
	parser.add_argument("--base-model", default="Qwen/Qwen2.5-VL-32B-Instruct")
	parser.add_argument("--data-root", type=Path, default=REPO_ROOT)
	parser.add_argument("--max-new-tokens", type=int, default=1024)
	parser.add_argument("--max-image-tokens", type=int, default=512)
	parser.add_argument("--max-seq", type=int, default=8192)
	parser.add_argument("--max-samples", type=int, default=None)
	parser.add_argument("--no-flash-attn", action="store_true")
	args = parser.parse_args(argv)

	samples = _load_jsonl(args.eval)
	if args.max_samples:
		samples = samples[: args.max_samples]
	print(f"[INFO] eval samples: {len(samples)}")
	print(f"[INFO] adapter: {args.adapter}")

	print(f"[INFO] Loading base model {args.base_model} ...")
	model_kwargs: dict = {"torch_dtype": torch.bfloat16, "device_map": "auto"}
	if not args.no_flash_attn:
		model_kwargs["attn_implementation"] = "flash_attention_2"
	try:
		from transformers import Qwen2_5_VLForConditionalGeneration as _Cls  # type: ignore
	except ImportError:
		from transformers import Qwen2VLForConditionalGeneration as _Cls  # type: ignore
	base = _Cls.from_pretrained(args.base_model, **model_kwargs)
	print(f"[INFO] Loading adapter {args.adapter} ...")
	model = PeftModel.from_pretrained(base, str(args.adapter))
	model.eval()

	processor = AutoProcessor.from_pretrained(args.base_model, trust_remote_code=True)
	if hasattr(processor, "image_processor"):
		processor.image_processor.max_pixels = args.max_image_tokens * 28 * 28
		processor.image_processor.min_pixels = 64 * 28 * 28

	results = []
	for i, sample in enumerate(samples):
		msgs = sample["messages"]
		gold_assistant = msgs[-1]["content"]
		prompt_msgs = msgs[:-1]

		images = _resolve_images(prompt_msgs, args.data_root)
		text = processor.apply_chat_template(prompt_msgs, tokenize=False, add_generation_prompt=True)

		try:
			inputs = processor(
				text=[text],
				images=[images] if images else None,
				padding=True,
				truncation=True,
				max_length=args.max_seq,
				return_tensors="pt",
			).to(model.device)
			with torch.no_grad():
				out_ids = model.generate(
					**inputs,
					max_new_tokens=args.max_new_tokens,
					do_sample=False,
					pad_token_id=processor.tokenizer.pad_token_id,
				)
			gen_ids = out_ids[:, inputs["input_ids"].shape[1] :]
			gen_text = processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
		except Exception as e:  # noqa: BLE001
			gen_text = ""
			print(f"  [{i+1}/{len(samples)}] {sample.get('task_id')}: generation failed: {e}", file=sys.stderr)

		gen_action = parse_first_action(gen_text)
		gold_action = parse_first_action(gold_assistant)
		match = bool(gen_action and gold_action and gen_action == gold_action)
		results.append(
			{
				"task_id": sample.get("task_id"),
				"step": sample.get("step"),
				"gold_action": gold_action,
				"gen_action": gen_action,
				"match": match,
				"valid_json": gen_action is not None,
				"gen_text_head": gen_text[:200],
			}
		)
		if (i + 1) % 5 == 0 or i + 1 == len(samples):
			running_match = sum(1 for r in results if r["match"]) / len(results)
			running_valid = sum(1 for r in results if r["valid_json"]) / len(results)
			print(
				f"  {i+1}/{len(samples)}: gold={gold_action} gen={gen_action} match={match} | "
				f"running match={running_match:.1%} valid={running_valid:.1%}"
			)

	total = len(results)
	valid = sum(1 for r in results if r["valid_json"])
	matches = sum(1 for r in results if r["match"])

	# per task
	by_task: dict = defaultdict(lambda: {"total": 0, "match": 0})
	for r in results:
		t = r["task_id"]
		by_task[t]["total"] += 1
		if r["match"]:
			by_task[t]["match"] += 1
	# per seed (id suffix _NN 제거)
	by_seed: dict = defaultdict(lambda: {"total": 0, "match": 0})
	for r in results:
		seed = (r["task_id"] or "").rsplit("_", 1)[0]
		by_seed[seed]["total"] += 1
		if r["match"]:
			by_seed[seed]["match"] += 1

	print(f"\n=== Offline action accuracy ===")
	print(f"  total samples: {total}")
	print(f"  valid JSON:    {valid} ({valid/total*100:.1f}%)" if total else "  no samples")
	print(f"  top-1 action match: {matches} ({matches/total*100:.1f}%)")

	print(f"\n=== Per seed ===")
	for s in sorted(by_seed):
		d = by_seed[s]
		print(f"  {s:38s}: {d['match']}/{d['total']} = {d['match']/d['total']*100:.0f}%")

	args.out.parent.mkdir(parents=True, exist_ok=True)
	args.out.write_text(
		json.dumps(
			{
				"total": total,
				"valid_json": valid,
				"matches": matches,
				"action_accuracy": matches / total if total else 0,
				"json_validity": valid / total if total else 0,
				"per_seed": {s: dict(d) for s, d in by_seed.items()},
				"per_task": {t: dict(d) for t, d in by_task.items()},
				"per_sample": results,
			},
			indent=2,
			ensure_ascii=False,
		),
		encoding="utf-8",
	)
	print(f"\n💾 saved → {args.out}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
