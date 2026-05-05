# cnu-ai-agent

Browser-Use + Qwen2.5-VL 기반 충남대 KORUS 자동화 에이전트 (Teacher-Student 행동복제 파이프라인).

**1차 범위**: KORUS (전자결재) 단일 도메인, 100 trajectory.

## 문서

- **[PLAN.md](PLAN.md)** — ground truth. 모든 구현은 이 문서를 따른다. Phase -1부터 Phase 4까지 단계별 산출물 정의.
- **[CLAUDE.md](CLAUDE.md)** — Claude Code onboarding (학교 환경에서 시작할 때 읽으면 됨).

## 셋업 — 작업이 두 머신에 걸쳐 있음

| 단계 | 머신 |
|------|------|
| Phase 0~2 (수집·변환) + Phase 4 (eval, 브라우저 동작) | 학교 **맥북** (macOS, 학내망에서 KORUS 접근 가능) |
| Phase 3 (LoRA SFT) | **B200 학습 서버** (`/NHNHOME/WORKSPACE/26moe002_H/<your-id>/`) |

학습 결과(ckpt)는 두 머신 사이에서 `rsync`/`scp`로 옮기거나, B200에서 vLLM serve 후 맥북에서 원격 호출 (Phase 4 네트워크 메모 참고).

### 1. 맥북 (수집·변환·평가)

```bash
git clone https://github.com/Sunkist18/cnu-ai-agent.git
cd cnu-ai-agent
uv venv --python 3.11
uv sync --extra dev

# Claude Code 띄우고 "PLAN.md 읽고 Phase 0a부터 진행해줘"
claude
```

### 2. B200 학습 서버 (Phase 3만)

```bash
# 본인 학생 폴더로 이동 (예: mwchoi)
cd /NHNHOME/WORKSPACE/26moe002_H/<your-id>
git clone https://github.com/Sunkist18/cnu-ai-agent.git
cd cnu-ai-agent

# root /home은 용량 작으니 venv는 본인 폴더 안에 만든다 (위에서 cd 한 위치)
uv venv --python 3.11
uv sync --extra training --extra serve
# uv가 컨테이너에 없으면: pip install -e ".[training,serve]"

# 학습은 단일 명령 — Claude Code 없이도 됨
python -m cnu_agent.training.qlora_sft \
    --train data/korus_train.jsonl \
    --eval  data/korus_eval.jsonl \
    --out   ckpt/qwen25vl-korus-lora
```

수집한 trajectory(맥북)와 학습 데이터(맥북에서 변환)를 B200으로 옮기는 방법:
```bash
# 맥북에서
rsync -av --progress data/ <user>@<b200-host>:/NHNHOME/WORKSPACE/26moe002_H/<your-id>/cnu-ai-agent/data/
```

### 3. Phase 4 (online eval) 네트워크 메모

B200이 학내망에 있는지 확인 필요. 학내망 밖이면 vLLM은 B200에서 serve, 브라우저는 맥북에서 띄우고 SSH tunnel 또는 학내 reverse proxy로 endpoint 연결. 그게 어렵다면 학습 ckpt를 맥북으로 가져와서 (단, 32B는 ~64GB라 맥북에서 추론은 어려움) 또는 작은 7B 모델로 1차 검증 후 B200에서 본 평가. 학습이 끝난 시점에서 결정.

## 진행 단계 (요약)

| Phase | 산출물 |
|------|------|
| -1: Repo bootstrap | 본 repo (지금) |
| 0a: Plumbing 검증 | `cnu_agent/teacher/claude_code_llm.py` 동작 확인 |
| 0b: Discovery + paraphrase | `discovery/seeds.json`, `tasks/korus_100.json` |
| 1: Teacher trajectory 수집 | `trajectories/{task_id}/...` 100개 |
| 2: 데이터 변환 | `data/korus_train.jsonl`, `data/korus_eval.jsonl` |
| 3: Student LoRA 학습 | `ckpt/qwen25vl-korus-lora/` |
| 4: 추론·평가 | Action accuracy / Task success rate |

## ⚠️ ToS 메모

Claude를 Teacher로 써서 다른 LLM을 distillation 하는 게 Anthropic Commercial Terms와 Max 구독 약관에 위배될 수 있음. 시작 전 본인이 확인할 것 — 자세한 내용 [PLAN.md](PLAN.md) 상단 ⚠️ 섹션.
