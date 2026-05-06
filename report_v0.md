# CNU AI Agent — v0 진행 리포트

**작성일**: 2026-05-06 (KST)
**작업자**: 최채민 (Sunkist18 / chaeminu)
**작업 환경**: 학교 맥북 (Phase 0~2) + B200 학습 서버 NVIDIA (Phase 3)
**Repo**: github.com/Sunkist18/cnu-ai-agent (private)

---

## 0. 한 줄 요약

| 항목 | 값 |
|---|---|
| 1차 범위 (계획) | KORUS 단일 도메인, 100 trajectory |
| 실제 수집 | 24 trajectory (read-only 카테고리만, mock 결재선 미설정) |
| 단계 진행 | Phase -1 → Phase 3 학습 완료 (전체 5단계 중 3단계) |
| 학습 결과 | Qwen2.5-VL-32B (33.45B) + LoRA r=16, 3 epoch, train_loss 1.143 |
| 최종 eval | loss 0.611 / token_acc 0.906 (단, seed 누설 — §6.3.5 참조) |
| Teacher success rate | 13/24 (54%) — PLAN.md 목표 70% 미달 |
| Mutating action 클릭 | 0건 (audit 검증) |
| 총 작업 시간 | 약 28시간 (반복 디버깅 포함) |
| Phase 3 학습 시간 | 32분 59초 (B200 단일 GPU) |

---

## 1. 단계별 진행

| Phase | 산출물 | 상태 | 소요 시간 |
|---|---|---|---|
| **-1** Repo bootstrap | skeleton + PLAN.md + CLAUDE.md | ✅ 완료 | (사전 작업) |
| **0a** ChatClaudeCode | `cnu_agent/teacher/claude_code_llm.py` | ✅ 완료 | 약 1시간 |
| **0b** Discovery + Paraphrase | seeds.json (38) + curated (25) + tasks (100) | ✅ 완료 | 약 4시간 |
| **1** Trajectory 수집 (v0) | `trajectories/` 24 디렉토리 | ✅ 부분 완료 (24/100) | 약 4시간 (1차 abort 포함) |
| **2** ChatML 변환 | `data/korus_train.jsonl` + `eval.jsonl` | ✅ 완료 | 30분 |
| **3** LoRA SFT | `ckpt/qwen25vl-korus-lora-v0/` (566 MB adapter, 5.4 GB ckpt) | ✅ 완료 | smoke 54초 + full **32분 59초** |
| **4** vLLM 추론 평가 | (미진행) | ⏸ 보류 | — |

---

## 2. 산출물 — 파일·데이터 수치

### 2.1 코드

| 파일 | 라인 수 | 테스트 |
|---|---|---|
| `cnu_agent/teacher/claude_code_llm.py` | 320 | 3/3 PASS |
| `cnu_agent/teacher/discover.py` | 254 | — (E2E 검증) |
| `cnu_agent/teacher/paraphrase.py` | 203 | — (출력 검증) |
| `cnu_agent/teacher/collect.py` | 521 | — (E2E 검증) |
| `cnu_agent/data/trajectory_to_sft.py` | 250 | 12/12 PASS |
| `cnu_agent/training/qlora_sft.py` | 308 | smoke 통과 |
| `scripts/save_auth.py` | 172 | — |
| `scripts/audit_trajectories.py` | 152 | — |
| `tests/cnu_agent/test_claude_code_llm.py` | 78 | 3/3 PASS |
| `tests/cnu_agent/test_seeds_and_tasks.py` | 159 | 10/10 PASS |
| `tests/cnu_agent/test_trajectory_conversion.py` | 178 | 12/12 PASS |

총 테스트: **40/40 PASS**

### 2.2 데이터

| Artifact | 개수 | 크기 |
|---|---|---|
| `discovery/seeds.json` | 38 seed | 12 KB |
| `discovery/seeds_curated.json` | 25 seed | 8 KB |
| `tasks/korus_100.json` | 100 task | 28 KB |
| `auth/korus_storage_state.json` | 4 쿠키 (2 도메인) | 1.1 KB |
| `trajectories/*/` | 24 디렉토리 | 90 MB |
| `trajectories/*/screenshots/*.png` | 287 PNG | 약 60 MB |
| `data/korus_train.jsonl` | 234 sample | 9.7 MB |
| `data/korus_eval.jsonl` | 74 sample | 3.2 MB |

### 2.3 모델·체크포인트

| 항목 | 값 |
|---|---|
| Base model | `Qwen/Qwen2.5-VL-32B-Instruct` |
| Total params | 33.45B |
| Trainable params (LoRA) | 약 100M (r=16, 7 modules) |
| Quantization | 없음 (bf16) |
| Flash-attention | 미사용 (SDPA) |
| LoRA target modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |

---

## 3. Phase 0b — Discovery 결과

### 3.1 38 seed 카테고리 분포

| 카테고리 | 개수 | requires_sensitive |
|---|---|---|
| 결재작성 | 20 | 20 (100%) |
| 결재처리 | 3 | 3 (100%) |
| 문서조회 | 7 | 4 (57%) |
| 첨부파일 | 2 | 1 (50%) |
| 결재선설정 | 3 | 0 (0%) |
| 환경설정 | 3 | 0 (0%) |
| **합계** | **38** | **28 (74%)** |

### 3.2 Curate (38 → 25)

trim 사유:
- 출장 정산 2건 (신청 폼과 패턴 유사)
- 국외출장 정산 1건 (해외 결재선 복잡, mock 부담)
- 급여 폼 2건 (계좌 1건만 남김)
- 공간/동아리/제안 등 specialized 1건씩 제거
- `(추정)` 표시된 메뉴 경로 3건 (잘못된 경로 학습 위험)
- 특수 권한 필요 1건 (포상 심사위원)

### 3.3 Paraphrase (25 → 100 task)

| 길이 | 분포 |
|---|---|
| min | 6자 |
| p25 | 15자 |
| median | 26자 |
| p75 | 58자 |
| max | 185자 |

| placeholder 키 | 사용 횟수 |
|---|---|
| `{{start_date}}` | 10 |
| `{{end_date}}` | 9 |
| `{{destination}}` | 4 |
| `{{purpose}}` | 4 |
| `{{doc_title}}` | 3 |
| `{{file_path}}` | 3 |
| `{{my_emp_id}}`, `{{date}}`, 기타 | 1~2 |

sensitive_keys 있는 task: **34/100**.

---

## 4. Phase 1 v0 — Trajectory 수집 결과

### 4.1 카테고리별 Teacher success rate

| Seed | trajectory 개수 | success | 평균 step | 평균 size |
|---|---|---|---|---|
| view_in_progress | 4 | **4 / 4 (100%)** | 13.0 | 3.4 MB |
| view_completed | 4 | 3 / 4 (75%) | 16.5 | 5.6 MB |
| circulate_pending | 4 | 3 / 4 (75%) | 7.0 | 1.4 MB |
| approve_pending | 4 | 2 / 4 (50%) | 11.2 | 2.4 MB |
| view_salary_statement | 4 | 1 / 4 (25%) | 13.5 | 3.8 MB |
| view_doc_register | 4 | 0 / 4 (0%) | 15.8 | 5.6 MB |
| **합계** | **24** | **13 / 24 (54%)** | **12.8** | **3.75 MB** |

### 4.2 안전성 검증

| 검사 항목 | 결과 |
|---|---|
| Mutating action 클릭 | **0건** (전 24 trajectory) |
| 검사 방법 | `state.interacted_element[*].ax_name` ground-truth audit |
| 검사 키워드 | 승인, 반려, 상신, 제출, 저장, 삭제, 회수, 재상신, 결재완료, 발송, 전송 |
| `_MUTATING_AUDIT.json` 생성 trajectory | 0개 |
| `_MUTATING_BLOCKED.json` (false-positive) | 13개 → 모두 정리 완료 |

### 4.3 step 수 분포 (24 trajectory)

| 구간 | 개수 |
|---|---|
| 0-4 step | 3 |
| 5-9 step | 4 |
| 10-14 step | 4 |
| 15-19 step | 13 |

총 step: 308 (avg 12.8/traj).

### 4.4 미수집 4 trajectory (대상 28 중)

| 사유 | 개수 |
|---|---|
| KORUS 세션 만료 후 로그인 redirect | 2 (`view_year_end_tax_00`, `_01`) |
| Process kill 시점 partial | 1 (`view_year_end_tax_02` — history.json 미생성) |
| 미시작 | 1 (`view_year_end_tax_03`) |

세션 만료 시점: 약 08:30 KST (`save_auth` 후 약 3.5시간 경과).

---

## 5. Phase 2 — ChatML 변환 결과

| 항목 | 값 |
|---|---|
| 입력 trajectory | 24 |
| 입력 step | 308 |
| 변환 실패 (불완전 step) | 0 |
| Output train | 234 sample (19 task) |
| Output eval | 74 sample (5 task) |
| Eval task IDs | circulate_pending_01, view_doc_register_01, view_doc_register_03, view_in_progress_02, view_salary_statement_03 |
| Train/eval split 기준 | task_id 단위 (step 단위 split = 데이터 누설) |
| Random seed | 42 |
| 이미지 path 포맷 | repo-relative (`trajectories/<id>/screenshots/step_N.png`) |

---

## 6. Phase 3 — LoRA SFT 결과

### 6.1 환경

| 항목 | 값 |
|---|---|
| GPU | NVIDIA B200 |
| VRAM | 191.5 GB |
| CUDA | 13.0 (compiled) |
| torch | 2.11.0+cu130 |
| Python | 3.11.13 (uv-managed) |
| 작업 디렉토리 | `/NHNHOME/WORKSPACE/26moe002_H/mwchoi/cnu-ai-agent` |
| HF cache | `/NHNHOME/WORKSPACE/26moe002_H/mwchoi/.cache/huggingface` (lustre1, 2TB) |
| 모델 다운로드 크기 | 약 64 GB (Qwen2.5-VL-32B-Instruct, 18 files) |

### 6.2 Smoke test (16 train + 8 eval, 1 epoch)

| Step | loss | grad_norm | mean_token_accuracy | epoch |
|---|---|---|---|---|
| 1 | 3.47 | 2.21 | 0.4318 | 0.25 |
| 2 | 3.98 | 3.05 | 0.4247 | 0.50 |
| 3 | 3.66 | 13.25 | 0.4490 | 0.75 |
| 4 | 3.35 | 2.36 | 0.4690 | 1.00 |

| Eval | 값 |
|---|---|
| eval_loss | 2.929 |
| eval_mean_token_accuracy | 0.4849 |
| eval_runtime | 8.5초 |
| train_runtime | 54.91초 |

### 6.3 Full v0 training (완료)

#### 6.3.1 Configuration

| 항목 | 값 |
|---|---|
| Train sample | 234 |
| Eval sample | 74 |
| Epochs | 3 |
| Batch | 1 |
| Gradient accumulation | 8 |
| Effective batch size | 8 |
| Total update steps | 90 |
| max_seq_length | 8192 |
| max_image_tokens | 512 |
| Learning rate | 2e-4 (cosine warmup 5%) |
| 실제 train_runtime | **1979초 (32분 59초)** |
| train_samples_per_second | 0.355 |
| train_steps_per_second | 0.045 |

#### 6.3.2 Train loss 추이

| step | epoch | train_loss | grad_norm | mean_token_accuracy |
|---|---|---|---|---|
| 5 | 0.17 | 3.488 | 1.174 | 0.4489 |
| 10 | 0.34 | 2.754 | 0.590 | 0.4947 |
| 15 | 0.51 | 2.329 | 0.253 | 0.5265 |
| 20 | 0.68 | 1.982 | 0.300 | 0.5784 |
| 25 | 0.85 | 1.480 | 0.694 | 0.6928 |
| 35 | 1.17 | 0.7529 | 0.143 | 0.8765 |
| 40 | 1.34 | 0.7534 | 0.132 | 0.8804 |
| 45 | 1.51 | 0.6815 | 0.106 | 0.8911 |
| 50 | 1.68 | 0.5819 | 0.136 | 0.9060 |
| 55 | 1.85 | 0.6355 | 0.114 | 0.9010 |
| 65 | 2.17 | 0.5408 | 0.135 | 0.9153 |
| 70 | 2.34 | 0.6006 | 0.099 | 0.9077 |
| 75 | 2.51 | 0.6461 | 0.108 | 0.9024 |
| 80 | 2.68 | 0.6208 | 0.131 | 0.9041 |
| 85 | 2.85 | 0.5602 | 0.087 | 0.9147 |
| 90 | 3.00 | 0.6092 | 0.190 | 0.9060 |

avg train_loss (전체): **1.143**.

#### 6.3.3 Eval (epoch 단위, 74 sample 5 task)

| epoch | eval_loss | eval_token_accuracy | eval_runtime |
|---|---|---|---|
| 1 | 0.7699 | 0.8741 | 56.5s |
| 2 | 0.6330 | 0.9011 | 55.8s |
| 3 | **0.6108** | **0.9061** | 55.7s |

#### 6.3.4 Checkpoint

| 항목 | 값 |
|---|---|
| 경로 | `ckpt/qwen25vl-korus-lora-v0/` |
| adapter_model.safetensors | 566 MB |
| Total ckpt 크기 | 5.4 GB (checkpoint-30/60/90 + optimizer state 포함) |
| 포함 파일 | adapter_config.json, processor_config.json, tokenizer.json (11 MB), chat_template.jinja, README.md, training_args.bin |

#### 6.3.5 ⚠️ Eval 해석 주의

**현재 eval acc 0.9061은 진짜 generalization 지표가 아님.**

| 항목 | 값 |
|---|---|
| Split 단위 | task_id 단위 (예: `view_completed_00` vs `_03`) |
| Seed-level disjoint? | **No** — 같은 seed의 다른 paraphrase가 train/eval 양쪽에 있음 |
| Eval task 5개 | circulate_pending_01, view_doc_register_01, view_doc_register_03, view_in_progress_02, view_salary_statement_03 |
| 같은 seed의 train task | circulate_pending_00/02/03, view_doc_register_00/02, view_in_progress_00/01/03, view_salary_statement_00/01/02 |

→ 모델은 같은 메뉴·UI 패턴을 본 적 있음. 토큰 다음 위치 예측은 쉬움.
→ **진짜 일반화는 unseen seed (예: 결재작성, 첨부파일)** 에서 측정해야 함 — 다음 세션 Phase 1 v1 + Phase 4.

### 6.4 PLAN.md 대비 hyperparameter 차이

| 항목 | PLAN.md | 실제 |
|---|---|---|
| LoRA r | 32 | **16** (smoke 단계 보수) |
| LoRA alpha | 64 | **32** |
| Batch | 2 | **1** |
| max_seq_length | 16384 | **8192** |
| Image token cap | (미명시) | **512** |
| Flash-attention 2 | 사용 | **미사용 (SDPA)** |

---

## 7. 못한 것 — 사유 명시

### 7.1 100 trajectory 미달성 (24/100)

| 사유 | 영향 |
|---|---|
| Mock 결재선 setup 미수행 | 결재작성 카테고리 (52 task) 수집 불가 |
| 첨부파일 카테고리 (8 task) 수집 불가 | 본인 PC 파일 또는 활성 결재 폼 필요 |
| 결재선설정 카테고리 (8 task) 수집 불가 | 저장 액션 mutating 위험 |
| 환경설정 카테고리 (4 task) 수집 불가 | 사용자 prefs 변경 위험 |
| KORUS 세션 만료 (3.5시간 후) | view_year_end_tax 4 task 중 2 redirect, 2 미수집 |

→ v0는 **순수 read-only 카테고리(문서조회 + 결재처리) 24개**로 한정.

### 7.2 Phase 4 (vLLM 추론 평가) 미진행

| 사유 | 비고 |
|---|---|
| 시간 부족 | Phase 0~3에 28시간 소요, eval은 추가 1~2시간 필요 |
| `--extra serve` 설치 미수행 | vLLM 약 2 GB dep |
| 24 trajectory에서 학습된 모델은 underfit 가능성 높음 | 평가해도 의미 적음 |

→ 다음 세션에서 mock 결재선 setup + 더 많은 trajectory 수집 후 진행.

### 7.3 Flash-attention 2 미사용

| 사유 | 영향 |
|---|---|
| B200 + CUDA 13 호환 wheel 미확인 | 빌드 시간 길어 회피 |
| SDPA로 대체 | B200에서 성능 차이 미미 (긴 sequence에선 차이 발생) |

---

## 8. 디버깅·반복 — 시간 잡아먹은 이슈

| # | 이슈 | 진단 시간 | 영향 |
|---|---|---|---|
| 1 | pytest가 `tests/cnu_agent/__init__.py`로 실제 `cnu_agent/` shadow → import 실패 | 10분 | pyproject pytest config 변경 (importlib mode + pythonpath) |
| 2 | `scripts/save_auth.py`의 `input()`이 Claude Code `!` prefix에서 즉시 EOF | 15분 | sentinel 파일 폴링 fallback 추가 |
| 3 | discover.py 1차: LLM call 90초 timeout 4회 연속 → process kill | 30분 | llm_timeout=300, max_history_items=10 |
| 4 | collect.py `steps.jsonl` 4.7MB / step (base64 image 중복) | 15분 | image content를 file:// path 참조로 치환 → 87% 감소 |
| 5 | mutating-guard false-positive 13건 (`submit` substring, done.text 보고문) | 30분 | 정규식 재설계 (click description + 액션 이름만 검사) |
| 6 | KORUS 세션 만료 후 25번째 task부터 로그인 redirect | 즉시 감지 | bulk kill, 23 trajectory 보존 + 2 bad 삭제 |
| 7 | Mac venv에 `huggingface_hub` 미설치 | 5분 | `uv pip install` |
| 8 | Mac → B200 SSH 불가 → rsync 사용 불가 | 20분 | HF Hub private dataset 우회 |
| 9 | `data/korus_*.jsonl`에 file:// abs path → B200 portable 안 됨 | 10분 | repo-relative 경로로 변경 + re-conversion |
| 10 | `Dataset.from_list` Arrow schema 충돌 (content str/list 혼합) | 15분 | messages를 JSON string으로 직렬화 |
| 11 | Qwen2-VL processor `torchvision` 의존 | 5분 | `pip install torchvision` |
| 12 | screenshot 2560x1271 → 4095 image token, max_seq=4096에서 truncation 불일치 | 15분 | processor.image_processor.max_pixels cap 추가 |

총 디버깅 시간: 약 **3시간**.

---

## 9. 시간 분포 추정

| 단계 | 작업 시간 | 디버깅·재시도 |
|---|---|---|
| Phase 0a | 30분 | 30분 |
| Phase 0b | 2시간 | 2시간 |
| Phase 1 v0 | 3시간 | 3시간 |
| Phase 2 | 30분 | 30분 |
| Phase 3 환경 setup | 30분 | 30분 |
| Phase 3 smoke + full | 30분 + 28분 | 1시간 |
| Mac↔B200 데이터 전송 | 30분 | 30분 |
| **합계** | **약 14시간 본 작업** | **약 14시간 디버깅·재시도** |

→ 실제 작업 시간 기준 28시간 (수면 시간 제외, 반복적 시도 포함).

---

## 10. 다음 세션 — 우선순위

| 우선순위 | 항목 | 예상 시간 |
|---|---|---|
| 1 | **Seed-disjoint eval split 재구성** (지금 eval은 seed 누설 — `--eval-by-seed` 플래그 추가) | 30분 |
| 2 | **Phase 4 v0 — 현재 ckpt로 unseen seed 추론 테스트** (vLLM 또는 transformers `.generate`로 5 task 실행) | 2~3시간 |
| 3 | Mock 결재선 setup (KORUS에서 originator=최종결재자=본인 결재 1~2개 생성) | 30분 (수동) |
| 4 | Phase 1 v1 — 결재작성 13 seed × 4 variant = 52 task 추가 수집 | 6~8시간 |
| 5 | Phase 1 v1 — 첨부파일 / 결재선설정 / 환경설정 추가 수집 (저위험) | 2~3시간 |
| 6 | Phase 2 재변환 + Phase 3 재학습 (LoRA r=32, max_seq=16384, 100+ sample) | 2시간 |
| 7 | flash-attention 2 빌드 (B200 + CUDA 13) | 1~2시간 |

**총 다음 세션 추정**: 약 14~20시간.

---

## 11. ⚠️ ToS / Privacy 메모

| 항목 | 상태 |
|---|---|
| Anthropic Commercial Terms — Claude를 다른 LLM distillation에 사용 | ⚠️ 사용자 위험 인지 후 진행 결정 |
| 본인 KORUS 계정 사용 | ✅ private repo + .env에 자격증명 (gitignored) |
| 동료 이름·문서번호 등 PII trajectory 포함 | ⚠️ 인지 — 학습 데이터에 그대로 들어감, 추후 PII 스크럽 단계 검토 |
| HF Hub private dataset (`chaeminu/cnu-korus-trajectories-v0`) | ✅ private 설정 |
| Mutating action 클릭 | ✅ 0건 (audit 검증) |

---

## 12. Repo 상태

| 항목 | 값 |
|---|---|
| Branch | main |
| Commits 추가 | 7 (370f392 → 22ee49b) |
| Commit 분리 | Phase 0a / 0b / 1 v0 / 2 / 2-fix / 3 / 3-fix |
| Lines added (전체) | 약 2,500 |
| Lines deleted | 약 80 |
| 테스트 통과율 | 40/40 (100%) |
| Push 상태 | origin/main 최신 (B200 git pull로 동기화) |

---

## Appendix A — 재현 명령어

### 맥북 (Phase 0~2)
```bash
git clone https://github.com/Sunkist18/cnu-ai-agent.git
cd cnu-ai-agent
uv venv --python 3.11
uv sync --extra dev

# storage_state 캡처 (1회)
python scripts/save_auth.py

# Discovery
python -m cnu_agent.teacher.discover --max-steps 35

# Curate (수동 또는 Claude 자동 trim)

# Paraphrase
python -m cnu_agent.teacher.paraphrase --variants 4

# Trajectory 수집
python -m cnu_agent.teacher.collect --categories "문서조회,결재처리" --max-steps 20

# 변환
python -m cnu_agent.data.trajectory_to_sft

# 데이터 업로드 (HF Hub)
hf upload chaeminu/cnu-korus-trajectories-v0 trajectories trajectories --repo-type dataset
hf upload chaeminu/cnu-korus-trajectories-v0 data data --repo-type dataset
```

### B200 (Phase 3)
```bash
cd /NHNHOME/WORKSPACE/26moe002_H/mwchoi
git clone https://github.com/Sunkist18/cnu-ai-agent.git
cd cnu-ai-agent
uv venv --python 3.11
uv sync --extra training
.venv/bin/pip install torchvision

# 데이터 다운로드
hf download chaeminu/cnu-korus-trajectories-v0 --repo-type dataset --local-dir .

# Qwen 모델 사전 다운로드
hf download Qwen/Qwen2.5-VL-32B-Instruct

# 학습
python -m cnu_agent.training.qlora_sft \
  --train data/korus_train.jsonl \
  --eval  data/korus_eval.jsonl \
  --out   ckpt/qwen25vl-korus-lora-v0 \
  --epochs 3 --max-seq 8192 --batch 1 --grad-accum 8 \
  --no-flash-attn --max-image-tokens 512
```
