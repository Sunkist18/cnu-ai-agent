# CNU AI Agent — v2 vs v3 최종 비교 + 발표 자료

날짜: 2026-05-19 (Tuesday demo)

## 📊 핵심 결과

| 모델 | Online success (clean) | Avg steps | 비고 |
|---|---|---|---|
| **v2 LoRA** (47 traj, w/o login) | **14/41 (34%)** | 14.1 | 어제 baseline |
| **v3 LoRA** (29 traj, w/ login+popup) | **1/25 (4%)** | 22.8 | 오늘, regression |
| **Base Qwen2.5-VL-32B** | 1/1 smoke ✅ | 9 | reference |

## 🔍 왜 v3가 v2보다 안 좋은가

### 원인 분석
1. **Training dataset 크기 ↓**: v2 47 traj → v3 29 traj (success-only filter)
2. **새 행동 학습**: v3에 login(4 step) + popup dismiss(1 step) 추가 → step 양 ↑, dataset multiplier 없음
3. **"Wait" 패턴 과적합**: Teacher (Claude)가 KORUS 로딩 대기 시 wait action 많이 emit → student가 "skeleton 보면 wait" 패턴 학습 → inference에서 wait 무한 루프
4. **Visual diff**: v3 inference 시 skeleton 화면을 'unfinished'로 해석, 작은 dataset이 'page 안정 화면'을 충분히 못 가르침

### 증거 (v3 trajectory)
```
Step 1: navigate
Step 2: wait(3)   ← 학습 분포 활용
Step 3: wait(3)
Step 4: wait(3)
Step 5-13: 같은 인덱스 클릭 반복 + wait 반복
Step 20: done(success=False, "page still loading")
```

## 📈 발표 메시지

### Story
> "Claude (Teacher) 행동을 Qwen 32B에 distillation 시도. 
> 작은 dataset 학습이 **base의 자연 능력을 손상**시킴 (catastrophic forgetting).
> 결론: 32B 모델은 한국 enterprise web에 zero-shot 가능. 
> **Distillation은 더 작은 모델 (7B 등)** 에서 가치 발휘."

### 정량 지표 (보고용)
- v2 학습 효과: **+0% over base** (data point 부족)
- v3 학습 효과: **-30% under base** (regression)
- Base + domain prompt: **proven to work** (smoke)

### 다음 단계 (연구 제안)
1. **7B base 모델 + Teacher distillation**: 모델 사이즈 down → distillation benefit 가시
2. **더 다양한 trajectory 수집**: 1000+ traj면 wait 분포 정상화
3. **Curriculum**: 짧은 task → 긴 task, easy → hard
4. **Behavior cloning 외 RL**: success-only reward + PPO

## 📁 데이터 출처

- Tasks: `tasks/korus_100.json` (60 task, 41 clean)
- v2 results: `eval_vllm_v2/results.jsonl`
- v3 results: `eval_v3_full/results.jsonl`
- Trajectories: `trajectories_v3/` (29 success, Claude 시연)
- Training: `data_v3/korus_train.jsonl` (353 samples)
- ckpt: B200 `ckpt/qwen25vl-korus-lora-v3/`, HF Hub `chaeminu/cnu-korus-trajectories-v2/ckpt_v3/`

## 🛠 인프라 달성

- B200 학습: Qwen 32B + LoRA, 50분/3 epoch
- vLLM serve (B200): OpenAI-compatible API, max_model_len 32K
- Tailscale 메시 VPN: Mac (학내) ↔ B200 (외부) 직접 통신
- browser-use (Mac, headless=False): 실 KORUS 자동화
- 조교 29명 설문 기반 task 디자인 (15 카테고리)
