# Phase 1 v0 — Trajectory 실패 모드 분석

**대상**: `trajectories/` 24 trajectory (Phase 1 v0 read-only 카테고리)
**분석일**: 2026-05-12
**Raw 데이터**: `analysis/_raw_summary.json`, `analysis/_fail_traces.json`

---

## 1. 전체 통계

| 항목 | 값 |
|---|---|
| 시도된 task | 28 |
| 수집된 trajectory | 24 (4개는 세션 만료/kill) |
| 평가 대상 | **24** |
| `done.success = True` | 13 (54.2%) |
| `done.success = False` | 11 (45.8%) |
| **재분류 후 실제 success** | **16 / 24 (66.7%)** — §5 참조 |

---

## 2. 11 fail trajectory 카테고리 분포

| # | 카테고리 | 빈도 | 비율 |
|---|---|---|---|
| 1 | 메뉴 path 못 찾음 (Spring 메뉴 구조) | 4 | 36.4% |
| 2 | Spring 폼 입력 실패 (shadow DOM / iframe) | 2 | 18.2% |
| 3 | 데이터 없음을 self-fail로 평가 (사실상 success) | 3 | 27.3% |
| 4 | Placeholder 미치환 (`{{doc_no}}` 그대로 입력) | 1 | 9.1% |
| 5 | Max steps 도달 (탐색 단계에서 소진) | 1 | 9.1% |
| **합계** | | **11** | **100%** |

---

## 3. 카테고리별 상세

### 3.1 메뉴 path 못 찾음 (4건) — 가장 큰 원인

| Trajectory | Step | 마지막 시도 | done.text 발췌 |
|---|---|---|---|
| `view_doc_register_00` | 13 | sitemap·search 후 포기 | "KORUS에서 등록대장(registration ledger)을 찾지 못했습니다" |
| `view_doc_register_01` | 19 | 공통관리 → 비즈니스플랫폼 → 게시판 (마지막 시도) | "작업 결과: 미완료" |
| `view_doc_register_02` | 19 | sitemap 검색 0건 + menu search box 입력 | "'문서 등록 대장' 메뉴를 찾을 수 없었습니다" |
| `view_doc_register_03` | 17 | sitemap에서 `문서`, `등록대장` 키워드 검색 모두 0건 | "현재 사용자 권한으로는 '전자문서 등록대장' 메뉴에 접근할 수 없습니다" |

**관찰**:
- 4건 모두 `view_doc_register_*` (같은 seed 4 variant). seed 자체 문제.
- seeds.json에 적힌 메뉴 경로 `전자문서 > 문서등록대장`이 실제 KORUS 메뉴에 **존재하지 않거나 다른 이름**.
- Discovery 단계에서 enumerate된 후보였지만 실제 클릭으로는 도달 못한 메뉴.

**근본 원인**: Phase 0b discovery에서 sitemap 라벨만 보고 `where`을 추정한 항목들이 실제 navigable path가 아닐 수 있음. `(추정)` 표시된 항목은 curate에서 trim했지만 `view_doc_register`는 표시 없이 살아남았음.

### 3.2 Spring 폼 입력 실패 (2건) — 두 번째 원인

| Trajectory | Step | 마지막 시도 | 문제점 |
|---|---|---|---|
| `approve_pending_03` | 17 | shadow DOM input + `evaluate()` 양쪽 시도 후 포기 | "Fields filled but search not executing" — shadow DOM 안에서 input은 됐는데 submit이 안 통함 |
| `circulate_pending_02` | 17 | 검색 → 0건 + 문서정보 popup 확인 → search 재시도 후 포기 | 폼 자체는 동작하지만 검색 결과 0건 (placeholder 값 때문이지만 agent는 폼 실패로 해석) |

**Spring 특이성**:
- KORUS는 Java EE/Spring 기반으로 form submit이 종종 POST + hidden state (CSRF token 등) 필요
- browser-use의 일반 `input` + `click(submit)` 패턴이 shadow DOM 안에서는 events fire 안 됨
- agent가 CDP `evaluate()`로 우회 시도했지만 form 내부 state 못 건드림

### 3.3 데이터 없음 self-fail (3건) — 사실상 success로 재분류 가능

| Trajectory | Step | 실제 수행 | self-eval |
|---|---|---|---|
| `view_salary_statement_01` | 15 | 급여명세서 페이지 도달 + 2026-05 / 2026-04 검색 시도 + "데이터 없음" 확인 | `success=False` (이번 달 급여 미발생을 task 실패로 봄) |
| `view_salary_statement_02` | 14 | 페이지 도달 + 2026-02 / 2026-03 검색 + "데이터 없음" | `success=False` |
| `view_salary_statement_03` | 19 | 페이지 도달 + 2025-12 검색 시도 + "데이터 없음" | `success=False` |

**관찰**:
- 3건 모두 page navigation **완벽 성공**. 메뉴 path도 정확히 찾음.
- task 자체는 "급여명세서 조회"라는 read-only — 데이터 표시 여부와 무관하게 조회 자체는 성공.
- agent가 너무 엄격하게 self-eval — "데이터 0건 = 사용자 의도 미달성"이라 해석.

**재분류 후 success rate**: 13 + 3 = **16 / 24 (66.7%)**.

### 3.4 Placeholder 미치환 (1건)

| Trajectory | Step | 입력값 | 결과 |
|---|---|---|---|
| `approve_pending_02` | 8 | search 필드에 `<secret>doc_no</secret>` 입력 후 `{{doc_no}}` placeholder인 것 확인 | 0 결과, agent가 "placeholder는 실제 값이 아님" 명시 |

**관찰**:
- task: `[approve_pending_02] {{doc_no}} 결재 건 상세 내용 검토하고 싶어`
- `collect.py`의 sensitive_data dummy 사전에 `doc_no: "DUMMY-DOC-001"`로 잡혀 있음
- 그러나 browser-use sensitive_data는 LLM에 `<secret>doc_no</secret>` 형태로만 노출 — agent가 이게 placeholder임을 인지하고 명시적으로 fail 처리

**근본 원인**: sensitive_data는 *실제 인증 자격증명* 가리는 용도지 paraphrase placeholder 치환 용도가 아님. task 텍스트의 `{{doc_no}}`는 별도 pre-처리로 dummy 또는 실제 값으로 치환해야 함.

### 3.5 Max steps 탐색 소진 (1건)

| Trajectory | Step | 진행 상황 | 마지막 |
|---|---|---|---|
| `view_completed_02` | 19 | 업무관리 → 완료문서 → 기안한 문서 navigation 완료, search interface 도달 | search 실행 안 하고 max_steps 도달, "incomplete" 보고 후 done(false) |

**관찰**:
- max_steps=20 (CLI default), 실질 19 step에 도달
- 메뉴 navigation에 너무 많은 step 소진 (sitemap 클릭, scroll, 다시 클릭…)
- search interface는 봤지만 실제 query 실행 못함

---

## 4. 카테고리별 영향 — 카테고리 cross-tab

| Seed | total | success | fail | 실패 카테고리 |
|---|---|---|---|---|
| view_in_progress | 4 | 4 | 0 | — |
| view_completed | 4 | 3 | 1 | max_steps_during_navigation |
| circulate_pending | 4 | 3 | 1 | search_form_input_failure |
| approve_pending | 4 | 2 | 2 | placeholder + search_form |
| view_salary_statement | 4 | 1 | 3 | empty_data_self_fail × 3 |
| view_doc_register | 4 | 0 | 4 | menu_not_found × 3 + permission × 1 |

**핵심 관찰**:
- `view_doc_register_*` 0/4 = seed 자체가 깨진 후보 (메뉴 부재 / 권한 부족)
- `view_salary_statement_*` 1/4 → 재분류 후 4/4 (success 평가 기준만 고치면 됨)
- `view_in_progress_*` 4/4 → KORUS도 일반 메뉴 path는 잘 따라감
- `circulate_pending`, `approve_pending`은 search form 깊이 들어가면 막힘

---

## 5. 재분류 후 성능

| 분류 | 개수 | 비율 |
|---|---|---|
| Genuine success | 13 | 54.2% |
| Empty-data self-fail (사실상 success) | 3 | 12.5% |
| **재분류 후 success** | **16** | **66.7%** |
| Genuine fail | 8 | 33.3% |
| - menu_not_found | 3 | 12.5% |
| - permission_denied | 1 | 4.2% |
| - search_form_input | 2 | 8.3% |
| - placeholder_unresolved | 1 | 4.2% |
| - max_steps_navigation | 1 | 4.2% |

---

## 6. 80% 목표 달성 actionable items

우선순위는 빈도 × fix 난이도 기반.

### Tier 1 — 빠르게 +12.5% (목표 80% 도달 핵심)

#### F1. Empty-data self-eval 정정 → +12.5%
**작업**: `cnu_agent/teacher/collect.py`의 task 텍스트에 "조회 결과가 없으면 success=True로 done 호출하라" 명시 추가.

**파일 변경**:
```python
# collect.py — full_task prefix에 추가
"task: {task['task']}\n\n"
"## Done 평가 규칙\n"
"- 페이지 도달 + 검색 실행까지만 했으면 결과 데이터 유무와 무관하게 done(success=True).\n"
"- read-only 조회 task의 성공 기준 = 의도한 페이지에서 결과를 *확인*한 것 (데이터 0건도 OK).\n"
"- search form 자체가 동작 안 한 경우만 done(success=False)."
```

**예상 효과**: 13/24 → 16/24 (54% → 67%).

#### F2. `view_doc_register` seed 제거 또는 메뉴 path 교정 → +16.7%
**작업**: 
- 옵션 A — seeds_curated에서 제거 (Phase 1 v1 진행 전)
- 옵션 B — KORUS에서 실제 메뉴 path 확인 후 seed의 `where` 필드 수정
- 옵션 C — DISCOVERY_PROMPT에 "이 메뉴는 KORUS에 없을 수 있음" hint 후 재발견

**예상 효과**: 4 trajectory 제거 시 20개 중 16 success = 80%.
또는 fix로 success 시 16 + 4 → 20/24 = 83%.

### Tier 2 — Spring 특화 (+12.5%, 더 깊은 작업)

#### F3. Search form (shadow DOM) 입력 액션 보강 → +8.3% (potential)
**작업**: `cnu_agent/teacher/collect.py` 또는 별도 actions 모듈에서 shadow DOM 대응 input 추가.

```python
@tools.action("shadow_dom_input", param_model=ShadowInputParams)
async def shadow_input(params, browser_session):
    # 1. CDP로 shadowRoot 탐색
    # 2. native HTMLInputElement.value = ... + dispatchEvent('input','change')
    # 3. form.submit() 명시 호출
```

**대상 trajectory**: `approve_pending_03`, `circulate_pending_02`

#### F4. Placeholder pre-substitution → +4.2%
**작업**: `collect.py`에서 task 텍스트의 `{{key}}` 토큰을 sensitive_data 진입 *전에* 치환 (또는 fallback 토큰 사전 사용).

```python
import re
PLACEHOLDER_FILL = {
    'doc_no': 'KORUS-DUMMY-2025-001',
    'doc_title': '테스트 문서',
    ...
}
task_text = re.sub(r'\{\{(\w+)\}\}', 
                   lambda m: PLACEHOLDER_FILL.get(m.group(1), m.group(0)), 
                   task['task'])
```

**대상 trajectory**: `approve_pending_02`

#### F5. Max-steps 상향 → +4.2%
**작업**: `collect.py --max-steps 30` (기본 20 → 30). 또는 prompt로 navigation 효율 강조.

**대상 trajectory**: `view_completed_02`

### Tier 3 — 다양화 (현재 24 trajectory가 너무 좁음)

#### F6. Phase 1 v1 — 결재 mutating 추가
mock 결재선 setup 후 결재작성 13 seed × 4 variant = 52 task 추가. 총 ~76 trajectory.

---

## 7. 권장 진행 순서

| 우선순위 | 작업 | 즉시 효과 |
|---|---|---|
| 1 | F1 (self-eval 정정 prompt) | 54% → 67%, 코드 5분 |
| 2 | F2 (view_doc_register seed 처리) | 67% → 80%+, 코드 또는 manual review |
| 3 | F4 (placeholder pre-sub) | 80% → 84% |
| 4 | F5 (max-steps 30) | 84% → 88% (가능성) |
| 5 | F3 (shadow DOM action) — 더 어려움 | 88% → 92% (가능성) |
| 6 | F6 (Phase 1 v1) — mock 결재선 후 | 데이터 다양성 확보, 별개 진행 |

**현실 추정**: F1+F2 만으로 80% 목표 달성 가능. 나머지는 v1 데이터까지 모은 뒤 측정.

---

## 8. Raw 데이터

- `analysis/_raw_summary.json` — 24 trajectory의 success/step/action_count/done text 요약
- `analysis/_fail_traces.json` — 11 fail trajectory의 마지막 3 step trace (eval/goal/actions)
