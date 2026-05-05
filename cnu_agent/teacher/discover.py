"""Phase 0: KORUS site discovery — Agent가 메뉴를 둘러보며 task seed를 수집.

Implementation guide: see `PLAN.md` §2.

Output: `discovery/seeds.json` — 30~40개 후보, 각 항목은
`{id, category, action_name, brief, where, requires_sensitive}`.
사람이 직접 review해서 `discovery/seeds_curated.json` (≤30개)으로 trim.

Run: `python -m cnu_agent.teacher.discover --out discovery/`
"""

from __future__ import annotations


async def main() -> None:
	raise NotImplementedError("Implement per PLAN.md §2")


if __name__ == "__main__":
	import asyncio

	asyncio.run(main())
