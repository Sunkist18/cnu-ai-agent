# v2 Online Eval — vLLM 학교서버 + browser-use (Mac)

- 실행: 2026-05-18
- 모델: Qwen2.5-VL-32B-Instruct + 우리 LoRA (ckpt/checkpoint-273)
- vLLM: A6000×2, max_model_len=32768
- 환경: Mac M1 Max (browser-use) → 학교서버 vLLM API

## 결과

| 지표 | 값 |
|---|---|
| Total tasks | 60/60 |
| Raw success | 17/60 = **28%** |
| Clean success (placeholder 제외) | 14/41 = **34%** |
| Broken tasks ({placeholder}) | 19 (32%) — v2 paraphrase 버그 |
| 총 소요 | 8.3h (8.3분/task) |

## Per-seed Clean rate

| seed | category | clean | rate |
|---|---|---|---|
| draft_general | 결재작성 | 3/0 | **300%** (broken=4) |
| approve_pending_review | 결재처리 | 3/3 | **100%** (broken=1) |
| attach_approval_file | 첨부파일 | 2/2 | **100%** (broken=2) |
| approve_batch_similar | 결재처리 | 3/4 | **75%**  |
| draft_leave_request | 결재작성 | 2/3 | **67%** (broken=1) |
| incoming_inbox_review | 공문처리 | 1/4 | **25%**  |
| view_in_progress | 문서조회 | 1/4 | **25%**  |
| view_completed | 문서조회 | 1/4 | **25%**  |
| search_documents_by_keyword | 문서조회 | 1/4 | **25%**  |
| incoming_attachment_batch_download | 공문처리 | 0/4 | **0%**  |
| incoming_summary_email | 공문처리 | 0/0 | **0%** (broken=4) |
| approve_preview | 결재처리 | 0/2 | **0%** (broken=2) |
| draft_trip | 결재작성 | 0/2 | **0%** (broken=2) |
| attach_training_certificate | 첨부파일 | 0/2 | **0%** (broken=2) |
| view_or_submit_year_end_tax | 정산 | 0/3 | **0%** (broken=1) |

## Failure modes

- menu_not_found: 22
- login: 17
- max_steps: 4

## 학습 vs Inference 차이점

| | 학습 시 collect | inference (이번 v2) |
|---|---|---|
| Storage state | ✅ (post-login) | ❌ fresh-login (분포 밖) |
| use_vision | True | True ✓ |
| max_clickable_elements | 20000 | 20000 ✓ |
| Teacher LLM | Claude (full instruct) | korus-v2 (32B + LoRA) |

**결론**: 학습 데이터에 로그인 trajectory 0건 → inference에서 OOD
→ login fail 15건. 메뉴 깊이 깊은 seed들도 어려움.

## 다음 단계 (v3)

- 로그인 imperative + popup 처리 + 무한 retry 금지 prompt
- seed별 메뉴 경로 힌트 주입 (discovery/v2_paths.json)
- Done 호출 규칙 명시 (탐색 욕심 금지)