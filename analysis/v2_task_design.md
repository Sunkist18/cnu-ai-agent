# KORUS v2 task 재설계 — survey 응답 기반

설문 응답 **29건** (교수 15 + 조교 13 + 1 기타) 분석 후 task 새로 설계.

---

## 1. Survey 정량 요약

### 1.1 사용 빈도

| 빈도 | 교수 (n=15) | 조교 (n=13) | 합계 |
|---|---|---|---|
| 거의 매일 (주 6회+) | 6 | 13 | 19 (68%) |
| 주 1-2회 | 2 | 0 | 2 |
| 월 5회 이하 | 5 | 0 | 5 |
| 사용 안함 | 1 | 0 | 1 |

→ **조교는 100% 매일 사용**. 교수는 학과장/일반 여부에 따라 분산.

### 1.2 교수 주요 업무 (mentions)

| 업무 | 언급 횟수 |
|---|---|
| 출장·휴가 등 복무 관련 결재 | 7 |
| 전자문서 결재 승인/반려 | 7 |
| 공문 수신 확인 | 6 |
| 학과 행정 문서 확인 및 결재 | 6 |
| 연구비·예산 관련 결재 | 2 |

### 1.3 조교 주요 업무 (mentions, n=13)

| 업무 | 언급 횟수 |
|---|---|
| 공문 수신 확인 및 내용 파악 | **13 (100%)** |
| 전자문서 기안 작성 및 상신 | 12 |
| 공문 내용 요약·관련자 전달 (이메일) | 12 |
| 공문 첨부파일 다운로드 및 정리 | 10 |
| 전자문서 결재 승인/반려 처리 | 9 |
| 공문 파일 별도 저장 (구글드라이브 등) | 8 |

### 1.4 불편한 점 — Pain points

| Pain (교수) | 언급 |
|---|---|
| 모바일 환경에서 결재 불편 | 6 |
| 첨부파일을 일일이 열어봐야 핵심 파악 | 4 |
| 유사 결재 반복 처리 | 3 |
| 시스템 UI 비직관적 (문서 찾기 어려움) | 3 |

| Pain (조교) | 언급 |
|---|---|
| 매일 수신 공문 하나씩 열어 확인 | 11 |
| 공문 요약·관련자 전달 작업 | 10 |
| 첨부파일 건별 다운로드 반복 | 8 |
| 파일명 불규칙·수동 정리 | 6 |
| 별도 저장소 업로드 | 6 |

### 1.5 자동화 희망 작업 (주관식, 핵심만)

| 희망 | 출처 |
|---|---|
| 일 수신 공문 목록 자동 요약 → 이메일 발송 | 조교 3건 명시 |
| 결재문서 미리보기·일괄결재 | 교수 2건 |
| 출장 신청 (반복 단순화), 비슷한 출장 복사 | 교수 2건 |
| 첨부파일 정리 + 이메일 발송 | 조교 2건 |
| 메뉴 쉽게 찾기 | 교수 1건 |
| 키워드 문서 검색 ("교육과정 개정 관련") | 교수 1건 |
| 공문 수신처 자동 판단 (교수/대학원/학부) | 조교 1건 |
| 공문 내용 미리 요약 | 조교 1건 |
| 모바일 결재 | 교수 1건 *(범위 밖)* |

---

## 2. v1 → v2 변화 요약

### 2.1 v1에서 drop할 것 (10 seed)

| Seed | Drop 사유 |
|---|---|
| `draft_account` | survey 0건 — 계좌 변경은 거의 일생 1-2회 |
| `draft_concurrent_position` | survey 0건 — 매우 드묾 |
| `draft_return_work` | survey 0건 — 복직은 휴직 끝낼 때만 |
| `draft_proposal` | survey 0건 — 제안공모 자체 안 함 |
| `draft_facility_rental` | survey 0건 — 시설 대여는 학과별 차이 |
| `view_year_end_tax` | survey 0건 — 연 1회 시기 한정 |
| `attach_deduction_doc` | survey 0건 — 연말정산 시기만 |
| `config_personal_settings` | survey 0건 — 1회성 setup |
| `setup_approval_line` | survey 0건 + v1 demo 메뉴 not found |
| `favorite_approval_line` | survey 0건 + v1 demo 메뉴 not found |

### 2.2 v1에서 keep (8 seed)

| Seed | Keep 사유 |
|---|---|
| `approve_pending` | 교수 7건 + 조교 9건 — 핵심 |
| `circulate_pending` | 교수 6건 공문 확인 |
| `draft_domestic_trip` | 출장 결재 7건 |
| `draft_overseas_trip` | 출장 카테고리 |
| `draft_annual_leave_plan` | 복무 결재 7건 |
| `draft_flexible_work` | 복무 — 점점 증가 |
| `draft_leave_absence` | 복무 — 드물지만 임팩트 큼 |
| `view_in_progress` | 결재 진행 상태 조회 |
| `view_completed` | 결재 완료 후 확인 |
| `view_salary_statement` | 매월 자동 |
| `attach_approval_file` | 조교 핵심 (12건 기안 작성) |
| `draft_certificate` | 가끔 — 재직증명서 자주 |
| `draft_facility_complaint` | 시설 민원 — survey 직접 언급 없으나 학과 행정 (6건)에 포함 |

→ v1 24 seed → v1 keep 13 seed

### 2.3 v2 신규 추가 후보 — survey 직접 시사

#### 공문 처리 카테고리 (NEW, 조교 100% 매일)

| 신규 Seed | 근거 |
|---|---|
| `incoming_inbox_review` | 조교 13건 — 수신 공문함 확인 (매일 첫 작업) |
| `incoming_attachment_batch_download` | 조교 10건 — 첨부파일 일괄 다운로드 |
| `incoming_summary_email` | 조교 12건 — 공문 요약 후 관련자 이메일 |
| `incoming_archive_storage` | 조교 8건 — 별도 저장소 (구글드라이브 등) 분류 |
| `incoming_recipient_classify` | 조교 1건 — 수신처 (교수/대학원/학부) 자동 판단 |

#### 결재 처리 강화 (교수 pain points)

| 신규 Seed | 근거 |
|---|---|
| `approve_preview` | 교수 4건 — 첨부파일 일일이 열지 않고 핵심 파악 (미리보기) |
| `approve_batch_similar` | 교수 3건 + 2건 — 유사 결재 일괄 처리 |
| `search_documents_by_keyword` | 교수 1건 (명시) + UI 직관성 호소 — "교육과정 개정 관련" 검색 |

#### 결재 작성 신규

| 신규 Seed | 근거 |
|---|---|
| `draft_trip_copy_previous` | 교수 1건 (외부강의·출장 중복) — 비슷한 출장 복사·재사용 |
| `draft_research_budget` | 교수 2건 — 연구비·예산 결재 (별도 카테고리 가능) |

---

## 3. v2 최종 제안 — **16 seed**

### 카테고리 [공문] — NEW, 조교 핵심 (5 seed)

| Seed | action_name | brief | 사용 빈도 |
|---|---|---|---|
| `incoming_inbox_review` | 수신 공문함 확인 | 받은 공문 리스트 열어 일자/제목/발신처 훑기 | 🔴 매일 |
| `incoming_attachment_batch_download` | 공문 첨부파일 일괄 다운로드 | 선택한 공문들의 첨부파일(HWP/PDF) 일괄 다운로드 | 🔴 매일 |
| `incoming_summary_email` | 공문 요약 + 관련자 메일 발송 | 공문 본문·첨부 요약, 수신 대상자 메일에 전달 | 🔴 매일 |
| `incoming_recipient_classify` | 공문 수신처 자동 분류 | 공문 내용 보고 교수/대학원생/학부생 중 누구에게 보낼지 판단 | 🟡 |
| `incoming_archive_storage` | 공문 파일 외부 저장소 정리 | 다운로드 파일을 polished 이름으로 폴더 분류 | 🟡 |

### 카테고리 [결재처리] — 교수+조교 핵심 (4 seed)

| Seed | action_name | brief | 사용 빈도 |
|---|---|---|---|
| `approve_pending_review` | 결재대기함 확인·검토 | 받은 결재 list 열고 항목 검토 (승인 클릭은 v2도 mock 결재선) | 🔴 매일 (교수+조교) |
| `approve_preview` | 결재문서 미리보기 (첨부 안 열고) | 본문·첨부 요지를 한 화면에서 파악 | 🔴 |
| `approve_batch_similar` | 유사 결재 일괄 처리 | 같은 패턴 결재건 그룹핑·일괄 승인 (mock) | 🟡 |
| `circulate_pending_review` | 공람 문서 확인 | 공람대기함 열어 항목 훑기 | 🟡 (교수 6건) |

### 카테고리 [결재작성·상신] — 교수 빈번 (5 seed)

| Seed | action_name | brief | 사용 빈도 |
|---|---|---|---|
| `draft_domestic_trip` | 국내출장신청·상신 | 일정·목적·여비 입력 후 결재 상신 | 🔴 (교수 7건) |
| `draft_overseas_trip` | 국외출장신청·상신 | 학회·세미나 등 해외 출장 | 🟡 |
| `draft_trip_copy_previous` | 이전 출장 복사·재사용 | 과거 결재한 출장을 base로 새 결재 만들기 (반복 결재 완화) | 🟡 (교수 자동화 희망) |
| `draft_leave_request` | 연가/병가/유연근무 신청 | 월별연가, 유연근무, 휴직 통합 형태로 단순화 | 🔴 |
| `draft_certificate` | 증명서 발급 신청 | 재직증명/경력증명/소득증명 등 | 🟡 |

### 카테고리 [문서조회·검색] — 교수+조교 (3 seed)

| Seed | action_name | brief |
|---|---|---|
| `view_in_progress` | 진행 문서 조회 | 내가 기안한 진행중 결재 상태 확인 |
| `view_completed` | 완료 문서 조회 | 결재 완료된 문서 검색·열람 |
| `search_documents_by_keyword` | 키워드 문서 검색 | "교육과정 개정", "출장비" 같은 키워드로 관련 문서 찾기 |

### 카테고리 [첨부파일] — 조교 핵심 (1 seed)

| Seed | action_name | brief |
|---|---|---|
| `attach_approval_file` | 기안 작성 시 파일 첨부 | 견적서·계획서 등을 결재 폼에 업로드 |

### 카테고리 [급여·정산] — 매월 (1 seed)

| Seed | action_name | brief |
|---|---|---|
| `view_salary_statement` | 급여명세서 조회 | 매월 1회 본인 명세서 |

### 카테고리 [시설] — 학과 행정 (1 seed)

| Seed | action_name | brief |
|---|---|---|
| `draft_facility_complaint` | 시설물 민원 신청 | 수리·고장 신고 (학과 행정 결재 6건에 포함) |

### 카테고리 [연구비] — 교수 (1 seed)

| Seed | action_name | brief |
|---|---|---|
| `draft_research_budget` | 연구비·예산 결재 | 연구비 집행 결재 (교수 2건 언급) |

→ **합계 5+4+5+3+1+1+1+1 = 21 seed**. 너무 많음. 좀 더 줄임.

---

## 4. v2 추천 — 16 seed (압축 최종)

### 우선순위 분류

| Tier | 의미 | seed 수 |
|---|---|---|
| 🔴 **MUST** | survey에서 매일·빈번하게 언급 | 8 |
| 🟡 **SHOULD** | 자주 또는 강한 pain point | 5 |
| 🟢 **OPTIONAL** | 가끔이지만 도메인 커버용 | 3 |

| Tier | Seed | 카테고리 |
|---|---|---|
| 🔴 | `incoming_inbox_review` | 공문 |
| 🔴 | `incoming_attachment_batch_download` | 공문 |
| 🔴 | `incoming_summary_email` | 공문 |
| 🔴 | `approve_pending_review` | 결재처리 |
| 🔴 | `approve_preview` | 결재처리 |
| 🔴 | `draft_domestic_trip` | 결재작성 |
| 🔴 | `draft_leave_request` | 결재작성 |
| 🔴 | `view_in_progress` | 조회 |
| 🟡 | `incoming_recipient_classify` | 공문 |
| 🟡 | `approve_batch_similar` | 결재처리 |
| 🟡 | `circulate_pending_review` | 결재처리 |
| 🟡 | `draft_trip_copy_previous` | 결재작성 |
| 🟡 | `view_completed` | 조회 |
| 🟢 | `search_documents_by_keyword` | 조회 |
| 🟢 | `attach_approval_file` | 첨부 |
| 🟢 | `draft_certificate` | 결재작성 |

**16 seed × 4 variant = 64 task**.

---

## 5. v2 vs v1 vs survey 매핑

| Persona / Pain | v1 커버 | v2 신규 추가 |
|---|---|---|
| 조교 — 매일 공문 확인 | ❌ | ✅ `incoming_inbox_review` |
| 조교 — 첨부파일 다운로드 반복 | 부분 (`attach_approval_file`만) | ✅ `incoming_attachment_batch_download` |
| 조교 — 공문 요약·메일 | ❌ | ✅ `incoming_summary_email` |
| 조교 — 수신처 분류 | ❌ | ✅ `incoming_recipient_classify` |
| 교수 — 첨부 일일이 열어봄 | ❌ | ✅ `approve_preview` |
| 교수 — 유사 결재 반복 | ❌ | ✅ `approve_batch_similar`, `draft_trip_copy_previous` |
| 교수 — 메뉴 찾기 어려움 | ❌ | ✅ `search_documents_by_keyword` |
| 교수 — 모바일 결재 | (범위 밖 — desktop only) | — |

---

## 6. v2 진행 시 결정해야 할 사항

| 결정 사항 | 옵션 |
|---|---|
| 신규 5 공문 seed의 KORUS 실제 메뉴 path | 사용자가 KORUS에서 직접 확인 필요. discovery 재실행도 옵션. |
| `incoming_summary_email` — 외부 이메일 발송은 KORUS 내장 vs 별도 SMTP? | KORUS 내 메일쓰기 기능 사용 (조교 응답에 "코러스 메일쓰기" 언급 있음) |
| `approve_batch_similar` — mock 결재선 필요 | Phase 1 v1+ 진입 전 mock 결재 1-2건 setup |
| `search_documents_by_keyword` — 검색 query 다양성 | paraphrase 단계에서 `{{keyword}}` placeholder |
| v1 seeds_curated.json + tasks/korus_100.json 처분 | backup (.v1.json) + 신규 v2 set 생성 |

---

## 7. 진행 절차 제안

1. **v2 seed 16개 확정** — 위 표 review + 추가/제거 결정
2. **신규 5 공문 seed의 KORUS path 확인** — discover.py 재실행 (공문 카테고리 강조 prompt)
3. **seeds_curated.v2.json 생성** — keep 8 + 신규 8 합쳐 16 seed
4. **paraphrase 재실행** — 16 × 4 = 64 task
5. **F1+F2 + xvfb-run 환경에서 Phase 1 v2 collect** — read-only 부분 먼저, mock 결재선 setup 후 mutating
6. **재학습** — 데이터 확장된 만큼 LoRA r=24 또는 r=32

자, 이 안에서 추가/제거하실 거 있으시면 알려주세요.
