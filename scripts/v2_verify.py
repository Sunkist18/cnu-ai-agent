"""v2 verify — 첫 v2_discover에서 표면만 확인된 8개 항목을 *실제 기능* 단까지 검증.

차이점:
- v2_discover.py: 메뉴 path 존재 여부만 (sitemap·메뉴트리 확인)
- v2_verify.py:  메뉴 들어가서 폼·버튼·인터랙션 실제 동작 확인 + 발견된 button 이름까지 기록

target 8개:
1. approve_preview — 결재대기함 문서 열어서 본문 미리보기 가능한지 (첨부 안 열고)
2. draft_trip_copy_previous — 출장 폼에 "이전 결재 복사" 버튼 있는지
3. attach_training_certificate — 의무교육 이수증 등록 위치
4. draft_overseas_trip — 복무>출장 폼에 국외 옵션 / 별도 메뉴
5. draft_research_budget — 연구비·예산·지출 키워드 폼 / 별도 메뉴
6. incoming_recipient_classify — 자동 라우팅 vs 수동 수신처 필드
7. search_documents_by_keyword — 진행문서함/완료문서 검색 실제 키워드 테스트
8. approve_batch_similar — 결재대기함 멀티셀렉트 + 일괄 승인 (공람 batch read와 별개)

Run:
  python scripts/v2_verify.py --out discovery/v2_verify.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from browser_use import Agent, Browser
from browser_use.agent.views import ActionResult
from browser_use.tools.service import Tools
from pydantic import BaseModel, Field

from cnu_agent.teacher.claude_code_llm import ChatClaudeCode

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
DEFAULT_AUTH = REPO_ROOT / "auth" / "korus_storage_state.json"
DEFAULT_OUT = REPO_ROOT / "discovery" / "v2_verify.json"


class VerifyFinding(BaseModel):
	target_id: str = Field(description="검증 대상 식별자 (예: approve_preview)")
	feature_present: bool = Field(description="실제 기능이 KORUS에 있는가 (메뉴 존재 ≠ 기능 동작)")
	how_to_use: str = Field(
		default="",
		description="기능 사용 절차 (예: '결재대기함 > 문서 클릭 > 우측 패널 본문 표시'). 없으면 빈 문자열.",
	)
	button_labels: list[str] = Field(
		default_factory=list,
		description="해당 화면에서 발견된 관련 버튼/링크 라벨 (예: ['미리보기', '재상신', '복사'])",
	)
	limitations: str = Field(default="", description="제약/관찰 (예: '첨부 PDF만 미리보기, HWP는 불가')")
	screenshot_hint: str = Field(default="", description="검증 시점의 페이지 URL 또는 메뉴 위치")


class SaveVerifyFindings(BaseModel):
	findings: list[VerifyFinding] = Field(description="8개 target 각각의 검증 결과")


VERIFY_TARGETS = [
	(
		"approve_preview",
		"결재대기함에 들어가서 **문서 한 건을 클릭**해보고, 본문이 우측 미리보기 패널 또는 modal에 "
		"바로 표시되는지 확인. 첨부파일을 클릭해서 다운로드하지 말고, 본문이 자체적으로 보이는지만. "
		"미리보기 UI 발견 시 어떤 버튼·영역인지 기록.",
	),
	(
		"draft_trip_copy_previous",
		"전자문서 > 기안 > 전체서식에서 '출장' 검색해서 **국내출장신청 폼을 직접 열어보고**, "
		"폼 상단/하단에 '이전 결재 복사', '재사용', '복사하여 작성' 같은 버튼이 있는지 확인. "
		"또는 진행문서함/완료문서에서 출장 문서를 선택했을 때 '복사' 옵션 있는지.",
	),
	(
		"attach_training_certificate",
		"의무교육 이수증 등록할 수 있는 메뉴 위치 확인. 후보: 인사관리, 성과관리>교육훈련, "
		"개인설정 등. 'sitemap'에서 '의무교육', '이수증', '교육이수' 키워드로 검색. "
		"별도 메뉴면 path 기록, 일반 기안 폼이면 어떤 서식 이름인지.",
	),
	(
		"draft_overseas_trip",
		"전자문서 > 기안 > 전체서식에서 '국외출장' 또는 '해외' 검색. 결과로 나온 폼이 있다면 "
		"'국내출장신청'과 별도 폼인지 확인. 별도 폼이면 두 seed 분리, 같은 폼에 국내/국외 옵션 "
		"라디오만 있으면 통합 가능.",
	),
	(
		"draft_research_budget",
		"전자문서 > 기안 > 전체서식 search box에 차례로 입력: '연구비', '예산', '지출', "
		"'출장비', '연구과제비'. 어떤 키워드에서 어떤 폼이 나오는지 기록. "
		"또는 '연구관리', '예산관리' 같은 별도 상단 메뉴가 있는지 확인.",
	),
	(
		"incoming_recipient_classify",
		"전자문서 > 공유/공람 > 받은문서에서 임의 1건 클릭. 화면에 '수신처', '담당자 지정', "
		"'전달' 같은 기능이 있는지. 자동 라우팅이 아니라 사용자가 수동으로 수신처 설정·전달하는 "
		"필드가 있는지 확인 (있으면 agent가 본문 읽고 수동 설정 자동화 가능).",
	),
	(
		"search_documents_by_keyword",
		"전자문서 > 결재 > 진행문서함 또는 완료문서함 페이지의 **검색 필드**에 '교육과정' 또는 "
		"'출장' 같은 일반 키워드 1개 입력해서 실제 검색 동작 여부 확인. 결과 건수와 사용 가능한 "
		"필터(제목/내용/기안자/날짜 등) 기록.",
	),
	(
		"approve_batch_similar",
		"전자문서 > 결재 > 결재대기함 (공람대기 아님!) 으로 이동해서, 문서 list에 **체크박스 + "
		"일괄 승인/반려 버튼** 있는지 확인. 공람의 '읽기처리'(읽음 표시)와는 다른 진짜 결재 "
		"승인이어야 함. 있으면 버튼 라벨 기록, 없으면 단건씩만 처리하는 게 확인됨.",
	),
]

VERIFY_PROMPT = """\
당신은 충남대학교 KORUS(전자결재시스템)에서 8개 기능의 **실제 동작 여부**를 검증합니다.
첫 discover에서는 메뉴 존재만 확인했고, 이번엔 들어가서 진짜 기능 작동을 봐야 합니다.

## 탐색 규칙

1. **read-only navigation only** — 메뉴 클릭·페이지 이동·폼 열기·검색 입력까지만.
   - 제출/저장/승인/반려/상신/임시저장/삭제 등 mutating 액션 절대 금지.
   - 폼은 열어서 UI 관찰만, 입력 후 검색 버튼 누르는 건 OK (검색은 mutating 아님).
2. **이미 본 메뉴는 효율적으로** — 같은 페이지 반복 방문 금지.
3. **로그아웃 절대 금지**.

## 검증 목표 — 8개 항목

각 항목별로 메뉴 들어가서 실제 기능 확인:

""" + "\n\n".join(
	f"### {i+1}. {tid}\n{desc}" for i, (tid, desc) in enumerate(VERIFY_TARGETS)
) + """

## 출력 형식

VerifyFinding 객체별:
- `target_id`: 위 목록의 식별자
- `feature_present`: 진짜 기능 동작 여부 (메뉴 존재 != 기능 동작)
- `how_to_use`: 실제 사용 절차
- `button_labels`: 화면에서 본 관련 버튼·링크 라벨 list
- `limitations`: 제약·관찰
- `screenshot_hint`: 검증 시점의 URL/메뉴 위치

## 종료 조건

- 8개 다 확인하면 `save_v2_verify_findings` 호출 → done.
- max_steps의 80% (≈ step 48) 에서 모은 만큼이라도 save 먼저 호출 후 done.

## ⚠️ 안전

mutating 클릭 == 실제 결재 흐름 영향. 검증·navigation·검색까지만.
"""


def _load_url_from_env() -> str | None:
	if not ENV_FILE.exists():
		return None
	for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if line.startswith("KORUS_URL="):
			return line.split("=", 1)[1].strip()
	return None


def _build_tools(out_path: Path) -> Tools:
	tools = Tools()

	@tools.action(
		"Save the v2 verify findings to discovery/v2_verify.json. "
		"Call this exactly once after verifying all 8 targets, then call done.",
		param_model=SaveVerifyFindings,
	)
	async def save_v2_verify_findings(params: SaveVerifyFindings) -> ActionResult:  # noqa: ARG001
		out_path.parent.mkdir(parents=True, exist_ok=True)
		dump = [f.model_dump() for f in params.findings]
		out_path.write_text(
			json.dumps(dump, indent=2, ensure_ascii=False) + "\n",
			encoding="utf-8",
		)
		msg = f"💾 Saved {len(dump)} verify findings → {out_path}"
		print(msg)
		return ActionResult(
			extracted_content=msg,
			long_term_memory=f"Saved {len(dump)} v2 verify findings; now call done.",
		)

	_ = save_v2_verify_findings
	return tools


async def run(auth_path: Path, out_path: Path, max_steps: int, url: str) -> int:
	if not auth_path.exists():
		print(f"[FAIL] storage_state 없음: {auth_path}", file=sys.stderr)
		return 2

	print(f"[INFO] auth: {auth_path}")
	print(f"[INFO] out:  {out_path}")
	print(f"[INFO] targets: {len(VERIFY_TARGETS)}")
	print(f"[INFO] max_steps: {max_steps}")

	tools = _build_tools(out_path)
	llm = ChatClaudeCode()
	browser = Browser(
		headless=False,
		storage_state=str(auth_path),
		user_data_dir=None,
		allowed_domains=["*.korus.ac.kr", "*.cnu.ac.kr"],
	)

	agent = Agent(
		task=VERIFY_PROMPT + f"\n\n## 시작 URL\n{url}",
		llm=llm,
		browser=browser,
		tools=tools,
		use_vision=False,
		use_judge=False,
		calculate_cost=False,
		max_actions_per_step=3,
		directly_open_url=False,
		llm_timeout=300,
		max_history_items=12,
		max_clickable_elements_length=20000,
	)
	try:
		history = await agent.run(max_steps=max_steps)
	finally:
		try:
			await browser.kill()
		except Exception:  # noqa: BLE001
			pass

	steps = len(history.history)
	is_done = history.is_done()
	print(f"[E2E] steps={steps}  is_done={is_done}")

	if not out_path.exists():
		print(f"[FAIL] {out_path} 생성 안 됨 — agent가 save_v2_verify_findings 호출 안 함", file=sys.stderr)
		return 3

	dump = json.loads(out_path.read_text(encoding="utf-8"))
	present = sum(1 for d in dump if d.get("feature_present"))
	print(f"[OK] {len(dump)}/8 findings — {present} feature present, {len(dump)-present} not present")
	return 0


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="KORUS v2 deep verify")
	parser.add_argument("--auth", type=Path, default=DEFAULT_AUTH)
	parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
	parser.add_argument("--max-steps", type=int, default=60)
	parser.add_argument("--url", type=str, default=None)
	args = parser.parse_args(argv)

	url = args.url or _load_url_from_env()
	if not url:
		print("[FAIL] --url 또는 .env의 KORUS_URL 필요", file=sys.stderr)
		return 2

	return asyncio.run(run(args.auth, args.out, args.max_steps, url))


if __name__ == "__main__":
	sys.exit(main())
