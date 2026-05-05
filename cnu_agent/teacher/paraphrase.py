"""Phase 0: seeds_curated.json → tasks/korus_100.json (LLM paraphrase로 확장).

Implementation guide: see `PLAN.md` §3.

각 seed에 대해 3~4개 자연어 표현으로 paraphrase. 학번/사번 같은 민감정보는
`{{my_emp_id}}` placeholder로 둠 (browser-use Agent.run(sensitive_data=...)와 매칭).

Run: `python -m cnu_agent.teacher.paraphrase --in discovery/seeds_curated.json --out tasks/korus_100.json`
"""

from __future__ import annotations


async def main() -> None:
	raise NotImplementedError("Implement per PLAN.md §3")


if __name__ == "__main__":
	import asyncio

	asyncio.run(main())
