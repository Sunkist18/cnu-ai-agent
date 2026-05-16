# KORUS v1 task 후보 — 교수님 review용

총 **24 seed × 4 paraphrase = 96 task** (F2 적용 후, view_doc_register 제거됨)

각 seed 옆에 제가 본 **실사용 빈도 추정** 표시:
- 🔴 매일/매주 사용
- 🟡 매월 또는 자주
- 🟢 가끔
- ⚪ 드묾 (1년 1회 이하)
- ❌ v1 demo 실패 (seed path 의심)

---

## [결재작성] — 52 task / 13 seed

| 빈도 | Seed | 작업 | where |
|---|---|---|---|
| 🔴 | `draft_annual_leave_plan` | 월별연가계획신청 | 복무 > 연가관리 > 월별연가계획신청 |
| 🔴 | `draft_domestic_trip` | 국내출장신청 | 복무 > 국내출장 > 국내출장신청 |
| 🟡 | `draft_flexible_work` | 유연근무신청 (시차/재택) | 복무 > 유연근무 > 유연근무신청 |
| 🟡 | `draft_facility_complaint` | 시설물 민원 (수리 요청) | 시설관리 > 시설물 민원관리 > 시설물 민원 신청 |
| 🟡 | `draft_certificate` | 증명서 발급 (재직/경력/소득) | 인사관리 > 교원인사 > 증명서관리 > 증명서신청 |
| 🟢 | `draft_training` | 교육훈련 참가 신청 | 성과관리 > 교육훈련 > 교육훈련신청 > 교육훈련신청 |
| 🟢 | `draft_overseas_trip` | 국외출장신청 | 복무 > 국외출장 > 국외출장신청 |
| 🟢 | `draft_facility_rental` | 시설물 대여 (강당/회의실) | 시설관리 > 시설물 대여 > 시설물 대여 신청 |
| 🟢 | `draft_leave_absence` | 휴직신청 (육아/질병/유학) | 인사관리 > 교원인사 > 임용 > 휴직신청 |
| ⚪ | `draft_account` | 급여 계좌 변경 | 급여관리 > 급여기본 > 계좌관리 > 개인계좌신청 |
| ⚪ | `draft_concurrent_position` | 겸직신청 (외부 기관) | 복무 > 겸직관리 > 겸직신청 |
| ⚪ | `draft_return_work` | 복직신청 (휴직 종료) | 인사관리 > 교원인사 > 임용 > 복직신청 |
| ⚪ | `draft_proposal` | 제안공모 신청 (업무 개선 아이디어) | 성과관리 > 제안공모 > 제안신청 |

---

## [결재처리] — 8 task / 2 seed

| 빈도 | Seed | 작업 |
|---|---|---|
| 🔴 | `approve_pending` | 받은 결재 검토 (v1 demo ✅) |
| 🟡 | `circulate_pending` | 공람 문서 확인 (v1 demo ✅) |

---

## [문서조회] — 16 task / 4 seed

| 빈도 | Seed | 작업 |
|---|---|---|
| 🔴 | `view_in_progress` | 진행문서함 (내 진행 중 문서) (v1 demo ✅) |
| 🔴 | `view_completed` | 완료문서 조회 (v1 demo ✅) |
| 🟡 | `view_salary_statement` | 급여명세서 조회 (월별, v1 demo ✅) |
| ⚪ | `view_year_end_tax` | 연말정산 내역 조회 (연 1회, v1 demo ✅) |

---

## [첨부파일] — 8 task / 2 seed

| 빈도 | Seed | 작업 | 비고 |
|---|---|---|---|
| 🟡 | `attach_approval_file` | 결재 문서에 파일 첨부 | 활성 결재 폼 필요 (수집 시 mock 필요) |
| ⚪ | `attach_deduction_doc` | 연말정산 소득공제 서류 첨부 | 연 1회 |

---

## [결재선설정] — 8 task / 2 seed

| 빈도 | Seed | 작업 | 비고 |
|---|---|---|---|
| 🟡❌ | `setup_approval_line` | 결재선 지정 | v1 demo에서 메뉴 not found — path 재확인 필요 |
| ⚪❌ | `favorite_approval_line` | 결재선 즐겨찾기 | v1 demo에서 메뉴 not found — path 재확인 필요 |

---

## [환경설정] — 4 task / 1 seed

| 빈도 | Seed | 작업 |
|---|---|---|
| ⚪ | `config_personal_settings` | 개인환경 (레이아웃·메뉴) (v1 demo ✅) |

---

# 제가 추천하는 trim — 24 seed → 약 14 seed

## 우선 keep (🔴 + 🟡 + 검증됨) — 14 seed

### 결재작성 (8)
- `draft_annual_leave_plan` — 매월
- `draft_domestic_trip` — 빈번
- `draft_flexible_work` — 점점 늘어남
- `draft_facility_complaint` — 보통
- `draft_certificate` — 가끔 (재직증명 자주)
- `draft_overseas_trip` — 학회 참석 등
- `draft_leave_absence` — 빈도 낮지만 중요
- `draft_training` — 의외로 자주

### 결재처리 (2)
- `approve_pending` ✅
- `circulate_pending` ✅

### 문서조회 (3)
- `view_in_progress` ✅
- `view_completed` ✅
- `view_salary_statement` ✅

### 첨부파일 (1)
- `attach_approval_file` (보편)

---

## trim 후보 (⚪ + 메뉴 not found) — 10 seed

| Seed | 사유 |
|---|---|
| `draft_account` | 급여 계좌 변경 — 1~2년에 한 번, 단순 폼 |
| `draft_concurrent_position` | 겸직 — 매우 드묾, 복잡한 결재선 |
| `draft_return_work` | 복직 — 휴직 끝낼 때만, 일생 1~2회 |
| `draft_proposal` | 제안공모 — 자유 텍스트 위주, 실사용 적음 |
| `draft_facility_rental` | 시설 대여 — 학과별 차이, 빈도 낮음 |
| `view_year_end_tax` | 연말정산 — 연 1회, 시기 한정 |
| `attach_deduction_doc` | 소득공제 서류 — 연말정산 시기 한정 |
| `setup_approval_line` | 메뉴 not found — path 재확인 후 결정 |
| `favorite_approval_line` | 메뉴 not found — path 재확인 후 결정 |
| `config_personal_settings` | 1회성 setup |

---

## 최소 keep 옵션 (더 엄격) — 10 seed

만약 더 줄이고 싶으면 `draft_overseas_trip`, `draft_leave_absence`, `draft_training` 빼면 10 seed × 4 = 40 task. 핵심 read/write 패턴만.

---

## 교수님께 드릴 질문 후보

1. **결재선설정 메뉴 (`setup_approval_line`, `favorite_approval_line`)** — KORUS에서 실제 메뉴 path 어디? v1 demo에서 못 찾음
2. **연말정산 관련 2개 seed** — 5월에 수집한다면 시기 안 맞음 (연말정산은 1-2월). 빼도 OK?
3. **결재작성 13개 중 trim 우선순위** — 실제 본인 업무에서 자주 쓰시는 것 표시?
4. **신규 추가 후보** — 위 24 seed에 없는데 자주 쓰시는 작업?
