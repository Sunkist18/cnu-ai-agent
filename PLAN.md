# CNU AI Agent — Teacher-Student 데이터 파이프라인 (KORUS 1차)

## Context

충남대학교 학내 웹플랫폼을 자연어 명령으로 자동 조작하는 에이전트를 만드는 게 최종 목표. 1차 범위는 **전자결재시스템 KORUS 단일 도메인, 100 trajectory**. browser-use를 실행 프레임워크로 두고, Teacher (Claude via Claude Agent SDK headless)가 KORUS task를 푸는 동안 매 step의 (관측, 사고, 액션) 튜플을 그대로 캡처해서, Qwen2.5-VL-32B를 QLoRA SFT로 도메인 적응시키는 행동복제(Behavioral Cloning) 파이프라인이다.

핵심 아이디어: browser-use의 `BaseChatModel` Protocol이 LLM 교체를 깔끔히 지원하므로, Teacher 단계에서는 `ChatClaudeCode`(우리가 작성)를, Student 추론 단계에서는 `ChatOpenAILike`(vLLM-served Qwen)를 그대로 끼워넣으면 된다. trajectory도 `register_new_step_callback`을 통해 코드 변경 없이 바깥에서 수집 가능.

---

## 결정 사항 정리

| 항목 | 결정 |
|------|------|
| Teacher | Claude Max + `claude-agent-sdk` (Python, headless) |
| Student | Qwen2.5-VL-32B (Instruct) + LoRA SFT (bf16) |
| Modality | DOM 직렬화 + Screenshot (멀티모달) |
| 도메인 | KORUS 전자결재시스템 (단일) |
| Trajectory 수 | 100 |
| Eval split | 80 train / 20 held-out |
| 학습 GPU | NVIDIA B200, 183GB HBM3e (단일) |
| 수집 머신 | 학교 **맥북** (macOS, 학내망에서 KORUS 접근) — Phase 0~2, 4 |
| 학습 서버 | **B200 컨테이너** — Phase 3 만. 작업 디렉토리: `/NHNHOME/WORKSPACE/26moe002_H/<your-id>/` (학생 5명 공용 폴더 안 본인 폴더). lustre1 마운트 2TB. root는 작아 venv는 본인 폴더 안에. |
| Phase 4 네트워크 | B200 학내망 진입 여부에 따라 결정. 진입 가능 → B200에서 vLLM serve + browser-use도 동일 머신에서. 미진입 → vLLM은 B200, 브라우저는 맥북, ChatOpenAILike(base_url=...)을 SSH tunnel/reverse proxy로 연결. 학습 끝난 후 결정. |
| Repo | 별도 GitHub repo `Sunkist18/cnu-ai-agent` (browser-use는 PyPI dep) |

---

## ⚠️ 사용자 확인이 필요한 ToS 이슈

Anthropic Commercial Terms는 일반적으로 *"서비스 출력으로 경쟁 LLM을 학습/distill 시키는 것 금지"* 조항을 포함한다. Qwen2.5-VL은 비-Anthropic 모델이므로 이 조항에 해당될 가능성이 높음. Max 구독 ToS도 동일 조항을 따를 가능성 큼. **본 plan은 사용자가 위 리스크를 인지·수용한다는 전제 하에 작성**되었으며, 학내 연구·교육 목적의 예외가 적용되는지 본인이 https://www.anthropic.com/legal/commercial-terms 와 Max 구독 약관을 직접 확인할 책임이 있음. 만약 위반 위험이 크다고 판단되면 Anthropic API + Batch (~$30~80) 또는 Gemini Flash로 라우팅 변경하면 되며, plan의 다른 부분은 그대로 유효함.

---

## Phase -1: Repo Bootstrap (지금 머신, 학교 이전 전) ✅ 완료

KORUS는 학내망 IP에서만 접근 가능 → 데이터 수집은 학교 맥북, 학습은 별도 B200 서버. 지금 머신(개인 PC)은 plan + skeleton만 만들어 GitHub에 올리고, 학교 환경에서 clone 후 살을 붙인다.

순서:

1. 별도 GitHub repo `Sunkist18/cnu-ai-agent` 생성 (private). browser-use는 PyPI dep으로 받음 — fork 안 함.
2. 로컬에 디렉토리 만들고 (`C:\Users\mass_\Documents\sandbox\cnu-ai-agent`) skeleton 작성:
   ```
   cnu-ai-agent/
   ├── pyproject.toml          # browser-use, claude-agent-sdk, transformers, trl, peft, bitsandbytes, vllm, pillow
   ├── README.md               # 한 페이지 quickstart (학교 환경 셋업 + 진행 단계)
   ├── PLAN.md                 # 이 plan을 그대로 옮긴 ground truth
   ├── CLAUDE.md               # 학교 Claude Code용 짧은 onboarding (PLAN.md 읽고 시작하라)
   ├── cnu_agent/
   │   ├── __init__.py
   │   ├── teacher/
   │   │   ├── __init__.py
   │   │   ├── claude_code_llm.py     # stub: BaseChatModel subclass, NotImplementedError
   │   │   ├── discover.py            # stub
   │   │   ├── paraphrase.py          # stub
   │   │   └── collect.py             # stub
   │   ├── data/
   │   │   ├── __init__.py
   │   │   └── trajectory_to_sft.py   # stub
   │   ├── training/
   │   │   ├── __init__.py
   │   │   └── qlora_sft.py           # stub (LoRA bf16 default, --quantize fallback)
   │   └── student/
   │       ├── __init__.py
   │       └── serve_and_run.py       # stub
   ├── tests/
   │   └── cnu_agent/
   │       ├── test_claude_code_llm.py
   │       └── test_trajectory_conversion.py
   └── .gitignore              # trajectories/, ckpt/, screenshots/, *.png, *.jsonl
   ```
   stub들은 import만 하고 docstring으로 "학교 환경에서 PLAN.md §N 참고해 구현"이라고 표시. 학교 Claude Code가 PLAN.md 읽고 stub 채우는 게 task가 됨.
3. 학교 환경 셋업 — 두 머신 분리:

   **(a) 맥북 (Phase 0~2, 4)** — 수집·변환·평가 모두 여기서. KORUS 접근은 학내 wifi/VPN.
   ```bash
   git clone https://github.com/Sunkist18/cnu-ai-agent.git
   cd cnu-ai-agent
   uv venv --python 3.11
   uv sync --extra dev
   # Claude Code 실행 후 "PLAN.md 읽고 Phase 0a부터 진행해줘"
   ```

   **(b) B200 학습 서버 (Phase 3 만)** — LoRA SFT 1회 돌리는 게 전부.
   ```bash
   cd /NHNHOME/WORKSPACE/26moe002_H/<your-id>   # 본인 학생 폴더 (예: mwchoi)
   git clone https://github.com/Sunkist18/cnu-ai-agent.git
   cd cnu-ai-agent
   uv venv --python 3.11   # root 작으니 venv는 본인 폴더 안 (.venv)
   uv sync --extra training --extra serve
   # 학습 데이터는 맥북에서 rsync로 옮겨오기:
   #   (맥북에서) rsync -av data/ <user>@<b200>:/NHNHOME/WORKSPACE/26moe002_H/<your-id>/cnu-ai-agent/data/
   python -m cnu_agent.training.qlora_sft \
       --train data/korus_train.jsonl --eval data/korus_eval.jsonl \
       --out ckpt/qwen25vl-korus-lora
   ```

**ToS 재확인**: 학교 환경에서 Claude Code 시작하기 전, 위 ⚠️ 섹션 한 번 더 확인하고 진행. ToS 위배가 우려되면 plan의 ChatClaudeCode 부분만 ChatAnthropic + Batch API 또는 다른 provider로 바꾸면 나머지는 그대로 유효.

---

## 아키텍처 개요

```
┌───────────────────────────────────────────────────────────┐
│ Phase 0: Domain Discovery (1회성)                          │
│                                                           │
│   browser-use Agent ─ llm=ChatClaudeCode                  │
│        │ task = "KORUS 메뉴를 둘러보고 가능한 작업을        │
│        │         JSON 리스트로 출력해줘"                    │
│        ▼                                                  │
│   discovery/seeds.json  (~30 task seed, 카테고리·난이도)   │
│        │                                                  │
│        ▼  사람 quick review (5~10분)                       │
│   discovery/seeds_curated.json (≤30개 확정)                │
│        │                                                  │
│        ▼  LLM paraphrase (각 seed → 3~4 표현)              │
│   tasks/korus_100.json (~100~120개)                       │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
┌───────────────────────────────────────────────────────────┐
│ Phase 1: Teacher Trajectory 수집 (1회성)                   │
│                                                           │
│   tasks/korus_100.json                                    │
│        │                                                  │
│        ▼                                                  │
│   browser-use Agent ───── llm=ChatClaudeCode ─────┐       │
│        │                                          │       │
│        │ register_new_step_callback              ┌▼─┐     │
│        ▼                                         │CC│     │
│   trajectories/{task_id}/                        │SDK     │
│     ├── history.json  (AgentHistoryList dump)   └──┘     │
│     ├── steps.jsonl   (raw input msgs + output)          │
│     └── screenshots/step_*.png                            │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
┌───────────────────────────────────────────────────────────┐
│ 데이터 변환 단계                                            │
│                                                           │
│   steps.jsonl + screenshots → Qwen2.5-VL chat format      │
│   { "messages": [                                         │
│       {"role":"system", "content": "..."},               │
│       {"role":"user", "content":[                         │
│            {"type":"image","image":"step_3.png"},         │
│            {"type":"text","text":"<DOM>...</DOM>..."}]}, │
│       {"role":"assistant","content":"{...AgentOutput...}"}│
│   ]}                                                      │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
┌───────────────────────────────────────────────────────────┐
│ Training (QLoRA SFT)                                      │
│   Qwen/Qwen2.5-VL-32B-Instruct + 4bit + LoRA r=16         │
│   trl.SFTTrainer + peft + bitsandbytes                    │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
┌───────────────────────────────────────────────────────────┐
│ Inference 단계                                             │
│   vLLM serve qwen2.5-vl-32b-korus-lora                    │
│   browser-use Agent ─ llm=ChatOpenAILike(base_url=...)     │
└───────────────────────────────────────────────────────────┘
```

---

## 구현 단계 (파일별)

새 코드는 `cnu_agent/`라는 별도 패키지에 두자. browser-use 본체는 건드리지 않는다 — 외부에서 wrap만 한다. 새 디렉토리 구조:

```
cnu_agent/
├── teacher/
│   ├── claude_code_llm.py     # ChatClaudeCode (BaseChatModel 구현)
│   ├── discover.py            # Phase 0: KORUS 메뉴 탐색 → seeds.json
│   ├── paraphrase.py          # Phase 0: seeds → 100 task 확장
│   └── collect.py             # Phase 1: 100 task 실행 + trajectory 저장
├── data/
│   └── trajectory_to_sft.py   # JSONL → Qwen ChatML 변환
├── training/
│   └── qlora_sft.py           # trl SFTTrainer 학습 스크립트
└── student/
    └── serve_and_run.py       # vLLM serve → Agent 실행 데모
```

### 1. `cnu_agent/teacher/claude_code_llm.py` — Claude Code를 BaseChatModel로 래핑

핵심 기술 결정: browser-use의 `ainvoke(messages, output_format) -> ChatInvokeCompletion[T]`는 single-turn structured output을 기대. Claude Code는 multi-turn tool-loop이 기본이라, **tools를 빈 배열로 강제**하고 **system prompt에 "JSON schema X에 맞춰서만 응답"**을 추가하는 방식으로 강제 단일 응답을 받는다.

구현 골자:
- `claude-agent-sdk` (Python)의 `query()` async generator 사용
- BaseChatModel의 `ainvoke(messages, output_format)` 안에서:
  1. messages를 Claude Code가 이해하는 prompt 텍스트로 직렬화 (system + user 텍스트, 이미지는 base64 inline)
  2. `output_format` (Pydantic class)이 있으면 `model_json_schema()`를 system instruction에 주입
  3. `query(prompt=..., options=ClaudeAgentOptions(allowed_tools=[], system_prompt_override=...))` 호출
  4. async iter 결과에서 final assistant text를 모아 JSON 파싱 → `output_format.model_validate_json(...)`
  5. `ChatInvokeCompletion(completion=..., usage=...)` 반환
- `--bare` 플래그 사용으로 hooks/skills/CLAUDE.md 제외해 startup 시간 단축
- 호출당 ~1~3s subprocess 오버헤드는 100 trajectory × ~10 step ≈ 1000 콜 → 약 30~50분으로 수용 가능

참고할 browser-use 코드:
- `browser_use/llm/base.py:18-59` — `BaseChatModel` Protocol 시그니처
- `browser_use/llm/views.py:32-49` — `ChatInvokeCompletion`
- `browser_use/llm/anthropic/chat.py` — 가장 가까운 reference 구현
- `browser_use/llm/messages.py:75-83` — 이미지 임베딩 (`ContentPartImageParam`)

### 2. `cnu_agent/teacher/discover.py` — Phase 0: KORUS 메뉴 탐색

100 task를 사람이 처음부터 정의하지 않고, 동일한 browser-use + Claude 인프라로 site discovery를 1회 돌려서 task seed를 자동 추출. 별도 브라우저 확장 도입은 인프라 중복이라 배제.

설계:
- `Agent(task=DISCOVERY_PROMPT, llm=ChatClaudeCode(), max_steps=40)`로 1회 실행
- DISCOVERY_PROMPT 골자: *"KORUS 메인 메뉴부터 시작해서 모든 1차/2차 메뉴를 클릭해 들어가 보고, 각 페이지에서 사용자가 할 수 있는 핵심 작업을 JSON 리스트로 출력해줘. 각 항목은 `{category, action_name, brief, where, requires_sensitive}` 필드로. 결재 승인/반려처럼 되돌릴 수 없는 액션은 `requires_sensitive: true`로 표시. 30~40개 후보를 만들고, 카테고리는 결재작성/결재처리/문서조회/첨부파일/결재선설정/환경설정 정도로 분류해."*
- Custom tool `@tools.action("save_discovery_seeds")`를 등록해서 Agent가 마지막에 결과를 `discovery/seeds.json`으로 저장하게 함 (browser-use Tools 패턴, README FAQ 참조)
- 출력 예시:
  ```json
  [
    {"id": "draft_vacation", "category": "draft", "action_name": "휴가신청서 작성·상신", "brief": "양식 선택 후 기간/사유 입력, 결재선 지정해 상신", "where": "/draft/new?form=vacation", "requires_sensitive": false},
    {"id": "approve_pending", "category": "approve", "action_name": "결재함 대기 문서 승인", "brief": "결재함 대기 탭에서 첫 문서 검토 후 승인", "where": "/inbox/pending", "requires_sensitive": true},
    ...
  ]
  ```
- 사용자가 `seeds.json`을 5~10분 quick review해서 (a) 권한 없는 항목, (b) 중복, (c) `requires_sensitive: true`인데 mock 안 만든 것 제거 → `seeds_curated.json` (≤30개)

### 3. `cnu_agent/teacher/paraphrase.py` — Phase 0: seed → 100개 task

curated seed 30개 각각에 대해 LLM (Claude)에게 3~4개 자연어 표현으로 paraphrase 요청.

```python
# 의사 코드
for seed in seeds_curated:
    variants = await claude_paraphrase(
        seed,
        n=4,
        instruction="동일한 작업을 학생이 부탁할 법한 다양한 자연어 명령으로 표현해줘. "
                    "구체적 값(날짜, 사유 등)은 매번 다르게 채워. 학번/사번 같은 민감정보는 "
                    "{{my_emp_id}} 같은 placeholder로 둬."
    )
    for v in variants:
        tasks.append({
            "id": f"{seed['id']}_{v.idx:02d}",
            "category": seed["category"],
            "task": v.text,
            "seed_id": seed["id"],
            "requires_sensitive": seed["requires_sensitive"],
        })
# tasks 길이 ~100~120 → 100개로 trim
```

paraphrase는 SFT 표현 다양성에 기여. 100 trajectory 같은 작은 셋에서는 동일 의미 다른 표현 학습이 generalization에 효과적.

login flow는 Phase 0/1 공통으로 task 외부에서 미리 한 번 처리 (`browser_use` real browser profile 활용해서 세션 쿠키 재사용). KORUS 인증이 SSO인지 ID/PW인지에 따라 분기 — 사용자가 한 번 수동 로그인 후 cookie storage_state를 저장하면 그 뒤로는 비로그인 task만 실행하면 된다.

**민감정보 주의**: 학번, 사번, 실명 등은 placeholder로 (`{{my_emp_id}}` 식)두고 `Agent(...).run(sensitive_data={...})`로 주입. browser-use의 sensitive_data 기능이 LLM에는 placeholder만 보여주고 브라우저에는 실제 값을 넣음 — trajectory에도 placeholder만 남아 학습 데이터가 안전.

### 4. `cnu_agent/teacher/collect.py` — Phase 1 수집 러너

핵심 후크 두 군데:
- `register_new_step_callback(step_callback)` — `(BrowserStateSummary, AgentOutput, step_num)`을 받아서 raw step JSONL append
- `agent.history.save_to_file(...)` — run 종료 후 전체 AgentHistoryList JSON 저장

저장 포맷 (`steps.jsonl`):
```json
{
  "task_id": "draft_001",
  "step": 3,
  "url": "https://korus.cnu.ac.kr/...",
  "screenshot_path": "trajectories/draft_001/screenshots/step_3.png",
  "input_messages": [ ... browser_use가 LLM으로 보낸 messages 그대로 ... ],
  "model_output": { "thinking": "...", "action": [{"click": {"index": 5}}] },
  "interacted_element": { "backend_node_id": ..., "selector": "..." }
}
```

input_messages 캡처 위치는 `browser_use/agent/message_manager/service.py:545` 의 `last_input_messages`. `register_new_step_callback`이 호출되는 시점에 이미 채워져 있으므로 `agent._message_manager.last_input_messages`로 접근 (또는 깔끔하게 `Agent`를 subclass해서 `_get_next_action` 직후에 캡처하는 게 안전).

실행:
```bash
python -m cnu_agent.teacher.collect --tasks korus --out trajectories/ --n 100
```

### 5. `cnu_agent/data/trajectory_to_sft.py` — Qwen2.5-VL ChatML로 변환

각 step → 학습 샘플 1개로 매핑. Qwen2.5-VL의 표준 chat format은:
```python
{
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "image", "image": "file://abs/path/step_3.png"},
            {"type": "text",  "text": dom_serialized + "\n\nTask: " + task + "\n\nHistory: ..."},
        ]},
        {"role": "assistant", "content": json.dumps(model_output)},
    ]
}
```

System prompt는 browser-use가 실제로 사용한 것을 그대로 쓴다 — `browser_use/agent/system_prompt.md` (혹은 step별 input_messages[0])에 들어있는 내용. **Teacher와 Student가 동일한 system prompt를 받아야 distillation이 의미 있음**.

input_messages에서 user content 추출 시 주의: browser-use는 system + user(state) + assistant(prev) + user(state) 식으로 누적되는 multi-turn 구조라서, 가장 마지막 user turn만 학습 입력으로 쓰고 그 이전 turn들은 history 텍스트로 압축. 이게 single-step BC의 표준 형태.

held-out split: task_id 단위로 80/20 분리 (step 단위가 아니라 task 단위! step 단위로 자르면 같은 trajectory의 step이 train/eval 양쪽에 들어가서 데이터 누설).

### 6. `cnu_agent/training/qlora_sft.py` — LoRA SFT (B200 183GB 기준)

팀원이 QLoRA로 정착한 상태지만, **B200 183GB**에서는 32B를 bf16으로 통째로 올려도 ~64GB라 quantization 없이 LoRA만으로 충분 (QLoRA의 4bit 양자화는 메모리 절감용 — 메모리가 남으면 bf16 LoRA가 학습 안정성 측면에서 더 유리). 그래서 **기본 = LoRA bf16**, fallback = QLoRA 4bit (코드에 `--quantize` 플래그로 토글 가능하게).

LoRA = **Lo**w-**R**ank **A**daptation. 32B 베이스를 freeze, target module들에 rank ~16~32 어댑터만 학습. 단일 B200으로 충분 (분산 불필요).

```python
# 핵심 deps
# uv add transformers>=4.46 trl>=0.12 peft>=0.13 accelerate datasets pillow
# (선택) uv add bitsandbytes  # quantize fallback 시
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from peft import LoraConfig
from trl import SFTTrainer, SFTConfig
import torch

model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2.5-VL-32B-Instruct",
    torch_dtype=torch.bfloat16,
    device_map="auto",  # 단일 B200이라 사실상 cuda:0
    attn_implementation="flash_attention_2",  # B200 + CUDA 13 지원
)

lora = LoraConfig(
    r=32, lora_alpha=64, lora_dropout=0.05,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    # ViT는 freeze — 텍스트 어댑터만 학습이 일반적 패턴
)

trainer = SFTTrainer(
    model=model, args=SFTConfig(
        output_dir="ckpt/qwen25vl-korus-lora",
        per_device_train_batch_size=2, gradient_accumulation_steps=4,
        learning_rate=2e-4, num_train_epochs=3,
        bf16=True, gradient_checkpointing=True, max_seq_length=16384,
        # B200 메모리 여유 → batch와 max_seq_length 둘 다 키움
    ),
    train_dataset=ds_train, eval_dataset=ds_eval,
    peft_config=lora, processing_class=processor,
)
trainer.train()
```

100 trajectory × ~10 step = ~800 train sample이라 **3 epoch도 5~15분 안에 끝**. 핵심은 학습 시간이 아니라 데이터 품질.

**컨테이너 환경 메모**: 학생 폴더는 `/NHNHOME/WORKSPACE/26moe002_H/<your-id>/` (lustre1 마운트, 2TB). repo도 ckpt도 모두 그 안. root volume은 작으니 venv·model cache는 절대 root에 두지 말 것. uv가 컨테이너에 없으면 `pip install -e ".[training]"`로 fallback. HuggingFace cache는 `HF_HOME=/NHNHOME/WORKSPACE/26moe002_H/<your-id>/.cache/huggingface` 등으로 본인 폴더 안에 redirect.

### 7. `cnu_agent/student/serve_and_run.py` — vLLM serve + browser-use 통합

학습 끝난 LoRA를 vLLM으로 띄우고, browser-use에서 OpenAI 호환 endpoint로 호출.

```bash
# vLLM serve
vllm serve Qwen/Qwen2.5-VL-32B-Instruct \
    --enable-lora --lora-modules korus=ckpt/qwen25vl-korus-lora \
    --port 8000 --max-model-len 16384
```

```python
# browser-use 측
from browser_use import Agent, Browser
from browser_use.llm.openai.like import ChatOpenAILike

llm = ChatOpenAILike(model="korus", base_url="http://localhost:8000/v1", api_key="dummy")
agent = Agent(task="휴가신청서 작성해서 상신해줘", llm=llm, browser=Browser())
await agent.run()
```

`ChatOpenAILike`는 `browser_use/llm/openai/like.py`에 이미 존재. 멀티모달 입력은 `ChatOpenAI` serializer가 base64 이미지를 OpenAI vision content part로 변환하는 걸 그대로 사용 (`browser_use/llm/openai/serializer.py:36-40`).

---

## KORUS 도메인별 추가 고려사항

- **iframe**: 학내 결재 시스템은 보통 메뉴/본문이 iframe으로 분리됨. browser-use의 DOM serializer는 iframe을 처리하지만 selector_map 인덱스가 iframe 내부 element도 포함하는지 데이터 수집 첫 5개 trajectory에서 수동 확인 필요.
- **세션 만료**: 결재 시스템은 보통 30분 idle timeout. trajectory 수집 중 한 task가 길어지면 만료될 수 있으니 task당 max_steps=30 정도로 제한, 만료 감지 시 task skip.
- **민감 액션**: "결재 승인/반려"는 되돌릴 수 없는 액션. 데이터 수집 중에는 **테스트 계정 또는 본인 명의 비공식 문서만** 사용하거나, 결재선의 마지막 결재자가 본인인 mock 결재를 만들어두고 거기서만 작업.

---

## Verification — end-to-end 테스트 절차

### Phase 0a: pipeline plumbing 검증 (ChatClaudeCode 작성 직후)
1. ChatClaudeCode unit test — 단순 Pydantic schema 1개 (`class Foo(BaseModel): x: int`)로 ainvoke 호출해서 valid 결과 받는지
2. browser-use Agent에 ChatClaudeCode를 끼워서 `task="Open google.com and report the title"` 같은 trivial task 1회 실행해서 step loop이 도는지

### Phase 0b: Discovery run + paraphrase
1. `discover.py` 실행 → `discovery/seeds.json` 생성. 사람이 5~10분 검토해서 ≤30개로 trim.
2. `paraphrase.py` 실행 → `tasks/korus_100.json` 생성. 무작위 10개 표본 검토해서 자연스러운지, sensitive placeholder가 잘 들어갔는지 확인.

### Phase 1: Trajectory 수집 (~1일)
1. `collect.py` 일괄 실행 (예상 30~50분, Claude Code subprocess 오버헤드 포함)
2. 첫 1 task만 실행해서 `trajectories/<task_id>/` 디렉토리에 `history.json`, `steps.jsonl`, `screenshots/*.png`이 정상 생성되는지 1차 확인
3. `steps.jsonl`을 열어서 `input_messages`에 시스템 프롬프트 + DOM 직렬화 + 스크린샷 base64가 다 들어있고, `model_output.action`이 valid한 ActionModel JSON인지 수동 확인 → 통과하면 나머지 99 task 일괄 실행
4. 완료 후 무작위 5개 trajectory 영상(스크린샷 시퀀스) 수동 검사 → Teacher가 KORUS task를 실제로 풀어냈는지 (success rate 기록)
5. Teacher success rate < 70%면 system prompt 또는 task 명세 보강 후 재수집

### Phase 2: 데이터 변환
1. `trajectory_to_sft.py`로 변환 → 결과 ChatML JSONL 1개 샘플 출력해서 messages 구조와 이미지 path가 정상인지 확인
2. task_id 단위 80/20 split (step 단위 split은 데이터 누설 — 같은 trajectory의 step이 train/eval 양쪽에 들어감)

### Phase 3: Student 학습 (~30분)
1. QLoRA SFT 3 epoch
2. eval loss curve 확인 — train/eval gap이 비정상적으로 크면 over-fit (100 traj × 10 step은 작은 셋이라 충분히 가능). LoRA r 줄이거나 dropout 높이는 식으로 대응.

### Phase 4: Student 추론 평가 (~1일)
1. held-out 20 task로 Student 단독 실행
2. 두 가지 metric:
   - **Action accuracy** (offline): held-out trajectory의 각 step에서 Student의 top-1 action이 Teacher action과 일치하는 비율
   - **Task success rate** (online): vLLM-served Student를 browser-use Agent에 끼워서 task를 실제로 끝내는 비율
3. Action accuracy ≥ 70%, Task success rate ≥ 50%면 1차 성공으로 간주. 미달이면 trajectory 추가 수집 (200~300으로 확장) 또는 LoRA r 증가.

### 검증 자동화
- `tests/cnu_agent/test_claude_code_llm.py` — `ChatClaudeCode.ainvoke`가 BaseChatModel Protocol에 맞는 응답을 주는지 unit test (Pydantic schema 검증 포함)
- `tests/cnu_agent/test_trajectory_conversion.py` — sample trajectory 1개 → ChatML 1개 변환의 round-trip 검증

---

## 주요 파일 참조 (browser-use 본체에서 건드리지 않고 활용)

| 파일 | 라인 | 용도 |
|------|------|------|
| `browser_use/llm/base.py` | 18-59 | `BaseChatModel` Protocol — 우리 ChatClaudeCode가 구현해야 하는 인터페이스 |
| `browser_use/llm/views.py` | 32-49 | `ChatInvokeCompletion` — ainvoke 반환형 |
| `browser_use/llm/messages.py` | 29-236 | `BaseMessage`, `UserMessage`, `ContentPartImageParam` |
| `browser_use/llm/anthropic/chat.py` | 137-260 | reference 구현 (가장 가까움) |
| `browser_use/llm/openai/like.py` | 1-15 | `ChatOpenAILike` — Student 추론 시 그대로 사용 |
| `browser_use/agent/service.py` | 1942 | LLM ainvoke 호출 지점 (캡처 후크 위치 결정 참고) |
| `browser_use/agent/service.py` | 151-162 | `register_new_step_callback` 시그니처 |
| `browser_use/agent/views.py` | 388-430 | `AgentOutput` — Teacher 출력 schema |
| `browser_use/agent/views.py` | 488-627 | `AgentHistory`, `AgentHistoryList`, `save_to_file` |
| `browser_use/agent/message_manager/service.py` | 545 | `last_input_messages` (input 캡처) |
| `browser_use/dom/serializer/serializer.py` | 69-714 | DOM index가 backend_node_id 기반으로 step간 stable함을 보장 |
| `examples/models/qwen.py` | 1-28 | OpenAI 호환 endpoint 사용 reference |
| `examples/models/ollama.py` | 1-11 | 로컬 모델 사용 reference |

---

## 1차 산출물 체크리스트

- [ ] `cnu_agent/teacher/claude_code_llm.py` — Claude Agent SDK wrapper (BaseChatModel)
- [ ] `cnu_agent/teacher/discover.py` + `discovery/seeds.json` (~30 seed)
- [ ] `cnu_agent/teacher/paraphrase.py` + `tasks/korus_100.json` (~100개)
- [ ] `cnu_agent/teacher/collect.py` — 수집 러너
- [ ] `trajectories/` — 100 traj 데이터 (~수 GB, 스크린샷 포함)
- [ ] `cnu_agent/data/trajectory_to_sft.py` — ChatML 변환
- [ ] `data/korus_train.jsonl` / `data/korus_eval.jsonl`
- [ ] `cnu_agent/training/qlora_sft.py` — 학습 스크립트
- [ ] `ckpt/qwen25vl-korus-lora/` — 학습된 LoRA
- [ ] `cnu_agent/student/serve_and_run.py` — vLLM serve + 추론 데모
- [ ] eval 결과 (Action accuracy / Task success rate) 기록
- [ ] `tests/cnu_agent/` — pipeline plumbing 검증 unit tests
