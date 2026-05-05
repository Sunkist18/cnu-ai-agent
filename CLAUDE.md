# CLAUDE.md

학교 컨테이너 환경 (단일 B200, Clunix, `/NHNHOME/WORKSPACE`)에서 작업 중인 Claude Code를 위한 onboarding.

## 시작하기 전에 반드시 읽기

1. **`PLAN.md`** — ground truth. Phase -1 ~ Phase 4 단계별 산출물·구현 디테일·검증 절차가 다 들어있다. 사용자 확인을 받아 작성된 plan이라 지금 단계에서는 plan을 따르는 게 기본. plan과 다른 방향이 필요하면 사용자에게 먼저 알릴 것.
2. **`PLAN.md` 상단 ⚠️ ToS 섹션** — Anthropic Commercial Terms · Claude Max 구독 약관과 distillation 충돌 가능성. 사용자가 본인 책임으로 진행한다고 결정한 상태이지만, 실제 데이터 수집 시작 전 한 번 더 환기.

## 현재 상태

- Phase -1 (repo bootstrap) 완료된 상태로 clone 받음.
- `cnu_agent/` 안의 stub 파일들은 docstring + `raise NotImplementedError`만 있음. PLAN.md §1~§7 참고해서 채우는 게 다음 작업.

## 코드 스타일

- Python ≥ 3.11. 모던 typing (`str | None`, `list[str]`).
- 비동기는 `async`/`await` (browser-use가 async).
- Pydantic v2 모델 사용.
- 들여쓰기는 탭 (browser-use 본체와 동일하게).
- `from uuid_extensions import uuid7str` + `Field(default_factory=uuid7str)`로 ID 생성.

## 테스트

```bash
uv run pytest -vxs tests/
```

테스트는 `tests/cnu_agent/` 안. browser-use mock은 쓰지 말고 real Agent + pytest-httpserver 패턴 따름. Claude Agent SDK 호출은 unit test에서 stub 가능 (subprocess 실제 호출은 통합 테스트로 분리).

## 데이터·체크포인트 위치

- Trajectory: `/NHNHOME/WORKSPACE/cnu-ai-agent/trajectories/<task_id>/`
- 학습 데이터: `/NHNHOME/WORKSPACE/cnu-ai-agent/data/`
- 모델 체크포인트: `/NHNHOME/WORKSPACE/cnu-ai-agent/ckpt/`

`.gitignore`에 위 경로 다 들어있음 — 절대 commit 금지 (스크린샷에 민감정보 포함 가능).

## browser-use 본체 코드 위치

PyPI dep으로 받았으므로 `.venv/lib/python3.11/site-packages/browser_use/...`에 있다. PLAN.md의 "주요 파일 참조" 섹션이 가리키는 라인 번호는 browser-use 0.2.x 기준. 구버전·신버전 차이 있으면 grep으로 함수명 찾아 보정.
