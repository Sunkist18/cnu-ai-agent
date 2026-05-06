# CNU AI Agent — v0 진행 리포트

**작성일**: 2026-05-06
**작업자**: 최채민
**작업 환경**: 학교 맥북 (Phase 0~2) + B200 학습 서버 NVIDIA (Phase 3)
**Repo**: github.com/Sunkist18/cnu-ai-agent (private)

---

## 0. 한 줄 요약

| 항목 | 값 |
|---|---|
| 1차 범위 (계획) | KORUS 단일 도메인, 100 trajectory |
| 실제 수집 | 24 trajectory (read-only 카테고리) |
| 단계 진행 | Phase -1 → Phase 3 학습 완료 (전체 5단계 중 3단계) |
| 학습 결과 | Qwen2.5-VL-32B + LoRA r=16, train_loss 1.143 |
| 최종 eval | loss 0.611 / token_acc 0.906 (단, seed 누설 — §6.3.5 참조) |
| Teacher success rate | 13/24 (54%) — PLAN.md 목표 70% 미달 |
| Mutating action 클릭 | 0건 (audit 검증) |

---

## 1. 단계별 진행 + 산출물

| Phase | 작업 내용 | 산출물 | 상태 |
|---|---|---|---|
| **-1** Repo bootstrap | 디렉토리 skeleton, PLAN.md, CLAUDE.md, .gitignore | repo + 7 stub 파일 | ✅ |
| **0a** ChatClaudeCode | Claude Agent SDK를 browser-use BaseChatModel로 wrap. 단일 user-turn 직렬화, JSON schema 주입, 토큰 usage 매핑 | `cnu_agent/teacher/claude_code_llm.py` (320 라인) + 테스트 3건 + E2E smoke (python.org) | ✅ |
| **0b-i** Storage state 캡처 | KORUS 수동 로그인 후 쿠키 4개 (cnu.korus.ac.kr × 2 + sso.korus.ac.kr × 2) 저장 | `auth/korus_storage_state.json` | ✅ |
| **0b-ii** Discovery | browser-use Agent로 KORUS 메뉴 read-only 탐색, custom tool로 seeds.json 자동 저장 | `discovery/seeds.json` (38 seed, 6 카테고리) | ✅ |
| **0b-iii** Curate | 38 → 25로 trim (mock 부담 / `(추정)` 메뉴 / 특수 권한 제거) | `discovery/seeds_curated.json` (25 seed) | ✅ |
| **0b-iv** Paraphrase | seed당 4 variant, 교수·조교·공무원 페르소나, placeholder 키 자동 검증 | `tasks/korus_100.json` (100 task) | ✅ |
| **1** Trajectory 수집 v0 | 28 task 시도, 24 성공. interacted_element ground-truth audit으로 mutating 0건 확인 | `trajectories/` 24 디렉토리 (308 step, 90 MB) | ✅ 부분 (24/100) |
| **2** ChatML 변환 | step별 → Qwen ChatML 1 sample. system / user(image+text) / assistant. task_id 단위 80/20 split. repo-relative 이미지 경로 | `data/korus_train.jsonl` (234) + `data/korus_eval.jsonl` (74) | ✅ |
| **3** LoRA SFT | Qwen2.5-VL-32B + LoRA r=16, bf16, gradient_checkpointing. multimodal 데이터 collator (chat template + image processor). 3 epoch | `ckpt/qwen25vl-korus-lora-v0/` (566 MB adapter) | ✅ |
| **4** vLLM 추론 평가 | (미진행) | — | ⏸ |

---

## 2. 산출물 — 파일·데이터 수치

### 2.1 코드

| 파일 | 라인 수 | 테스트 |
|---|---|---|
| `cnu_agent/teacher/claude_code_llm.py` | 320 | 3/3 PASS |
| `cnu_agent/teacher/discover.py` | 254 | E2E 검증 |
| `cnu_agent/teacher/paraphrase.py` | 203 | 출력 검증 |
| `cnu_agent/teacher/collect.py` | 521 | E2E 검증 |
| `cnu_agent/data/trajectory_to_sft.py` | 250 | 12/12 PASS |
| `cnu_agent/training/qlora_sft.py` | 308 | smoke 통과 |
| `scripts/save_auth.py` | 172 | — |
| `scripts/audit_trajectories.py` | 152 | — |
| `tests/cnu_agent/test_claude_code_llm.py` | 78 | 3/3 PASS |
| `tests/cnu_agent/test_seeds_and_tasks.py` | 159 | 10/10 PASS |
| `tests/cnu_agent/test_trajectory_conversion.py` | 178 | 12/12 PASS |

총 테스트: **40/40 PASS**.

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
| 최종 adapter | 566 MB (`ckpt/qwen25vl-korus-lora-v0/adapter_model.safetensors`) |

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
- 공간/동아리/제안 등 specialized 1건씩
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
| 기타 (my_emp_id, date, year, doc_no, amount, ...) | 1~2 |

sensitive_keys 있는 task: **34/100**.

---

## 4. Phase 1 v0 — Trajectory 수집 결과

### 4.1 카테고리별 Teacher success rate

| Seed | 시도 | success | 평균 step | 평균 size |
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
| Mac↔B200 데이터 전송 | HF Hub private dataset (`chaeminu/cnu-korus-trajectories-v0`) |

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

### 6.3 Full v0 training

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
| max_image_tokens | 512 (per image, 28×28 patch grid 기준) |
| Learning rate | 2e-4 (cosine, warmup 5%) |
| train_runtime | 1979초 |
| train_samples_per_second | 0.355 |

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

| epoch | eval_loss | eval_token_accuracy |
|---|---|---|
| 1 | 0.7699 | 0.8741 |
| 2 | 0.6330 | 0.9011 |
| 3 | **0.6108** | **0.9061** |

#### 6.3.4 Checkpoint 구성

| 파일 | 크기 |
|---|---|
| adapter_model.safetensors | 566 MB |
| tokenizer.json | 11 MB |
| checkpoint-30 / -60 / -90 (mid-training, optimizer state 포함) | 4.8 GB (3개 합계) |
| adapter_config.json + processor_config.json + chat_template.jinja + README.md + training_args.bin + tokenizer_config.json | < 100 KB |
| **합계** | 5.4 GB |

#### 6.3.5 ⚠️ Eval 해석 주의

**현재 eval acc 0.9061은 진짜 generalization 지표가 아님.**

| 항목 | 값 |
|---|---|
| Split 단위 | task_id 단위 (예: `view_completed_00` vs `_03`) |
| Seed-level disjoint? | **No** — 같은 seed의 다른 paraphrase가 train/eval 양쪽에 있음 |
| Eval task 5개 | circulate_pending_01, view_doc_register_01, view_doc_register_03, view_in_progress_02, view_salary_statement_03 |
| 같은 seed의 train task | circulate_pending_00/02/03, view_doc_register_00/02, view_in_progress_00/01/03, view_salary_statement_00/01/02 |

→ 모델은 같은 메뉴·UI 패턴을 본 적 있음. 토큰 다음 위치 예측은 쉬움.
→ **진짜 일반화는 unseen seed (예: 결재작성, 첨부파일)** 에서 측정해야 함.

### 6.4 PLAN.md 대비 hyperparameter 차이

| 항목 | PLAN.md | 실제 | 사유 |
|---|---|---|---|
| LoRA r | 32 | 16 | 24 trajectory 작은 셋이라 capacity 낮춤 |
| LoRA alpha | 64 | 32 | r 비례 축소 |
| Batch | 2 | 1 | 32B + 이미지 + max_seq 8192 메모리 보수 |
| max_seq_length | 16384 | 8192 | 단일 image 토큰 cap 512로 제한했으니 8192 충분 |
| Image token cap | (미명시) | 512 | KORUS screenshot 2560×1271 → native 4095 token, cap 필수 |
| Flash-attention 2 | 사용 | 미사용 (SDPA) | B200 + CUDA 13용 wheel 미확인 |

---

## 7. 못한 것 — 사유 명시

### 7.1 100 trajectory 미달성 (24/100)

| 사유 | 영향 |
|---|---|
| Mock 결재선 setup 미수행 | 결재작성 카테고리 (52 task) 수집 불가 |
| 첨부파일 카테고리 (8 task) 수집 불가 | 본인 PC 파일 또는 활성 결재 폼 필요 |
| 결재선설정 카테고리 (8 task) 수집 불가 | 저장 액션 mutating 위험 |
| 환경설정 카테고리 (4 task) 수집 불가 | 사용자 prefs 변경 위험 |
| KORUS 세션 만료 (장시간 운영 시) | view_year_end_tax 4 task 중 2 redirect, 2 미수집 |

→ v0는 **순수 read-only 카테고리(문서조회 + 결재처리) 24개**로 한정.

### 7.2 Phase 4 (vLLM 추론 평가) 미진행

| 사유 |
|---|
| `--extra serve` 설치 미수행 (vLLM 약 2 GB dep) |
| 24 trajectory 학습 모델은 underfit 가능성 — 평가해도 의미 적음 |
| Seed-level disjoint eval split이 우선 (지금은 paraphrase 누설) |

→ 다음 세션에서 mock 결재선 setup + 더 많은 trajectory 수집 후 진행.

### 7.3 Flash-attention 2 미사용

| 사유 | 영향 |
|---|---|
| B200 + CUDA 13 호환 wheel 미확인 | 빌드 시간 길어 회피 |
| SDPA로 대체 | B200에서 짧은 sequence 차이 미미. 긴 sequence·큰 batch 필요해지면 재검토 |

---

## 8. 알려진 한계 + 결정사항 모음

| # | 항목 | 결정 |
|---|---|---|
| 1 | KORUS DOM 누적 시 ChatClaudeCode 응답이 browser-use 기본 90s timeout 초과 | llm_timeout=300s, max_history_items=10, max_clickable_elements_length=20000 |
| 2 | `tests/cnu_agent/__init__.py`가 실제 `cnu_agent/` 패키지 shadowing | __init__.py 삭제 + pytest importlib mode + pythonpath=[`.`] |
| 3 | Claude Code의 `!` prefix는 stdin이 TTY 아님 → `input()` 즉시 EOF | `save_auth.py` sentinel 파일 폴링 fallback 추가 |
| 4 | `steps.jsonl`에 base64 image 중복으로 step당 4.7 MB | image content를 file:// path 참조로 치환 → step당 600 KB로 감소 |
| 5 | mutating-guard 정규식이 done.text 보고문·search 쿼리·placeholder까지 잡음 (false-positive 13건) | click 액션의 description/text + 정해진 mutating 액션 이름만 검사하도록 재설계. interacted_element ground-truth audit 별도 추가 |
| 6 | Mac↔B200 SSH 불가 (B200은 web shell만) | HF Hub private dataset (`chaeminu/cnu-korus-trajectories-v0`) 으로 우회 |
| 7 | `data/*.jsonl`에 file:// 절대 경로 → 머신 간 portable 안 됨 | repo-relative 경로 (`trajectories/<id>/screenshots/step_N.png`)로 변경 |
| 8 | `Dataset.from_list` Arrow schema mix (content str/list 혼합) | messages 통째로 JSON string으로 직렬화, collator에서 다시 파싱 |
| 9 | Qwen2-VL processor가 `torchvision` 의존 (이미지만 쓸 때도 video processor 로드) | `pip install torchvision` |
| 10 | KORUS screenshot 2560×1271 → native 4095 image token, max_seq=4096에서 truncation 불일치 | `processor.image_processor.max_pixels = 512 × 28 × 28`로 cap |
| 11 | `eval_loss` 0.611 / token_acc 0.906이지만 같은 seed의 paraphrase가 train/eval 양쪽 존재 | 다음 세션 1순위로 seed-disjoint split 재구성 |

---

## 9. Repo 상태

| 항목 | 값 |
|---|---|
| Branch | main |
| Commits 추가 | 8 (370f392 → 349779b) |
| Commit 분리 | Phase 0a / 0b / 1 v0 / 2 / 2-fix / 3 / 3-fix-1 / 3-fix-2 / docs |
| Lines added (전체) | 약 3,000 |
| Lines deleted | 약 80 |
| 테스트 통과율 | 40/40 (100%) |
| Push 상태 | origin/main 최신 |

---

## 10. 다음 세션 — 우선순위

| 우선순위 | 항목 |
|---|---|
| 1 | **Seed-disjoint eval split 재구성** (`--eval-by-seed` 플래그 추가, 현재 paraphrase 누설 문제 해결) |
| 2 | **Phase 4 v0** — 현재 ckpt로 unseen seed 추론 테스트 (vLLM 또는 transformers `.generate`로 5 task 실행, action accuracy + task success rate 측정) |
| 3 | **Mock 결재선 setup** (KORUS에서 originator=최종결재자=본인인 결재 1~2개 생성) |
| 4 | **Phase 1 v1** — 결재작성 13 seed × 4 variant = 52 task 추가 수집 |
| 5 | Phase 1 v1 — 첨부파일 / 결재선설정 / 환경설정 추가 수집 (저위험) |
| 6 | Phase 2 재변환 + Phase 3 재학습 (LoRA r=32, max_seq 16384, 100+ sample) |
| 7 | Flash-attention 2 빌드 (B200 + CUDA 13) |

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

## Appendix A — 재현 명령어

### 맥북 (Phase 0~2)

```bash
git clone https://github.com/Sunkist18/cnu-ai-agent.git
cd cnu-ai-agent
uv venv --python 3.11
uv sync --extra dev

# storage_state 캡처 (1회)
python scripts/save_auth.py

# Discovery (read-only KORUS 메뉴 탐색)
python -m cnu_agent.teacher.discover --max-steps 35

# Curate (수동 또는 자동 trim 스크립트)
# discovery/seeds_curated.json 생성

# Paraphrase (seed당 4 variant)
python -m cnu_agent.teacher.paraphrase --variants 4

# Trajectory 수집 (read-only 카테고리만)
python -m cnu_agent.teacher.collect --categories "문서조회,결재처리" --max-steps 20

# 안전 audit (mutating click 검사 + false-positive 정리)
python scripts/audit_trajectories.py

# ChatML 변환
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

# 학습 (full v0)
python -m cnu_agent.training.qlora_sft \
  --train data/korus_train.jsonl \
  --eval  data/korus_eval.jsonl \
  --out   ckpt/qwen25vl-korus-lora-v0 \
  --epochs 3 --max-seq 8192 --batch 1 --grad-accum 8 \
  --no-flash-attn --max-image-tokens 512
```
