# CNU AI Agent — Test Task 명세

조교/교수 29명 설문 기반 KORUS 자동화 task 15 카테고리.

모든 task는 **read-only 모드** — 메뉴 도달·조회까지, 제출/승인 등 mutating 금지.

정답 기준: 의도한 페이지/form 도달 + 결과 확인 → `done(success=True)`. 데이터 0건도 OK.


## 공문처리 — 수신 공문함 확인

- **하는 일**: 받은 공문 list 확인 (제목/일자/발신처). 일일 첫 작업.
- **메뉴**: 전자문서 > 공유/공람 > 받은문서
- **상세**: 327 incoming documents visible with date, sender, subject columns
- **paraphrase 4개**:
  - 받은 공문 확인해줘
  - 수신 공문함 열어서 보여줘
  - 오늘 들어온 공문 리스트 보여주세요
  - 전자문서 받은문서함에 새 공문 들어온 거 있나 확인하고 싶은데, 제목이랑 발신처 날짜 다 보여줘


## 공문처리 — 공문 첨부파일 일괄 다운로드

- **하는 일**: 선택한 공문들의 첨부파일(HWP/PDF)을 PC저장 버튼으로 일괄 다운로드.
- **메뉴**: 전자문서 > 공유/공람 > 받은문서
- **상세**: PC저장 (batch download) button visible for multiple selected documents
- **paraphrase 4개**:
  - 받은 공문 첨부 일괄 다운
  - 받은문서함에서 공문 첨부파일 일괄 다운로드해줘
  - 공람 받은 공문들 첨부파일 한꺼번에 PC에 저장 부탁해
  - 전자문서 받은문서함에 있는 공문 몇 개 선택해서 첨부된 HWP랑 PDF 파일 전부 PC저장 버튼으로 다운받고 싶어


## 공문처리 — 공문 요약 후 관련자 메일 발송

- **하는 일**: 첨부 본문 분석(analyze_attachment) 후 KORUS 업무메일로 요약 작성 + 적절한 수신자 분류 (발송 직전까지).
- **메뉴**: 업무메일 (top navigation)
- **상세**: 업무메일 tab visible in main top navigation menu


## 결재처리 — 결재대기함 검토

- **하는 일**: 받은 결재 문서 열어 본문·첨부 검토 (승인/반려 직전까지). needs mock approval line.
- **메뉴**: 전자문서 > 결재 > 결재대기함
- **상세**: 6 pending approval documents visible with checkboxes for selection
- **paraphrase 3개**:
  - 결재함 확인해줘
  - 대기 중인 결재 문서 검토해줘
  - 전자문서 결재대기함에서 받은 결재 건들 본문이랑 첨부파일 확인 부탁해


## 결재처리 — 결재 문서 본문 미리 파악

- **하는 일**: 첨부 다운로드 + analyze_attachment로 본문 요약 (KORUS 별도 preview UI 없어서 agent reasoning).
- **상세**: Document detail pages consistently fail to load; cannot verify preview functionality
- **paraphrase 2개**:
  - 결재 문서 미리 확인
  - 대기 중인 결재 문서 내용 요약해줘


## 결재처리 — 비전자문서 일괄결재 검토

- **하는 일**: 결재대기함 '비전자문서 일괄결재' 버튼으로 유사 건 검토 (승인 직전까지). needs mock approval line.
- **메뉴**: 전자문서 > 공유/공람 > 공람대기
- **상세**: 327 documents with batch checkboxes and 읽기처리 (batch read) button for bulk processing
- **paraphrase 4개**:
  - 비전자 일괄결재 검토
  - 비전자문서 일괄결재 확인해줘
  - 결재대기함 비전자문서 일괄로 검토 부탁해
  - 대기 중인 비전자문서들 유사 건 일괄결재 기능으로 한 번에 검토해주세요


## 결재작성 — 일반 전자문서 기안 작성

- **하는 일**: 전체서식 27개 중 적절한 폼 선택 → 폼 작성 + 결재선 지정 (상신 직전까지). needs mock approval line.
- **메뉴**: 전자문서 > 기안 > 전체서식/기관서식/부서서식/최근서식/임시저장함
- **상세**: 5 submenus available with 27 forms visible and search box for form filtering


## 결재작성 — 출장신청 (국내/국외)

- **하는 일**: 복무>출장 폼 작성 + 결재선 지정 (상신 직전까지). needs mock approval line.
- **paraphrase 2개**:
  - 출장 신청 좀 해줘
  - 서울 연구발표회 참석용 국내출장 결재 작성해주세요


## 결재작성 — 휴가·유연근무 신청

- **하는 일**: 유연근무·연가·병가 폼 작성 + 결재선 지정 (상신 직전까지). needs mock approval line.
- **메뉴**: 전자문서 > 복무 > 유연근무
- **상세**: 유연근무 menu item visible under 복무; likely covers leave/flexible work requests
- **paraphrase 3개**:
  - 휴가 신청해줘
  - 6월 20일 개인 사유로 연가 신청 좀 부탁해
  - 다음 주 월요일부터 수요일까지 가족 행사 참석으로 연가를 써야 하는데 전자결재 시스템에서 휴가 신청서 작성하고 결재선 지정까지 완료해줘


## 첨부파일 — 기안 폼에 파일 첨부

- **하는 일**: 기안 작성 중 첨부파일 영역에 견적서·계획서 등 업로드 (상신 직전까지).
- **메뉴**: 전자문서 > 기안 (forms)
- **상세**: Standard form feature; attachment areas likely exist within individual forms but not directly verified
- **paraphrase 2개**:
  - 파일 첨부해줘
  - 기안 문서에 사업계획서 첨부해줘


## 첨부파일 — 의무교육 이수증 등록

- **하는 일**: 교육훈련 실적관리 그리드의 '수료증빙파일' 컬럼에 이수증 업로드 (저장 직전까지).
- **상세**: No dedicated menu for uploading training certificates found in explored sections
- **paraphrase 2개**:
  - 이수증 등록해줘
  - 교육훈련 수료증 파일 올려줘


## 문서조회 — 진행 문서 조회

- **하는 일**: 내가 기안하거나 결재선에 포함된 진행 중 문서 list 확인.
- **메뉴**: 전자문서 > 결재 > 진행문서함
- **상세**: 진행문서함 menu item confirmed in navigation tree
- **paraphrase 4개**:
  - 진행문서함 열어줘
  - 진행 중인 결재 문서 확인해줘
  - 내가 올린 문서들 중에 아직 진행 중인 거 리스트 보여줄래
  - 내가 기안했거나 결재자로 지정된 문서 중에서 현재 결재 진행 중인 것들을 확인하고 싶어


## 문서조회 — 완료 문서 조회

- **하는 일**: 결재 완료 문서 list/상세 확인.
- **메뉴**: 전자문서 > 결재 > 완료문서
- **상세**: 완료문서 menu item confirmed in navigation tree
- **paraphrase 4개**:
  - 완료 문서 보여줘
  - 결재 완료된 문서들 목록 좀 확인하고 싶어
  - 이번 달 완료 처리한 전자결재 문서 전부 보여줘
  - 지난 3개월간 내가 결재 완료한 문서들 중에서 품의서 관련된 것만 찾아서 상세 내용 확인해줘


## 문서조회 — 키워드로 문서 검색

- **하는 일**: 진행문서함 또는 완료문서 검색 필드에 키워드 입력 + 필터(제목/기안자/날짜) 조합.
- **메뉴**: 전자문서 > 기안 > 전체서식
- **상세**: Search box visible and functional in form list; tested with '연구비' query (returned 0 results but search function exists)
- **paraphrase 4개**:
  - 출장 문서 찾아줘
  - 진행문서함에서 연구비 신청 문서 검색해줘
  - 이번 달에 기안된 장비 구매 관련 문서 찾아주세요
  - 완료문서함에서 '학생 지도' 키워드로 제목 검색하고, 2026년 4월 이후 기안된 건만 보여줘


## 정산 — 연말정산 내역 조회/신청

- **하는 일**: 상단 nav 연말정산 메뉴 진입 후 내역 조회 또는 신청 폼 (제출 직전까지). 연 1회.
- **메뉴**: 연말정산 (top navigation)
- **상세**: 연말정산 menu item visible in main top navigation menu
- **paraphrase 3개**:
  - 연말정산 조회해줘
  - 올해 연말정산 신청하려는데 폼 열어줄래?
  - 상단 메뉴에서 연말정산 들어가서 올해 제출 서류랑 신청 폼 확인할 수 있게 해줘
