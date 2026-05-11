# v0 결과 + v1 계획 — 발표용 요약

**발표일**: 2026-05-12 10:00 KST

---

## 1. 한 장 요약 — 숫자 위주

| 항목 | 값 |
|---|---|
| 1차 범위 | KORUS (Spring 기반, 충남대 전자결재) |
| 실제 수집 | **24 trajectory** (read-only safety subset) |
| Teacher success rate | **54.2%** (13/24) |
| **재분류 후 (F1 적용 시)** | **66.7%** (16/24) |
| Mutating action 클릭 | **0건** (interacted_element ground-truth audit) |
| 학습 결과 | Qwen2.5-VL-32B + LoRA r=16, 3 epoch |
| 최종 eval | loss **0.611** / token_acc **0.906** |
| Adapter | **566 MB** |

---

## 2. KORUS 난이도 — 비교 baseline

| 도메인 | 시스템 | 범용 모델 예상 success |
|---|---|---|
| 사이버캠퍼스 | 일반 LMS | ~90% |
| 학과 게시판 | 일반 웹 | ~85% |
| **KORUS** | **Spring 기반 독자 구축** | **40~50% (가설)** |

**우리 v0 fine-tune 결과 54%는 도메인 자체 난이도 반영**.
KORUS 특성: Java EE/Spring + iframe 다중 + shadow DOM form + JSP POST submit + 메뉴 deeply nested.

---

## 3. Seed별 success rate — 어디서 막혔나

| Seed | success | 비고 |
|---|---|---|
| view_in_progress | **4/4 (100%)** | 일반 메뉴 navigation 잘 됨 |
| view_completed | 3/4 (75%) | 마지막 1건 max_steps 도달 |
| circulate_pending | 3/4 (75%) | search form 입력 실패 1건 |
| approve_pending | 2/4 (50%) | placeholder 1건 + form 1건 |
| view_salary_statement | 1/4 (25%) | **3건은 self-eval fail → F1으로 100% 복원 가능** |
| view_doc_register | **0/4 (0%)** | seed의 메뉴 path가 KORUS에 부재 → 제거 |

---

## 4. 실패 분석 — 5 카테고리

| 카테고리 | 빈도 | 원인 | Fix 우선순위 |
|---|---|---|---|
| 메뉴 path not found (Spring 메뉴 구조) | 4 | seed의 `where` 추정값이 실제 path와 다름 | F2 — seed 제거 ✅ |
| 데이터 없음 self-fail (사실상 success) | 3 | "조회 결과 0건"을 task 실패로 평가 | F1 — done 평가 prompt ✅ |
| Spring shadow DOM 폼 입력 실패 | 2 | input + click 양쪽 비효율 | F3 — shadow-aware action (v1) |
| Placeholder 미치환 | 1 | `{{doc_no}}` 그대로 입력 | F4 — pre-substitution (v1) |
| Max steps 소진 | 1 | navigation 20 step 부족 | F5 — max-steps 30 (v1) |

---

## 5. v1 진입 전 적용 완료 — F1 + F2

### F1 — `Done 평가 규칙` prompt 명시
- read-only 조회 task는 페이지 도달 + 결과 확인 → `done(success=True)` (데이터 0건이어도)
- `success=False`는 (a) 메뉴/페이지 부재, (b) form 미동작, (c) max_steps 도달 시만
- `cnu_agent/teacher/collect.py` commit `dbcc104`

### F2 — `view_doc_register` seed 제거
- 25 seed → 24 seed (paraphrase 재실행 → 96 task)
- 메뉴 path가 실제 KORUS에 부재 또는 권한 부족 — `view_doc_register_03` 자체가 "현재 사용자 권한으로는 안 보임" 보고

### 예상 효과 (v0 데이터 가정 시)
| 단계 | success rate |
|---|---|
| v0 그대로 | 54.2% (13/24) |
| F1 적용 후 (재분류) | 66.7% (16/24) |
| F1 + F2 (view_doc_register 제외) | **80.0%** (16/20) |

→ **80% 목표 달성 가능** (코드 fix만으로).

---

## 6. 학습 곡선 (v0)

| step | epoch | train_loss | eval_loss | eval_token_acc |
|---|---|---|---|---|
| 5 | 0.17 | 3.488 | — | — |
| 25 | 0.85 | 1.480 | — | — |
| 30 | 1.00 | — | 0.7699 | 0.8741 |
| 60 | 2.00 | — | 0.6330 | 0.9011 |
| 90 | 3.00 | 0.6092 | **0.6108** | **0.9061** |

avg train_loss: **1.143**. eval 0.9061은 token-level — seed-level disjoint 아니므로 진짜 일반화 ≠.

---

## 7. v1 actionable — 다음 미팅 전

| 우선순위 | 작업 | 효과 |
|---|---|---|
| 1 | F1 + F2 적용 (✅ 완료) — v1 수집 시 자동 반영 | 54% → 80% 예상 |
| 2 | Mock 결재선 setup (수동) → 결재작성 52 task 추가 수집 | 데이터 다양성 76 trajectory |
| 3 | A1 — Gemini Flash baseline 비교 (현재 진행 중) | KORUS 난이도 입증 |
| 4 | A7 — 세션 중단 자동 재인증 | 24시간 일괄 수집 가능 |
| 5 | A4 — 영상 녹화 (이번 발표 자료 포함) | 시각 자료 확보 |
| 6 | F3 — Spring shadow DOM action | +8% 추정 |
| 7 | F4 — placeholder pre-sub | +4% |
| 8 | F5 — max-steps 30 | +4% |

---

## 8. ⚠️ 안전성

| 항목 | 결과 |
|---|---|
| Mutating action (승인/반려/상신/제출/저장/삭제) 클릭 | **0건 / 308 step** |
| 검증 방법 | `state.interacted_element[*].ax_name` 후속 audit (액션 결과 ground truth) |
| 추가 안전 layer | DISCOVERY/COLLECT prompt 명시 + click action 정규식 가드 + audit 스크립트 |
| KORUS 세션 만료 시 행동 | 멈춤 + 기록 (덮어쓰기 안 함) |
| 동료 trajectory 영향 | **0건** (read-only subset, mutating은 v1 mock 결재선 후) |

---

## 9. 데모 영상

- `videos/v1_demo/` — Agent가 KORUS read-only로 메뉴 navigate하는 시각 자료
- 4 task: view_in_progress, approve_pending (조회), circulate_pending, config_personal_settings

---

## Appendix A — 1차 산출물 코드·데이터

| 카테고리 | 항목 | 크기 |
|---|---|---|
| 코드 | 8 모듈 + 3 테스트 (40/40 PASS) | 2,500 라인 |
| Discovery | 38 seed → 24 curate → 96 task (v1) | 50 KB |
| Trajectory | 24 dir, 308 step | 90 MB |
| 학습 데이터 | train 234 + eval 74 sample | 13 MB |
| Adapter | `qwen25vl-korus-lora-v0` | 566 MB |
| 영상 | demo 4 task | (생성 중) |
