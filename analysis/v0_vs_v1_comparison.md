# KORUS Agent — v0 vs v1 비교

작성일 **2026-05-12**

---

## 1. 전체 요약

| 지표 | v0 | v1 demo (first batch) |
|---|---|---|
| 수집 trajectory | 24 | 10 |
| Teacher success rate | 13 / 24 = **54.2%** | 8 / 10 = **80.0%** |
| 카테고리 커버 | 2 (read-only) | 5 |
| 평균 step / trajectory | 12.8 | 11.4 |
| 평균 step (success만) | 13.6 | 6.75 |
| mutating click | 0 / 308 step | 0 / 114 step |
| 학습 결과 (LoRA) | eval_loss 0.611 / token_acc 0.906 | (v1 데이터 확장 후 재학습) |
| 데모 영상 | — | 10 mp4 + 합본 3분 22초 |

---

## 2. 데이터 수집 단위

| 단위 | v0 | v1 (계획) | v1 (now demo) |
|---|---|---|---|
| Seed (curated) | 25 | 24 | — |
| Paraphrase task | 100 | 96 | — |
| 실제 시도 trajectory | 28 | 96 (full) | 10 (demo) |
| 실제 수집 trajectory | 24 | 96 | 10 |

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

| Fix | 변경 |
|---|---|
| F1 | `cnu_agent/teacher/collect.py` — full_task prefix에 `Done 평가 규칙` 추가 (페이지 도달 + 결과 확인 → success=True, 데이터 0건 OK) |
| F2 | `discovery/seeds_curated.json` — `view_doc_register` seed 제거 (25 → 24 seed), paraphrase 재실행으로 task 100 → 96 |

### 예상 → 실측 비교

| 단계 | 예상 | 실측 (v1 demo 10 trajectory) |
|---|---|---|
| v0 그대로 | 54.2% | — |
| F1 (재분류) | 66.7% | — |
| F1 + F2 | 80.0% | **80.0% (8/10)** ✅ |

→ **예상 그대로 80% 달성**.

---

## 6. v1 demo 신규 수집 결과 (10 task 100%/80%)

### 6.1 Per-task 결과

| Task | 카테고리 | v1 결과 | v1 step | v0 동일 seed 결과 | v0 동일 seed step |
|---|---|---|---|---|---|
| approve_pending_01 | 결재처리 | ✅ | **3** | 2/4 success | 11.2 avg |
| approve_pending_03 | 결재처리 | ✅ | **3** | 2/4 success | 11.2 avg |
| circulate_pending_03 | 결재처리 | ✅ | 6 | 3/4 success | 7.0 avg |
| view_completed_01 | 문서조회 | ✅ | 8 | 3/4 success | 16.5 avg |
| view_in_progress_00 | 문서조회 | ✅ | 8 | 4/4 success | 13.0 avg |
| view_salary_statement_01 | 문서조회 | ✅ | 9 | 1/4 success (v0 self-fail) | 13.5 avg |
| view_year_end_tax_00 | 문서조회 | ✅ | 9 | 0/2 success (v0 세션 만료) | 3.0 avg (login redirect) |
| config_personal_settings_00 | 환경설정 (신규) | ✅ | 8 | (미수집) | — |
| setup_approval_line_00 | 결재선설정 | ❌ | 23 | (미수집) | — |
| favorite_approval_line_00 | 결재선설정 | ❌ | 25 | (미수집) | — |

### 6.2 카테고리별

| 카테고리 | v1 demo success | v1 demo total | success rate |
|---|---|---|---|
| 결재처리 | 3 | 3 | 100% |
| 문서조회 | 4 | 4 | 100% |
| 환경설정 | 1 | 1 | 100% |
| 결재선설정 | 0 | 2 | 0% |
| **합계** | **8** | **10** | **80%** |

### 6.3 핵심 관찰

| 관찰 | 의미 |
|---|---|
| `approve_pending_01` v0 19 step → v1 3 step | F1 prompt가 "결재대기함 도달 후 0건 인식 = success" 즉시 판단 |
| `approve_pending_03` v0 17 step fail → v1 3 step success | F1 prompt 효과 추가 검증 |
| `view_salary_statement_01` v0 15 step self-fail → v1 9 step success | F1 prompt가 self-fail 정정 (data empty → still success) |
| `view_year_end_tax_00` v0 3 step (login redirect) → v1 9 step success | 세션 만료 fix (재인증) + F1 작동 |
| 환경설정 신규 카테고리 첫 시도 success | F1 적용 + read-only 안전 prompt가 새 카테고리에서도 동작 |
| 결재선설정 2건 fail (메뉴 not found) | view_doc_register와 같은 패턴 — seed의 `where` path 추정값이 실제 KORUS에 부재. v1+ 에서 seed 제거 또는 path 교정 필요 |

---

## 7. v0 → v1 step 효율 비교

| seed | v0 평균 step | v1 평균 step | 감소 |
|---|---|---|---|
| approve_pending | 11.2 | 3.0 | -73% |
| circulate_pending | 7.0 | 6.0 | -14% |
| view_completed | 16.5 | 8.0 | -52% |
| view_in_progress | 13.0 | 8.0 | -38% |
| view_salary_statement | 13.5 | 9.0 | -33% |

→ F1 prompt가 navigation 효율 크게 개선. 평균 약 -40%.

---

## 8. 학습 결과 (v0)

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

## 9. 학습 epoch별 추이

| Epoch | Train loss (avg) | Eval loss | Eval token acc |
|---|---|---|---|
| 0.17 (step 5) | 3.488 | — | — |
| 0.85 (step 25) | 1.480 | — | — |
| 1.00 (step 30) | — | 0.7699 | 0.8741 |
| 2.00 (step 60) | — | 0.6330 | 0.9011 |
| 3.00 (step 90) | 0.6092 | **0.6108** | **0.9061** |

---

## 10. 안전성 검증

| 항목 | v0 | v1 demo |
|---|---|---|
| Mutating click 시도 | 0 | 0 |
| 검사 step 수 | 308 | 114 |
| 검사 방법 | `interacted_element.ax_name` ground-truth audit | 동일 |
| 모달/팝업 처리 | 취소·X 만 (Escape send_keys 기록) | 동일 |
| 세션 만료 처리 | 멈춤 + 기록 (v0에서 25번째 task 직전 발생) | v1 신규 인증, 만료 안 됨 |

---

## 11. 안전 가드 layer

| Layer | 역할 |
|---|---|
| DISCOVERY/COLLECT prompt | "절대 클릭 금지" 명시 + read-only 모드 강조 |
| `_scan_mutating` 정규식 | click 액션 description/text + 정해진 action name 매칭 |
| `_MUTATING_BLOCKED.json` 자동 저장 | 의심 step 별도 보존 (수동 검토용) |
| `scripts/audit_trajectories.py` | history.json의 `interacted_element` 사후 ground-truth audit |
| Browser `allowed_domains=*.korus.ac.kr,*.cnu.ac.kr` | 외부 사이트 우회 차단 |

---

## 12. 코드·데이터 산출물

| 카테고리 | v0 | v1 추가 |
|---|---|---|
| 코드 라인 | 약 2,500 | +400 (analysis/audit/video script) |
| 테스트 | 40 / 40 PASS | 동일 |
| Seed | 38 enumerated, 25 curated | view_doc_register 제거 (24 curated) |
| Task | 100 paraphrase | 96 (24 seed × 4 variant) |
| Trajectory | 24 (90 MB) | 10 demo (~40 MB) |
| 학습 데이터 | train 234 / eval 74 | (v1 확장 후 재변환) |
| Adapter | 566 MB | (v1 데이터로 재학습 예정) |
| 데모 영상 | — | 10 mp4 + ALL.mp4 (3분 22초, 2.7 MB) |

---

## 13. 다음 미팅 액션 진행 상황

| # | 액션 | 상태 |
|---|---|---|
| A1 | 성능 비교 평가 (Gemini, 범용 모델) | 보류 (key 대기) |
| A2 | 실패 원인 분석 + 연구실 공유 | ✅ `analysis/v0_failure_modes.md` |
| A3 | 목표 success 80% 상향 | ✅ **달성** (v1 demo 8/10 = 80%) |
| A4 | 실험 결과 비디오 녹화 | ✅ 10 mp4 + 합본 3분 22초 |
| A5 | 쓰기 위주 태스크 | 보류 (교수님 데이터 선정 대기) |
| A6 | B200 환경 설정 가이드 | 생략 |
| A7 | 세션 중단 자동 재인증 | v1 full collect 전 fix 예정 |

---

## 14. 영상 파일 목록

| 영상 | 길이 | 크기 |
|---|---|---|
| approve_pending_01.mp4 | 6초 | 114 KB |
| approve_pending_03.mp4 | 6초 | 115 KB |
| circulate_pending_03.mp4 | 10초 | 178 KB |
| view_completed_01.mp4 | 14초 | 198 KB |
| view_in_progress_00.mp4 | 12초 | 193 KB |
| view_salary_statement_01.mp4 | 16초 | 230 KB |
| view_year_end_tax_00.mp4 | 16초 | 195 KB |
| config_personal_settings_00.mp4 | 14초 | 234 KB |
| setup_approval_line_00.mp4 (fail) | 44초 | 752 KB |
| favorite_approval_line_00.mp4 (fail) | 48초 | 470 KB |
| **ALL.mp4 (합본)** | **3분 22초** | **2.7 MB** |
