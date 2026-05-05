"""Phase 0b — seeds_curated.json → tasks/korus_100.json (PLAN.md §3).

각 curated seed에 대해 ChatClaudeCode로 3~4개의 자연어 task 표현을 생성.
학번/사번/실명/금액/날짜 같은 사용자별 값은 `{{my_emp_id}}`, `{{my_name}}`,
`{{amount}}`, `{{date}}` 같은 placeholder로 둠 — browser-use Agent.run(
sensitive_data={...})로 주입 시 LLM에는 placeholder만 노출, brower에는 실제 값.

페르소나: 충남대 교수·조교·공무원 (학생 아님 — paraphrase 톤 주의).

Run:
  python -m cnu_agent.teacher.paraphrase \\
    --in  discovery/seeds_curated.json \\
    --out tasks/korus_100.json \\
    --variants 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from pathlib import Path

from browser_use.llm.messages import SystemMessage, UserMessage
from pydantic import BaseModel, Field

from cnu_agent.teacher.claude_code_llm import ChatClaudeCode
from cnu_agent.teacher.discover import Seed

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN = REPO_ROOT / "discovery" / "seeds_curated.json"
DEFAULT_OUT = REPO_ROOT / "tasks" / "korus_100.json"

PLACEHOLDER_RE = re.compile(r"\{\{[a-z_]+\}\}")


# region Schemas


class Variant(BaseModel):
	text: str = Field(description="자연어 task 명령 (한국어). placeholder는 {{snake_case}} 형태")
	sensitive_keys: list[str] = Field(
		default_factory=list,
		description="text에 등장한 placeholder 키 목록 (중괄호 제외, 예: ['my_emp_id','date'])",
	)


class Variants(BaseModel):
	variants: list[Variant] = Field(description="동일 seed에 대한 3~4개 표현")


class Task(BaseModel):
	id: str
	category: str
	task: str
	seed_id: str
	requires_sensitive: bool
	sensitive_keys: list[str]


# endregion


PARAPHRASE_SYSTEM = """\
당신은 충남대학교 KORUS(전자결재시스템) 자동화 에이전트의 학습 데이터를 만드는 일을 합니다.
하나의 seed 작업이 주어지면, 충남대 **교수·조교·공무원**이 시스템에 자연어로 시킬 법한
표현을 다양하게 생성합니다.

## 사용자 페르소나
- 학생이 아닙니다. 교수·조교·공무원 본인이 자기 일을 처리하는 톤.
- 어투는 정중한 일상 한국어 (공식 문서체 X, 슬랭 X). "~해줘", "~좀 해줘", "~부탁해", "~해주세요" 자연스럽게.

## 규칙
1. **표현 다양성**: 동일 의미를 어휘·문장 구조 다르게. 짧은 명령(~10자) 1개, 보통 길이(15-30자) 1-2개,
   조건·맥락 포함 긴 명령(40자+) 1개 정도로 mix.
2. **구체 값 다양화**: 날짜·사유·문서 제목·금액은 매번 다른 값. 다만 학번/사번/실명/금액 등
   사용자별 값은 placeholder로:
     - 본인 교번/사번 → `{{my_emp_id}}`
     - 본인 이름 → `{{my_name}}`
     - 금액 → `{{amount}}`
     - 날짜 (특정 날짜를 사용자가 채워야 하는 경우) → `{{date}}`, `{{start_date}}`, `{{end_date}}`
     - 문서 번호 → `{{doc_no}}`
     - 그 외 사용자별 값은 적절한 snake_case placeholder로.
3. **placeholder 사용 시** 사용된 placeholder 키 (중괄호 제외) 를 sensitive_keys에 모두 포함.
4. **mutating seed (결재 승인/반려/상신/제출)** 의 경우: 표현은 만들되 placeholder로 어떤 결재인지
   특정해야 함. 예: "{{doc_no}} 문서 승인해줘" 또는 "내가 받은 결재 중 {{doc_title}} 건 검토 후 승인".
5. seed의 brief에 "needs mock approval line"이 있으면 무시하고 일반 사용자 명령처럼 표현. (그건
   수집 시점 안전장치 메모용이지 task 텍스트에 들어갈 내용 아님.)

## 출력 형식
Variants JSON 한 객체. variants 필드에 3~4개 Variant 객체 배열.
"""


def _build_user_prompt(seed: Seed, n_variants: int) -> str:
	return f"""\
다음 seed에 대해 {n_variants}개 자연어 task 표현을 생성하세요.

seed:
  id: {seed.id}
  category: {seed.category}
  action_name: {seed.action_name}
  brief: {seed.brief}
  where: {seed.where}
  requires_sensitive: {seed.requires_sensitive}
"""


def _validate_placeholders(text: str, sensitive_keys: list[str]) -> tuple[bool, str]:
	"""text 안의 {{...}} 토큰들이 sensitive_keys와 일치하는지 검사."""
	found = set(PLACEHOLDER_RE.findall(text))
	found_keys = {tok[2:-2] for tok in found}
	declared = set(sensitive_keys)
	if found_keys != declared:
		return False, f"placeholders {sorted(found_keys)} != sensitive_keys {sorted(declared)}"
	return True, ""


async def _paraphrase_one(llm: ChatClaudeCode, seed: Seed, n_variants: int) -> list[Variant]:
	messages = [
		SystemMessage(content=PARAPHRASE_SYSTEM),
		UserMessage(content=_build_user_prompt(seed, n_variants)),
	]
	result = await llm.ainvoke(messages, output_format=Variants)
	variants = result.completion.variants
	# 정규화: declared keys ⊆ found keys 가 아니면 sensitive_keys 재계산.
	for v in variants:
		ok, _ = _validate_placeholders(v.text, v.sensitive_keys)
		if not ok:
			recomputed = sorted({tok[2:-2] for tok in PLACEHOLDER_RE.findall(v.text)})
			v.sensitive_keys = recomputed
	return variants


async def run_paraphrase(in_path: Path, out_path: Path, n_variants: int) -> int:
	if not in_path.exists():
		print(f"[FAIL] {in_path} 없음 — 먼저 discovery + 사용자 curation 필요", file=sys.stderr)
		return 2

	seeds_raw = json.loads(in_path.read_text(encoding="utf-8"))
	seeds = [Seed.model_validate(s) for s in seeds_raw]
	print(f"[INFO] seeds: {len(seeds)}개 → variants per seed: {n_variants}")

	llm = ChatClaudeCode()

	tasks: list[Task] = []
	for i, seed in enumerate(seeds):
		print(f"[{i + 1}/{len(seeds)}] {seed.id} — paraphrasing…", flush=True)
		try:
			variants = await _paraphrase_one(llm, seed, n_variants)
		except Exception as e:  # noqa: BLE001
			print(f"  ⚠️ {seed.id} 실패: {e}", file=sys.stderr)
			continue
		for idx, v in enumerate(variants):
			tasks.append(
				Task(
					id=f"{seed.id}_{idx:02d}",
					category=seed.category,
					task=v.text,
					seed_id=seed.id,
					requires_sensitive=seed.requires_sensitive or bool(v.sensitive_keys),
					sensitive_keys=v.sensitive_keys,
				)
			)

	out_path.parent.mkdir(parents=True, exist_ok=True)
	out_path.write_text(
		json.dumps([t.model_dump() for t in tasks], indent=2, ensure_ascii=False) + "\n",
		encoding="utf-8",
	)
	print(f"[OK] {len(tasks)}개 task 저장 → {out_path}")

	# 무작위 10개 시각 검증
	sample = random.sample(tasks, min(10, len(tasks)))
	print("\n--- 무작위 10개 샘플 ---")
	for t in sample:
		print(f"  [{t.category}] {t.id}")
		print(f"    {t.task}")
		if t.sensitive_keys:
			print(f"    sensitive_keys: {t.sensitive_keys}")

	if not (90 <= len(tasks) <= 130):
		print(
			f"[WARN] task 수가 90~130 범위 밖 ({len(tasks)}) — variants 수 또는 seed 수 조정 검토",
			file=sys.stderr,
		)
	return 0


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="seed paraphrase → tasks/korus_100.json (Phase 0b)")
	parser.add_argument("--in", dest="in_path", type=Path, default=DEFAULT_IN)
	parser.add_argument("--out", dest="out_path", type=Path, default=DEFAULT_OUT)
	parser.add_argument("--variants", type=int, default=4, help="seed당 variant 수 (3~4 권장)")
	args = parser.parse_args(argv)

	return asyncio.run(run_paraphrase(args.in_path, args.out_path, args.variants))


if __name__ == "__main__":
	sys.exit(main())
