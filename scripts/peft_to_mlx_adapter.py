"""PEFT (HF) LoRA adapter → mlx-vlm format adapter 변환.

PEFT key 형식:
  base_model.model.model.language_model.layers.{N}.{block}.{module}.lora_A.weight
  base_model.model.model.language_model.layers.{N}.{block}.{module}.lora_B.weight
  - lora_A.weight shape: (rank, in_features)
  - lora_B.weight shape: (out_features, rank)

mlx-vlm key 형식 (apply_lora_layers 후 LoRaLayer 내부 attribute):
  language_model.model.layers.{N}.{block}.{module}.A   shape (in_features, rank)
  language_model.model.layers.{N}.{block}.{module}.B   shape (rank, out_features)

차이:
1. 키 prefix 재배치 (PEFT: `base_model.model.model.language_model.X`
   → MLX: `language_model.model.X`)
2. weight transpose (A: T, B: T)
3. dtype float32 → float16/bfloat16 (선택, MLX 호환성)
4. adapter_config.json에 `rank` 키 추가 (mlx-vlm은 `r` 안 보고 `rank` 봄)

Run:
  python scripts/peft_to_mlx_adapter.py \\
    --src /tmp/our_ckpt/ckpt \\
    --dst /tmp/our_ckpt_mlx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mlx.core as mx
from safetensors import safe_open
from safetensors.numpy import save_file as save_safetensors  # numpy호환으로 저장

PEFT_PREFIX = "base_model.model.model.language_model."
MLX_PREFIX = "language_model.model."


def convert_key_and_weight(peft_key: str, peft_tensor: mx.array) -> tuple[str, mx.array] | None:
	"""PEFT key → MLX key, + weight transpose."""
	if not peft_key.startswith(PEFT_PREFIX):
		# Unexpected prefix — skip (visual blocks 등은 우리 LoRA target 아님)
		return None
	suffix = peft_key[len(PEFT_PREFIX):]  # 예: "layers.0.self_attn.q_proj.lora_A.weight"

	# .lora_A.weight / .lora_B.weight → .A / .B (transpose)
	if suffix.endswith(".lora_A.weight"):
		new_suffix = suffix[:-len(".lora_A.weight")] + ".A"
		# (rank, in) → (in, rank)
		new_tensor = peft_tensor.T
	elif suffix.endswith(".lora_B.weight"):
		new_suffix = suffix[:-len(".lora_B.weight")] + ".B"
		# (out, rank) → (rank, out)
		new_tensor = peft_tensor.T
	else:
		# 일반 LoRA가 아닌 다른 weight (bias 등) — 일단 skip
		return None

	mlx_key = MLX_PREFIX + new_suffix
	return mlx_key, new_tensor


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--src", type=Path, required=True, help="PEFT ckpt dir (with adapter_config.json + adapter_model.safetensors)")
	parser.add_argument("--dst", type=Path, required=True, help="MLX adapter output dir")
	parser.add_argument("--dtype", default="bfloat16", choices=["float32", "float16", "bfloat16"])
	args = parser.parse_args(argv)

	src = args.src
	dst = args.dst
	dst.mkdir(parents=True, exist_ok=True)

	# 1. PEFT adapter_config → MLX adapter_config (add `rank` field)
	peft_cfg = json.loads((src / "adapter_config.json").read_text(encoding="utf-8"))
	mlx_cfg = {
		"rank": peft_cfg["r"],
		"alpha": peft_cfg["lora_alpha"],
		"dropout": peft_cfg.get("lora_dropout", 0.0),
		"target_modules": peft_cfg.get("target_modules", []),
		# 원본 PEFT 필드도 동봉 (디버깅용)
		"_peft_source": {k: v for k, v in peft_cfg.items() if not isinstance(v, (dict, list)) or k == "target_modules"},
	}
	(dst / "adapter_config.json").write_text(
		json.dumps(mlx_cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
	)
	print(f"[1/3] adapter_config.json — rank={mlx_cfg['rank']} alpha={mlx_cfg['alpha']}")

	# 2. Convert safetensors
	src_st = src / "adapter_model.safetensors"
	if not src_st.exists():
		print(f"[FAIL] {src_st} 없음", file=sys.stderr)
		return 2

	import numpy as np

	new_state: dict[str, np.ndarray] = {}
	dtype_map = {"float32": np.float32, "float16": np.float16, "bfloat16": None}  # bf16은 numpy 직접 안 됨

	dtype_name = args.dtype
	n_lora = n_skip = 0
	with safe_open(str(src_st), framework="mlx") as f:
		for k in sorted(f.keys()):
			t = f.get_tensor(k)
			out = convert_key_and_weight(k, t)
			if out is None:
				n_skip += 1
				continue
			new_key, new_tensor = out
			# dtype 변환
			if dtype_name == "bfloat16":
				new_tensor = new_tensor.astype(mx.bfloat16)
				# safetensors numpy 저장은 bfloat16 직접 안 됨 — float32로 캐스트 후 저장하거나
				# mlx의 save 함수 사용
				np_arr = np.asarray(new_tensor.astype(mx.float32))  # bf16 round-trip
			elif dtype_name == "float16":
				np_arr = np.asarray(new_tensor.astype(mx.float16))
			else:
				np_arr = np.asarray(new_tensor.astype(mx.float32))
			new_state[new_key] = np_arr
			n_lora += 1

	print(f"[2/3] converted {n_lora} lora tensors (skipped {n_skip})")

	# 3. Save — mlx-vlm 기본 파일명 'adapters.safetensors'
	dst_st = dst / "adapters.safetensors"
	save_safetensors(new_state, str(dst_st))
	print(f"[3/3] saved → {dst_st}  ({dst_st.stat().st_size // 1024 // 1024} MB)")

	# 샘플 키 출력
	print("\n샘플 키:")
	for k in sorted(new_state.keys())[:5]:
		print(f"  {k}  shape={new_state[k].shape} dtype={new_state[k].dtype}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
