"""Phase 0b — KORUS 도메인 자동 탐색 (PLAN.md §2).

Agent가 ChatClaudeCode로 KORUS 메뉴를 read-only로 enumerate해서 30~40개 task
seed를 `discovery/seeds.json`으로 저장.

핵심 안전장치:
- DISCOVERY_PROMPT가 mutating 액션(승인/반려/상신/제출/저장/삭제) 클릭을 명시적으로 금지.
- 결재 mutating 시나리오는 enumerate는 하되 클릭은 금지 — 실제 수집(Phase 1)은
  사용자가 mock 결재선 setup 후 진행.
- storage_state로 SSO 통과 — 매 실행마다 재로그인 안 함.

Run:
  python -m cnu_agent.teacher.discover \\
    --auth auth/korus_storage_state.json \\
    --out  discovery/seeds.json \\
    --max-steps 40
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from browser_use import Agent, Browser
from browser_use.agent.views import ActionResult
from browser_use.tools.service import Tools
from pydantic import BaseModel, Field

from cnu_agent.teacher.claude_code_llm import ChatClaudeCode

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
DEFAULT_AUTH = REPO_ROOT / "auth" / "korus_storage_state.json"
DEFAULT_OUT = REPO_ROOT / "discovery" / "seeds.json"


# region Schemas


class Seed(BaseModel):
	id: str = Field(description="snake_case 식별자 (예: draft_vacation, approve_pending)")
	category: str = Field(description="결재작성/결재처리/문서조회/첨부파일/결재선설정/환경설정 중 하나")
	action_name: str = Field(description="한국어 작업명 (예: '휴가신청서 작성·상신')")
	brief: str = Field(description="1-2문장 작업 요약. mutating이면 'needs mock approval line' 표기")
	where: str = Field(description="URL path 또는 메뉴 경로 (예: '전자결재 > 받은결재함')")
	requires_sensitive: bool = Field(
		description="학번/사번/실명/금액/날짜 등 사용자별 값이 필요하거나 결재 mutating이면 True"
	)


class SaveSeedsParams(BaseModel):
	seeds: list[Seed] = Field(description="enumerate한 30~40개 seed 전체")


# endregion


# region Discovery prompt — mutating 클릭 금지가 핵심

DISCOVERY_PROMPT = """\
당신은 충남대학교 KORUS(전자결재시스템) 메뉴 구조를 탐색해서, 교수·조교·공무원이
KORUS에서 할 수 있는 작업들을 30~40개로 enumerate합니다.

## 탐색 규칙 (반드시 준수)

1. **read-only navigation only** — 메뉴 클릭·페이지 이동·폼 페이지 보기까지만. 절대 입력·제출하지 않습니다.

2. **금지 액션 (절대 클릭 금지)**:
   - 결재 승인 / 반려 / 상신 / 제출 / 저장 / 임시저장 / 삭제 / 회수 / 재상신
   - 모든 "확인"·"예"·"적용"·"등록"·"추가" 버튼 (의도치 않게 데이터 변경 가능)
   이런 버튼이 보이면 클릭하지 말고 페이지 정보만 관찰.

3. **모달/팝업 처리** — 의도치 않게 모달이 떴으면 "취소"·"닫기"·"X"만 클릭. 절대 "확인"·"저장" 누르지 않음.

4. **폼 페이지 진입은 OK, 입력·제출 금지** — 결재 작성 폼이 떠도 form schema·필드 라벨 관찰만 하고
   추출. 키 입력으로 폼을 채우지 않습니다.

5. **로그인 상태 유지** — 이미 storage_state로 SSO 통과. 로그아웃 버튼 절대 클릭 금지.

## 카테고리 (실제 메뉴 보고 적절히 조정)

- `결재작성` — 휴가신청·출장신청·지출결의·구매요청·연가신청 등 (originating)
- `결재처리` — 받은 결재 검토·승인·반려 (mutating, **enumerate only, 클릭 금지**)
- `문서조회` — 진행중/완료 문서 조회·검색·필터
- `첨부파일` — 파일 첨부·다운로드 관련
- `결재선설정` — 결재선 지정·관리·즐겨찾기·대결자 설정
- `환경설정` — 알림·프로필·서명·테마 등

## 사용자 페르소나

KORUS 사용자는 충남대 **교수·조교·공무원**입니다 (학생 아님). enumerate하는 작업도 그 관점에서:
본인 휴가/출장 신청, 본인이 발의한 문서 조회, 부하 직원이 올린 결재 검토 등.

## 각 seed 형식

- `id` : snake_case (예: `draft_vacation`, `approve_pending_review`)
- `category` : 위 카테고리 중 하나
- `action_name` : 한국어 작업명 (예: "휴가신청서 작성·상신")
- `brief` : 1-2문장 작업 요약. **결재 mutating 액션이면 brief 끝에 "needs mock approval line" 명시**.
- `where` : URL path 또는 메뉴 경로 (예: `전자결재 > 받은결재함 > 대기`)
- `requires_sensitive` : bool. 학번/사번/실명/금액/날짜 같은 사용자별 입력 필요하거나
  결재 mutating이면 true.

## 종료 조건

- **25~35개** 후보 모이면 즉시 **`save_discovery_seeds(seeds=[...])`** 도구 호출 → 그 직후 `done(success=True)`.
- 카테고리별로 균형 (각 카테고리 최소 1~2개) 잡히면 quantity보다 quality 우선. 30개 넘기려고
  무리하게 클릭 많이 하지 말 것 — DOM 누적되면 응답 느려짐.
- max_steps의 70% 지점(≈ step 28)에서는 무조건 `save_discovery_seeds` 먼저 호출 후 `done`.

## 효율 가이드

- 메뉴 모달/sitemap에서 메뉴 라벨만 보고도 seed 추론 가능한 항목은 직접 클릭 들어가지 말고
  관찰만으로 enumerate. 모든 페이지를 다 들어갈 필요 없음.
- `wait`은 꼭 필요할 때만 (페이지 skeleton만 보일 때). 두 step 연속 wait 금지.
- 한 번 들어간 메뉴는 재방문 금지. 기억해서 enumerate.

## ⚠️ 다시 강조

mutating 액션 클릭 == 본인이나 동료의 실제 결재 흐름을 건드리는 incident. enumerate만 하고
클릭은 절대 금지. 결재처리 카테고리는 menu·item 목록 관찰까지만, 실제 "승인" 버튼 클릭 금지.
"""

# endregion


def _load_url_from_env() -> str | None:
	if not ENV_FILE.exists():
		return None
	for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if line.startswith("KORUS_URL="):
			return line.split("=", 1)[1].strip()
	return None


def _build_tools(out_path: Path) -> Tools:
	"""Tools registry with a custom save_discovery_seeds action that writes to out_path."""
	tools = Tools()

	@tools.action(
		"Save the enumerated KORUS task seeds to discovery/seeds.json. "
		"Call this exactly once with all 30-40 seeds before calling done.",
		param_model=SaveSeedsParams,
	)
	async def save_discovery_seeds(params: SaveSeedsParams) -> ActionResult:  # noqa: ARG001
		out_path.parent.mkdir(parents=True, exist_ok=True)
		dump = [s.model_dump() for s in params.seeds]
		out_path.write_text(
			json.dumps(dump, indent=2, ensure_ascii=False) + "\n",
			encoding="utf-8",
		)
		msg = f"💾 Saved {len(dump)} seeds → {out_path}"
		print(msg)
		return ActionResult(
			extracted_content=msg,
			long_term_memory=f"Saved {len(dump)} seeds to {out_path.name}; now call done.",
		)

	# keep a reference so static checkers don't flag the closure as unused
	_ = save_discovery_seeds
	return tools


async def run_discovery(auth_path: Path, out_path: Path, max_steps: int, url: str) -> int:
	if not auth_path.exists():
		print(f"[FAIL] storage_state 없음: {auth_path}", file=sys.stderr)
		print(
			"       먼저 `python scripts/save_auth.py`로 KORUS 로그인하고 storage_state 저장하세요.",
			file=sys.stderr,
		)
		return 2

	print(f"[INFO] auth: {auth_path}")
	print(f"[INFO] out:  {out_path}")
	print(f"[INFO] url:  {url}")
	print(f"[INFO] max_steps: {max_steps}")

	tools = _build_tools(out_path)

	llm = ChatClaudeCode()
	browser = Browser(
		headless=False,  # 사람이 SSO 흐름·메뉴 동작 눈으로 확인
		storage_state=str(auth_path),
		user_data_dir=None,
	)
	# directly_open_url=False로 task 텍스트의 URL을 자동 navigate 하지 못하게 — Agent가 직접
	# 클릭으로 메뉴를 탐색해야 menu hierarchy가 trajectory에 남음.
	agent = Agent(
		task=DISCOVERY_PROMPT + f"\n\n## 시작 URL\n{url} 에서 시작.",
		llm=llm,
		browser=browser,
		tools=tools,
		# vision은 v1에서 끔 — 첫 실행은 DOM 위주로 빠르게. 메뉴 인식 부족하면 재실행 시 켜기.
		use_vision=False,
		use_judge=False,
		calculate_cost=False,
		max_actions_per_step=3,
		directly_open_url=False,
		# DOM·history 누적이 ChatClaudeCode subprocess 응답을 90s 안에 못 맞추는 문제 대응:
		# - llm_timeout 5분으로 늘림 (browser-use 기본 90s)
		# - max_history_items 10으로 제한 (context 토큰 절감)
		# - max_clickable_elements_length 절반으로 (DOM 직렬화 길이 절감)
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
		print(
			f"[FAIL] {out_path} 생성 안 됨 — agent가 save_discovery_seeds를 호출 안 함",
			file=sys.stderr,
		)
		return 3

	dump = json.loads(out_path.read_text(encoding="utf-8"))
	print(f"[OK] {len(dump)}개 seed 저장 완료")
	return 0


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="KORUS 도메인 탐색 (Phase 0b)")
	parser.add_argument("--auth", type=Path, default=DEFAULT_AUTH, help="storage_state 파일")
	parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="seeds.json 출력 경로")
	parser.add_argument("--max-steps", type=int, default=40, help="agent 최대 step 수")
	parser.add_argument(
		"--url", type=str, default=None, help="KORUS 시작 URL (기본: .env의 KORUS_URL)"
	)
	args = parser.parse_args(argv)

	url = args.url or _load_url_from_env()
	if not url:
		print("[FAIL] --url 인자 없고 .env에도 KORUS_URL 없음", file=sys.stderr)
		return 2

	return asyncio.run(run_discovery(args.auth, args.out, args.max_steps, url))


if __name__ == "__main__":
	sys.exit(main())
