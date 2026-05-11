# KORUS Agent — v0 vs v1 비교

작성일 **2026-05-12**

---

## 1. 전체 요약

| 지표 | v0 | v1 (in progress) |
|---|---|---|
| 수집 trajectory | 24 | 4 (demo, 추가 6개 진행 중) |
| Teacher success rate | 13/24 = **54.2%** | 4/4 = **100%** (demo subset) |
| 카테고리 커버 | 2 (read-only) | 5 (read-only + 환경설정 + 결재선설정) |
| 평균 step / trajectory | 12.8 | 6.25 |
| mutating click | 0 / 308 step | 0 / 25 step |
| 학습 결과 | LoRA r=16, eval_loss 0.611, token_acc 0.906 | (v1 데이터 확장 후 재학습) |

---

## 2. 데이터 수집 단위

| 단위 | v0 | v1 (계획) | v1 (now) |
|---|---|---|---|
| seed (curated) | 25 | 24 | 24 |
| paraphrase task | 100 | 96 | 96 |
| 실제 trajectory 시도 | 28 | 96 | 10 (4 + 6 진행 중) |
| 실제 수집 trajectory | 24 | 96 | 4 (10 진행 중) |
| 카테고리 분포 | 결재처리 8 / 문서조회 16 | 결재처리 8 / 문서조회 16 / 첨부 8 / 결재선 8 / 환경 4 / 결재작성 52 | demo 5 카테고리 |

---

## 3. Seed별 v0 success rate

| Seed | v0 success | 비고 |
|---|---|---|
| view_in_progress | 4 / 4 = 100% | 기본 메뉴 navigation 잘 됨 |
| view_completed | 3 / 4 = 75% | 1건 max_steps 도달 |
| circulate_pending | 3 / 4 = 75% | 1건 search form 실패 |
| approve_pending | 2 / 4 = 50% | placeholder 1 + form 1 |
| view_salary_statement | 1 / 4 = 25% | 3건 self-fail (F1으로 복구) |
| view_doc_register | 0 / 4 = 0% | seed 자체 path 불일치 → 제거 |

---

## 4. v0 실패 모드 카테고리

| 카테고리 | 빈도 | 대표 trajectory | Fix |
|---|---|---|---|
| 메뉴 path not found | 4 | view_doc_register_00/01/02 | F2 — seed 제거 |
| 데이터 없음 self-fail | 3 | view_salary_statement_01/02/03 | F1 — done 평가 prompt |
| Spring shadow DOM form | 2 | approve_pending_03, circulate_pending_02 | F3 (v1+) |
| Placeholder 미치환 | 1 | approve_pending_02 | F4 (v1+) |
| Max steps 도달 | 1 | view_completed_02 | F5 — max-steps 30 |

---

## 5. F1 + F2 적용 (v1 진입 전 코드 fix)

| Fix | 변경 | 효과 |
|---|---|---|
| F1 | `cnu_agent/teacher/collect.py` — full_task prefix에 `Done 평가 규칙` 추가 (페이지 도달 + 결과 확인 → success=True, 데이터 0건 OK) | self-fail 3건 복구 |
| F2 | `discovery/seeds_curated.json` — `view_doc_register` seed 제거 (25 → 24 seed), paraphrase 재실행으로 task 100 → 96 | 메뉴 부재 4건 제외 |

### 예상 success rate (v0 데이터 적용 시)

| 단계 | 분자 | 분모 | rate |
|---|---|---|---|
| v0 그대로 | 13 | 24 | 54.2% |
| F1 (재분류) | 16 | 24 | 66.7% |
| F1 + F2 (view_doc_register 제외) | 16 | 20 | **80.0%** |

---

## 6. v1 신규 demo 수집 결과 (4 task 완료)

| Task | 카테고리 | Success | v1 steps | v0 동일 seed steps |
|---|---|---|---|---|
| approve_pending_01 | 결재처리 | ✅ | **3** | 19 |
| circulate_pending_03 | 결재처리 | ✅ | 6 | 5 (v0 도 success) |
| view_in_progress_00 | 문서조회 | ✅ | 8 | 11 |
| config_personal_settings_00 | 환경설정 (신규) | ✅ | 8 | (v0 미수집) |
| **합계** | | **4 / 4 (100%)** | avg 6.25 | avg 11.7 |

### 관찰

| 관찰 | 의미 |
|---|---|
| `approve_pending_01` v0 19 step → v1 3 step | F1 prompt가 "결재대기함 도달 후 0건 인식 = success" 즉시 판단 |
| 환경설정 신규 카테고리 첫 시도 success | F1 적용 + read-only 안전 prompt가 새 카테고리에서도 동작 |
| 평균 step 12.8 → 6.25 | 불필요한 페이지 재방문 / max_steps 소진 감소 |

---

## 7. 학습 결과 (v0)

| Metric | v0 |
|---|---|
| Base model | Qwen2.5-VL-32B-Instruct (33.45B) |
| Trainable params | ~100M (LoRA r=16) |
| Train sample | 234 (19 task) |
| Eval sample | 74 (5 task) |
| Epochs | 3 |
| Effective batch size | 8 |
| max_seq_length | 8192 |
| max_image_tokens | 512 |
| train_runtime | 1979초 (B200 단일 GPU) |
| **eval_loss (epoch 3)** | **0.611** |
| **eval_token_accuracy** | **0.906** |
| ckpt 크기 | 5.4 GB (adapter 566 MB + 3 checkpoint) |

⚠️ eval은 같은 seed의 다른 paraphrase가 train/eval 양쪽 — seed-disjoint 아님.

---

## 8. 학습 epoch별 추이

| Epoch | Train loss (avg) | Eval loss | Eval token acc |
|---|---|---|---|
| 0.17 (step 5) | 3.488 | — | — |
| 0.85 (step 25) | 1.480 | — | — |
| 1.00 (step 30) | — | 0.7699 | 0.8741 |
| 2.00 (step 60) | — | 0.6330 | 0.9011 |
| 3.00 (step 90) | 0.6092 | **0.6108** | **0.9061** |

---

## 9. 안전성 검증

| 항목 | v0 | v1 (지금까지) |
|---|---|---|
| Mutating click 시도 | 0 | 0 |
| 검사 step 수 | 308 | 25 |
| 검사 방법 | `interacted_element.ax_name` ground-truth audit | 동일 |
| 모달/팝업 처리 | 취소·X 만 (Escape send_keys 1회 기록됨) | 동일 |
| 세션 만료 처리 | 멈춤 + 기록 (v0에서 25번째 task 직전 발생) | (v1 신규 인증, 만료 안 됨) |

---

## 10. 안전 가드 layer

| Layer | 역할 |
|---|---|
| DISCOVERY/COLLECT prompt | "절대 클릭 금지" 명시 + read-only 모드 강조 |
| `_scan_mutating` 정규식 | click 액션 description/text + 정해진 action name 매칭 |
| `_MUTATING_BLOCKED.json` 자동 저장 | 의심 step 별도 보존 (수동 검토용) |
| `scripts/audit_trajectories.py` | history.json의 `interacted_element` 사후 ground-truth audit |
| Browser `allowed_domains=*.korus.ac.kr,*.cnu.ac.kr` | 외부 사이트 우회 차단 |

---

## 11. 코드·데이터 산출물

| 카테고리 | v0 | v1 추가 |
|---|---|---|
| 코드 라인 | 약 2,500 | +200 (analysis/audit/video script) |
| 테스트 | 40 / 40 PASS | 동일 |
| Seed | 38 enumerated, 25 curated | view_doc_register 제거 (24 curated) |
| Task | 100 paraphrase | 96 (24 seed × 4 variant) |
| Trajectory | 24 (90 MB) | 4 demo + 6 진행 중 (예상 ~30 MB) |
| 학습 데이터 | train 234 / eval 74 | (v1 확장 후 재변환) |
| Adapter | 566 MB | (v1 데이터로 재학습 예정) |
| 데모 영상 | — | 4 mp4 + ALL.mp4 (40초, 697 KB) |

---

## 12. 다음 미팅 액션 진행 상황

| # | 액션 | 상태 |
|---|---|---|
| A1 | 성능 비교 평가 (Gemini, 범용 모델) | 보류 (key 대기) |
| A2 | 실패 원인 분석 + 연구실 공유 | ✅ `analysis/v0_failure_modes.md` |
| A3 | 목표 success 80% 상향 | F1+F2 코드 fix 완료, v1 측정 대기 |
| A4 | 실험 결과 비디오 녹화 | ✅ 4 mp4 + 합본 (`videos/v1_demo/`) |
| A5 | 쓰기 위주 태스크 | 보류 (교수님 데이터 선정 대기) |
| A6 | B200 환경 설정 가이드 | 작성 안 함 (생략) |
| A7 | 세션 중단 자동 재인증 | v1 collect 전 fix 예정 |
