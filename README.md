# cnu-ai-agent

Browser-Use + Qwen2.5-VL 기반 충남대 KORUS 자동화 에이전트 (Teacher-Student 행동복제 파이프라인).

**1차 범위**: KORUS (전자결재) 단일 도메인, 100 trajectory.

## 문서

- **[PLAN.md](PLAN.md)** — ground truth. 모든 구현은 이 문서를 따른다. Phase -1부터 Phase 4까지 단계별 산출물 정의.
- **[CLAUDE.md](CLAUDE.md)** — Claude Code onboarding (학교 환경에서 시작할 때 읽으면 됨).

## 학교 환경 (단일 B200, Clunix 컨테이너) 셋업

```bash
cd /NHNHOME/WORKSPACE
git clone https://github.com/choiminwoo/cnu-ai-agent.git
cd cnu-ai-agent

# 의존성 설치
uv venv --python 3.11
uv sync --extra training --extra serve --extra dev
# uv가 컨테이너에 없으면: pip install -e ".[training,serve,dev]"

# Claude Code 띄우고 "PLAN.md 읽고 Phase 0a부터 진행해줘"
claude
```

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
