#!/usr/bin/env bash
# v3 학습 (B200 서버에서 실행)
#
# 전제:
#   - cd /NHNHOME/WORKSPACE/26moe002_H/mwchoi/cnu-ai-agent
#   - .venv 활성화 + transformers/peft/trl/torch 설치됨
#   - HF_TOKEN 설정 (private dataset 접근용)
#
# 실행:
#   bash scripts/b200_train_v3.sh
#
# 결과:
#   ckpt/qwen25vl-korus-lora-v3/  (LoRA adapter)
#   ckpt/qwen25vl-korus-lora-v3/checkpoint-N/  (epoch별)

set -euxo pipefail

REPO="chaeminu/cnu-korus-trajectories-v2"
DATA_DIR="$HOME/cnu-ai-agent/data_v3"
TRAJ_DIR="$HOME/cnu-ai-agent/trajectories_v3"
CKPT_DIR="$HOME/cnu-ai-agent/ckpt/qwen25vl-korus-lora-v3"

# 1) HF에서 v3 dataset 다운로드
echo "[1/3] Downloading v3 dataset + screenshots from HF..."
hf download "$REPO" --repo-type dataset \
  --include "data_v3/*" \
  --include "trajectories_v3/*/screenshots/*.png" \
  --local-dir "$HOME/cnu-ai-agent"

ls -la "$DATA_DIR/"
echo "screenshots: $(find "$TRAJ_DIR" -name '*.png' | wc -l)"

# 2) 학습 (Qwen2.5-VL-32B + LoRA r=16)
echo "[2/3] Training v3 (32B + LoRA)..."
cd "$HOME/cnu-ai-agent"

PYTHONPATH=. python -m cnu_agent.training.qlora_sft \
  --train "$DATA_DIR/korus_train.jsonl" \
  --eval  "$DATA_DIR/korus_eval.jsonl" \
  --out   "$CKPT_DIR" \
  --base-model "Qwen/Qwen2.5-VL-32B-Instruct" \
  --epochs 3 \
  --lr 2e-4 \
  --batch 1 \
  --grad-accum 8 \
  --max-seq 8192 \
  --lora-r 16 \
  --lora-alpha 32 \
  --lora-dropout 0.05 \
  2>&1 | tee "$HOME/cnu-ai-agent/train_v3.log"

# 3) ckpt를 HF로 push (Mac에서 vLLM이 pull할 수 있게)
echo "[3/3] Uploading v3 ckpt to HF..."
hf upload "$REPO" "$CKPT_DIR/checkpoint-273" "ckpt_v3/checkpoint-273" \
  --repo-type dataset

echo "✅ v3 학습 완료. Mac에서 vLLM reload 가능"
echo "   adapter: $CKPT_DIR/checkpoint-273"
echo "   HF path: $REPO/ckpt_v3/checkpoint-273"
