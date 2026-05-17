# v2 최종 리포트 — 자동 수집·변환·업로드 완료

작성: 2026-05-17 13:35 KST · 모든 자동 chain 완료. **Mac push + B200 학습 명령 1줄씩** 실행만 남음.

---

## 1. 한 줄 요약

| 지표 | v0 | v1 (이전 demo) | **v2** |
|---|---|---|---|
| Seed 수 | 25 | 24 | **15** (survey-driven) |
| Task 수 | 100 | 96 | **60** |
| Trajectory 수집 | 24 | 10 (demo) | **60** |
| Teacher success rate | 54.2% (13/24) | 80% (8/10) | **78.3% (47/60)** |
| Mutating click | 0 | 0 | **0** (audit) |
| Total step | 308 | 114 | **874 (처리)** |
| 학습 데이터 | 234+74 = 308 sample | — | **728+146 = 874 sample** |
| 학습 모델 (예정) | LoRA r=16 | — | LoRA r=16 또는 r=24 |
| HF dataset | trajectories-v0 | — | **cnu-korus-trajectories-v2** |

→ **v0 대비 success rate +24%p, 학습 sample ×2.8배 (308→874).**

---

## 2. v2 collect 상세 — 60/60 trajectory

### 2.1 Seed별 success rate

| Seed | success/total | 평균 step | 카테고리 |
|---|---|---|---|
| `incoming_inbox_review` | **4/4 (100%)** | 8.0 | 공문 |
| `incoming_summary_email` | **4/4 (100%)** | 15.2 | 공문 |
| `approve_pending_review` | **4/4 (100%)** | 14.0 | 결재처리 |
| `approve_preview` | **4/4 (100%)** | 9.8 | 결재처리 |
| `view_in_progress` | **4/4 (100%)** | 15.0 | 조회 |
| `view_completed` | **4/4 (100%)** | 9.0 | 조회 |
| `search_documents_by_keyword` | **4/4 (100%)** | 16.0 | 조회 |
| `view_or_submit_year_end_tax` | **4/4 (100%)** | 9.2 | 정산 |
| `attach_training_certificate` | 3/4 (75%) | 17.5 | 첨부 |
| `draft_general` | 3/4 (75%) | 16.2 | 결재작성 |
| `approve_batch_similar` | 2/4 (50%) | 20.5 | 결재처리 |
| `attach_approval_file` | 2/4 (50%) | 15.5 | 첨부 |
| `draft_leave_request` | 2/4 (50%) | 23.5 | 결재작성 |
| `incoming_attachment_batch_download` | 2/4 (50%) | 15.8 | 공문 |
| `draft_trip` | 1/4 (25%) | 19.8 | 결재작성 |
| **합계** | **47/60 (78.3%)** | **15.0** | |

### 2.2 카테고리별

| 카테고리 | success | 평균 |
|---|---|---|
| 공문처리 | 10/12 (83%) | 12 step |
| 결재처리 | 10/12 (83%) | 14 step |
| 결재작성 | 6/12 (50%) ← 가장 어려움 (복잡한 폼 입력) | 20 step |
| 첨부파일 | 5/8 (63%) | 17 step |
| 문서조회 | 12/12 (100%) | 13 step |
| 정산 | 4/4 (100%) | 9 step |

### 2.3 v0 → v2 핵심 개선

| | v0 | v2 |
|---|---|---|
| 결재처리 success | 5/8 (62%) | **10/12 (83%)** |
| 문서조회 success | 8/16 (50%) → F1 후 11/16 (68%) | **12/12 (100%)** |
| 공문 처리 (NEW) | — | **10/12 (83%)** ← 조교 핵심 작업 |
| 정산 (NEW) | — | **4/4 (100%)** |
| 첨부 본문 분석 | ❌ | ✅ analyze_attachment (kordoc) |

---

## 3. 적용된 fix·신규 기능

| | 적용 시점 | 효과 |
|---|---|---|
| F1 — Done 평가 규칙 prompt | v1 commit dbcc104 | "데이터 없음 = success" 정정. v1 demo 4/4 검증. v2 그대로. |
| F2 — `view_doc_register` seed 제거 | v1 | seed path 부재로 4/4 fail 원인 제거. |
| `analyze_attachment` Tools.action | v2 commit fcd200c→0642a5a (수정 다수) | kordoc로 HWP/HWPX/PDF/DOCX 본문 추출, agent context 주입. survey 핵심 pain 해소. |
| ChatClaudeCode 내부 retry + backoff | v2 commit 0642a5a | server_error / rate_limit transient 회복. `approve_pending_review` 0/4 → 4/4, `incoming_summary_email` 0/4 → 4/4. |
| Survey-driven 15 seed | v2 commit 186d6f2 | 무용한 seed 10개 제거, 공문 처리 카테고리 신설. |

---

## 4. 산출물 위치

### Mac (working dir: `/Users/chaeminu/Documents/sandbox/cnu-ai-agent`)
| 항목 | 위치 | 크기 |
|---|---|---|
| 코드 | git tracked | — |
| Trajectory (v2) | `trajectories_v2/` (gitignored) | 220 MB |
| Train/eval JSONL | `data_v2/korus_*.jsonl` (gitignored) | 34 MB |
| 분석 리포트 | `analysis/v2_final_report.md` (이 파일) | 8 KB |
| Seed | `discovery/seeds_curated.json` (15 v2 seed, gitignored) | 5 KB |
| Task | `tasks/korus_100.json` (60 v2 task, gitignored) | 30 KB |

### HuggingFace Hub (private)
- Dataset: **`chaeminu/cnu-korus-trajectories-v2`**
- 935 files, 220 MB trajectories + 34 MB data
- Commits: `a5e1362` (trajectories), `b89f114` (data)
- URL: https://huggingface.co/datasets/chaeminu/cnu-korus-trajectories-v2

---

## 5. 깨어나면 할 일 — 명령 3개

### Step 1 (Mac) — git push

```bash
cd /Users/chaeminu/Documents/sandbox/cnu-ai-agent
git push origin main
```

push 후 `git log --oneline -10` 으로 8 커밋 확인 가능.

### Step 2 (B200) — git pull + hf download + 학습

```bash
cd /NHNHOME/WORKSPACE/26moe002_H/mwchoi/cnu-ai-agent
git pull origin main
.venv/bin/hf download chaeminu/cnu-korus-trajectories-v2 \
  --repo-type dataset --local-dir .
# trajectories/ + data/ 가 떨어짐 — 이름이 dataset 안에서는 그대로
mv trajectories trajectories_v2 || true  # path 일관성
mv data data_v2 || true

# Verify
ls trajectories_v2/ | wc -l   # 60
wc -l data_v2/*.jsonl         # 728 + 146
```

### Step 3 (B200) — 학습 시작

```bash
nohup .venv/bin/python -m cnu_agent.training.qlora_sft \
  --train data_v2/korus_train.jsonl \
  --eval  data_v2/korus_eval.jsonl \
  --out   ckpt/qwen25vl-korus-lora-v2 \
  --epochs 3 \
  --max-seq 8192 \
  --batch 1 \
  --grad-accum 8 \
  --logging-steps 5 \
  --no-flash-attn \
  --max-image-tokens 512 \
  > /tmp/sft_v2.log 2>&1 &

echo "PID=$!" > /tmp/sft_v2.pid

# 진행 확인 (아무 때나)
ps -p $(cat /tmp/sft_v2.pid) >/dev/null 2>&1 && echo "running" || echo "done"
grep "'loss':" /tmp/sft_v2.log | tail -5
```

### 예상 학습 시간

| 항목 | v0 | **v2 예상** |
|---|---|---|
| Train sample | 234 | **728 (×3.1)** |
| Effective batch size | 8 | 8 |
| Update steps × epoch | 30 × 3 = 90 | 91 × 3 = **273** |
| Time per step (B200) | ~22s | ~22s |
| **Total 학습 시간** | 33분 | **~100분 (1h 40min)** |

---

## 6. ⚠️ 알아둘 점

| 항목 | 내용 |
|---|---|
| Eval split | task_id 단위. v2도 같은 seed의 다른 paraphrase가 train/eval 양쪽 — strict generalization 측정 아님 (이전 리포트 §6.3.5와 동일 이슈) |
| 안전성 | 60 trajectory × 874 step audit — mutating click 0건 |
| `draft_trip` 1/4 | 출장 폼 입력 복잡. 추가 fix 필요 (다음 미팅 후) |
| Ubuntu 배포 | 메모리 저장됨 — Phase 4 진입 시 headless 또는 Xvfb 검증 필요 |

---

## 7. 다음 마일스톤

1. **v2 학습** (B200, ~100분) — Step 3 명령
2. **Phase 4 진입** — vLLM serve + held-out 추론 평가
3. **mock 결재선 setup 후 mutating 실 수집** — 실제 결재 완결까지
4. **Ubuntu 배포 검증** — `headless=True` smoke or `xvfb-run` 래퍼

---

## Appendix — 자동 chain 실행 로그

| 단계 | 시작 | 종료 | 산출 |
|---|---|---|---|
| paraphrase v2 (15 seed × 4) | 00:50 | 00:55 | 60 task |
| collect v2 (1차) | 00:55 | 04:08 (kill) | 22 traj, 9 success |
| retry fix commit | 04:08 | 04:09 | commit 0642a5a |
| collect v2 (재실행) | 04:09 | **13:33 완료** | 60 traj, 47 success |
| Phase 2 변환 | 13:34 | 13:34 | data_v2/ |
| HF Hub 업로드 | 13:34 | 13:35 | dataset commit a5e1362+b89f114 |
| 최종 리포트 | 13:35 | 13:35 | 이 파일 |

총 active wall-clock: ~12시간 (00:50 → 13:35). 대부분 collect 시간.
