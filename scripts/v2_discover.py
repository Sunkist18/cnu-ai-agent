"""v2 discover — survey 21 seed의 KORUS 실제 메뉴 path 탐색.

기존 discover.py의 인프라(Tools, ChatClaudeCode, Browser)를 재사용하면서
survey-focused prompt만 다르게.

목적: 21 seed의 `where` 필드를 KORUS 실제 path로 확정. seed 자체는 미리 정의된
target list를 prompt에 주입 (`v1 discover처럼 광범위 enumerate가 아니라 targeted
verification`).

Run:
  python scripts/v2_discover.py --out discovery/v2_paths.json
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
DEFAULT_OUT = REPO_ROOT / "discovery" / "v2_paths.json"


class PathFinding(BaseModel):
	seed_id: str = Field(description="찾으려는 task의 식별자")
	exists: bool = Field(description="KORUS에 해당 기능 메뉴가 존재하는가")
	menu_path: str = Field(description="찾았으면 path (예: '전자문서 > 결재 > 결재대기함'). 못 찾으면 빈 문자열")
	url_hint: str = Field(default="", description="URL/route hint (선택)")
	notes: str = Field(default="", description="관찰 메모 — 기능 형태, 위치 모호함, 권한 필요 등")


class SaveFindings(BaseModel):
	findings: list[PathFinding] = Field(description="21 seed 각각에 대한 결과")


# 21 seed v2 — survey에서 도출
V2_TARGETS = [
	# A. 공문 처리
	("incoming_inbox_review", "수신 공문/공람 함 — 매일 받은 공문 list 확인"),
	("incoming_attachment_batch_download", "수신 공문의 첨부파일을 한 번에 또는 건별 다운로드"),
	("incoming_attachment_rename_organize", "다운로드한 첨부파일 정리·이름 변경 기능 (KORUS 내장 또는 외부)"),
	("incoming_summary_email", "공문 내용을 KORUS 메일쓰기로 관련자에게 발송 (KORUS 메일 기능)"),
	("incoming_recipient_classify", "공문 수신 시 수신자(교수/대학원생/학부생) 분류·자동 라벨링 기능 존재 여부"),
	("incoming_archive_external", "공문을 외부 저장소(구글드라이브 등)로 보내는 기능 또는 다운로드 위치 변경"),
	# B. 결재 처리
	("approve_pending_review", "결재대기함 — 받은 결재 검토 + 승인/반려 직전까지"),
	("approve_preview", "결재 문서 미리보기 — 첨부 열지 않고 본문·요약 한 화면에 표시되는지"),
	("approve_batch_similar", "유사 결재 일괄 처리 — 여러 건 한 번에 승인/반려하는 기능"),
	# C. 결재 작성
	("draft_general", "일반 전자문서 기안 작성 — 폼 작성 + 결재선 지정 (상신 직전까지)"),
	("draft_domestic_trip", "국내출장신청"),
	("draft_overseas_trip", "국외출장신청"),
	("draft_trip_copy_previous", "이전 출장 결재 복사·재사용 기능"),
	("draft_leave_request", "연가/병가/유연근무·휴직 신청"),
	("draft_research_budget", "연구비·예산 결재 — 전용 메뉴 또는 일반 기안 형태"),
	# D. 첨부·등록
	("attach_approval_file", "기안 폼 안에서 파일 첨부 영역"),
	("attach_training_certificate", "법정의무교육 이수증 등록 — 어디서 업로드?"),
	# E. 조회·검색
	("view_in_progress", "진행문서함"),
	("view_completed", "완료문서 조회"),
	("search_documents_by_keyword", "키워드로 문서 검색 — '교육과정 개정' 같은 자연어/키워드 검색 기능"),
	# F. 정산
	("view_or_submit_year_end_tax", "연말정산 — 신청 또는 내역 조회"),
]

DISCOVERY_PROMPT = """\
당신은 충남대학교 KORUS(전자결재시스템) 메뉴 구조를 탐색해서, **survey에서 도출된 21개 작업**의 실제
메뉴 path 또는 기능 존재 여부를 확인합니다.

## 탐색 규칙

1. **read-only navigation only** — 메뉴 클릭·페이지 이동·폼 페이지 열기까지만.
   - 폼 입력·제출·승인·반려·상신·저장·삭제 등 mutating 액션 절대 금지.
   - 모달 떴으면 "취소"/"닫기"/"X"만.
2. **각 항목별로 결과 명확히**:
   - 메뉴 path를 명시적으로 (예: `전자문서 > 결재 > 결재대기함`)
   - 기능 형태 메모 (예: "별도 메뉴 있음" vs "기안 폼 안에 포함" vs "기능 없음")
   - 권한 부족하면 그 사실 명시
3. **이미 본 메뉴는 재방문 금지** — 효율적으로.
4. **로그인 상태 유지** — 로그아웃 절대 금지.

## 목표 — 21개 작업

각 항목의 (`seed_id`, `description`) 를 보고, KORUS에서 해당 기능을 찾으세요:

""" + "\n".join(f"- **{sid}**: {desc}" for sid, desc in V2_TARGETS) + """

## 효율 가이드

- 모든 항목을 직접 클릭해보는 게 아니라, sitemap이나 메뉴 트리에서 위치 확인만 해도 OK.
- 의심스러운 메뉴는 한 단계만 들어가서 화면 보고 판단.
- 21개 항목 다 확인했으면 즉시 `save_v2_findings` 호출 → done.
- max_steps의 70% 지점(≈ step 35)에서 모은 만큼이라도 save 먼저 호출 후 done.

## 출력 형식

각 항목별로 PathFinding 객체:
- `seed_id`: 위 목록의 식별자
- `exists`: 기능 존재 여부 (True/False)
- `menu_path`: 찾았으면 path, 못 찾았으면 빈 문자열
- `url_hint`: URL/route hint (있으면)
- `notes`: 관찰 메모 (예: "별도 메뉴 없고 기안 폼 안에 포함", "권한 필요")

## ⚠️ 안전

mutating 액션 클릭 == 실제 결재 흐름 영향. enumerate·navigation만.
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
		"Save the v2 path findings to discovery/v2_paths.json. "
		"Call this exactly once with findings for all 21 seeds before calling done.",
		param_model=SaveFindings,
	)
	async def save_v2_findings(params: SaveFindings) -> ActionResult:  # noqa: ARG001
		out_path.parent.mkdir(parents=True, exist_ok=True)
		dump = [f.model_dump() for f in params.findings]
		out_path.write_text(
			json.dumps(dump, indent=2, ensure_ascii=False) + "\n",
			encoding="utf-8",
		)
		msg = f"💾 Saved {len(dump)} findings → {out_path}"
		print(msg)
		return ActionResult(
			extracted_content=msg,
			long_term_memory=f"Saved {len(dump)} findings to {out_path.name}; now call done.",
		)

	_ = save_v2_findings
	return tools


async def run(auth_path: Path, out_path: Path, max_steps: int, url: str) -> int:
	if not auth_path.exists():
		print(f"[FAIL] storage_state 없음: {auth_path}", file=sys.stderr)
		return 2

	print(f"[INFO] auth: {auth_path}")
	print(f"[INFO] out:  {out_path}")
	print(f"[INFO] url:  {url}")
	print(f"[INFO] max_steps: {max_steps}")
	print(f"[INFO] targets: {len(V2_TARGETS)}")

	tools = _build_tools(out_path)
	llm = ChatClaudeCode()
	browser = Browser(
		headless=False,
		storage_state=str(auth_path),
		user_data_dir=None,
		allowed_domains=["*.korus.ac.kr", "*.cnu.ac.kr"],
	)

	agent = Agent(
		task=DISCOVERY_PROMPT + f"\n\n## 시작 URL\n{url} 에서 시작.",
		llm=llm,
		browser=browser,
		tools=tools,
		use_vision=False,
		use_judge=False,
		calculate_cost=False,
		max_actions_per_step=3,
		directly_open_url=False,
		llm_timeout=300,
		max_history_items=10,
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
		print(f"[FAIL] {out_path} 생성 안 됨 — agent가 save_v2_findings 호출 안 함", file=sys.stderr)
		return 3

	dump = json.loads(out_path.read_text(encoding="utf-8"))
	found = sum(1 for d in dump if d.get("exists"))
	print(f"[OK] {len(dump)}/21 findings 저장 — {found} found, {len(dump)-found} not found")
	return 0


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="KORUS v2 path 탐색")
	parser.add_argument("--auth", type=Path, default=DEFAULT_AUTH)
	parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
	parser.add_argument("--max-steps", type=int, default=50)
	parser.add_argument("--url", type=str, default=None)
	args = parser.parse_args(argv)

	url = args.url or _load_url_from_env()
	if not url:
		print("[FAIL] --url 또는 .env의 KORUS_URL 필요", file=sys.stderr)
		return 2

	return asyncio.run(run(args.auth, args.out, args.max_steps, url))


if __name__ == "__main__":
	sys.exit(main())
