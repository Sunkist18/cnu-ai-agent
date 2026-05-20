# KORUS 자동화 — 최종 데모 결과 (Friday)

날짜: 2026-05-21
담당: 최민우 (KORUS)

## 🏆 핵심 결과

| 접근법 | 성공률 | task set | 비고 |
|---|---|---|---|
| v2 LoRA (Qwen 32B fine-tune) | 14/41 (34%) | 41 clean | 60 trajectory 학습 |
| v3 LoRA (login+popup 추가) | 1/25 (4%) | 25 clean | **regression** (작은 dataset 과적합) |
| Claude Sonnet 4.5 + prompt | 10/11 (91%) | (중단) | |
| **Claude Sonnet 4.7 + prompt** | **19/20 (95%)** | 20 | ✅ **데모 채택** |

## 결론

> **32B fine-tuning < prompt engineering on frontier model**
>
> 한국 enterprise web(KORUS) 자동화는 작은 dataset distillation으로 손해(regression)를 봤으나,
> Claude Sonnet 4.7 + 도메인 특화 프롬프트로 **95%** 달성.

## Claude 4.7 결과 상세 (19/20)

```
✅ 결재처리 (approve_*):     5/5  (대기함, preview, 일괄결재)
✅ 공문처리 (incoming_*):    5/5  (받은공문 4, 첨부 다운로드 1)
✅ 문서조회 (search/view):   6/6  (키워드 검색 4, 완료문서 2)
✅ 결재작성 (draft_trip):    1/1  (출장 신청)
❌ 첨부파일 (training_cert): 0/1  (이수증 등록 — KORUS 메뉴 불명확, task 설계 이슈)
```

- 평균 step: 10.6
- 평균 소요: 6.7분/task

## 프롬프트 핵심 (analysis/claude_prompt_korus.md)

1. **read-only 모드** — 조회까지만, mutating 금지
2. **로그인 DOM selector** — `<input id=userId01>`, `<input id=emplyrSecretNo>`, `<a title=로그인>`
3. **KORUS 특징 명시** — iframe, 새 탭, skeleton 로딩, 만족도 팝업
4. **무한 루프 방지** — 같은 클릭 3번 ❌, wait 4번 ❌
5. **메뉴 힌트** — seed별 검증된 경로 (discovery/v2_paths.json)
6. **결과 정리** — done text에 자연어 + 목록으로 사용자 친화 출력

## 데모 스토리

1. **가설**: 한국 KORUS 특수 도메인 → Claude 증류로 Qwen 학습
2. **fine-tuning 실험**: v2 34%, v3 4% (regression)
3. **발견**: 작은 dataset distillation은 base 능력 손상
4. **대안**: frontier model(Claude 4.7) + domain prompt = **95%**
5. **결론**: 모델 크기 충분하면 prompt engineering이 distillation보다 효율적.
   증류는 더 작은 모델(7B)에서 가치 — 향후 연구.

## 산출물

- `eval_claude_korus/korus_results.csv` — Task.xlsx 취합용 (응답 열 포함)
- `eval_claude_korus/results.jsonl` — raw 결과
- `eval_claude_korus/<task_id>/history.json` — trajectory
- `analysis/claude_prompt_korus.md` — 프롬프트
- 비교: `eval_vllm_v2/` (v2), `eval_v3_full/` (v3)
