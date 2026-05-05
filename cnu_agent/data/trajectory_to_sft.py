"""Phase 2: trajectory JSONL + screenshots → Qwen2.5-VL ChatML JSONL.

Implementation guide: see `PLAN.md` §5.

각 step → 학습 샘플 1개 (system / user[image+text] / assistant).
- task_id 단위 80/20 split (step 단위 split은 데이터 누설).
- assistant content는 Teacher AgentOutput JSON 직렬화.
- system prompt는 Teacher가 실제로 받은 것을 그대로 (input_messages[0]).

Run: `python -m cnu_agent.data.trajectory_to_sft --in trajectories/ --out data/`
"""

from __future__ import annotations


def main() -> None:
	raise NotImplementedError("Implement per PLAN.md §5")


if __name__ == "__main__":
	main()
