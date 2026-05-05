"""Phase 1: 100 task에 대해 browser-use Agent를 Teacher (ChatClaudeCode)로 실행 → trajectory 저장.

Implementation guide: see `PLAN.md` §4.

핵심 후크:
- `agent.register_new_step_callback(step_cb)` → step별 (BrowserStateSummary, AgentOutput, n) JSONL append
- 종료 후 `agent.history.save_to_file("history.json")` → 전체 AgentHistoryList JSON

저장 구조:
    trajectories/<task_id>/
        history.json
        steps.jsonl
        screenshots/step_<n>.png

Run: `python -m cnu_agent.teacher.collect --tasks tasks/korus_100.json --out trajectories/`
"""

from __future__ import annotations


async def main() -> None:
	raise NotImplementedError("Implement per PLAN.md §4")


if __name__ == "__main__":
	import asyncio

	asyncio.run(main())
