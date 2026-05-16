"""Attachment extraction — KORUS 공문 첨부파일 (HWP/HWPX/PDF/DOCX/XLSX) → Markdown/JSON.

조교 설문 응답에 따르면 "첨부파일 다운로드 후 본문 확인 → 요약 → 관련자 메일 발송"이
매일 반복되는 핵심 워크플로. browser-use Agent는 첨부 파일 binary 자체를 못 읽으므로
다운로드된 파일을 텍스트로 추출해서 agent context에 주입해야 함.

엔진: **kordoc** (Node.js, `vendor/kordoc-local/`에 설치) — HWP/HWPX/HWPML/PDF/DOCX/XLSX
모두 한 도구로 처리. AI-native Markdown/JSON 출력.

이미지 (.png/.jpg/.jpeg)는 변환 없이 path만 반환 — Qwen2.5-VL이 vision으로 직접 처리.

Run (직접 테스트):
  python -m cnu_agent.teacher.attachments /tmp/test.hwpx
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
KORDOC_DIR = REPO_ROOT / "vendor" / "kordoc-local"

# kordoc이 직접 다루는 확장자 (변환 가능)
KORDOC_EXTS = {".hwp", ".hwpx", ".hwpml", ".pdf", ".docx", ".xlsx"}
# Qwen vision이 직접 처리 (변환 불필요)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
# 일반 텍스트 (그냥 읽음)
TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".xml", ".html"}


@dataclass
class ExtractResult:
	success: bool
	file_type: str  # 'document' | 'image' | 'text' | 'unsupported' | 'error'
	markdown: str | None = None  # 문서 변환 결과 (텍스트 형태)
	blocks: list[dict] | None = None  # kordoc 구조화 블록 (선택)
	metadata: dict | None = None
	image_path: str | None = None  # 이미지인 경우 절대 경로 (Qwen vision 입력용)
	error: str | None = None

	def to_dict(self) -> dict[str, Any]:
		return {
			"success": self.success,
			"file_type": self.file_type,
			"markdown": self.markdown,
			"blocks_count": len(self.blocks) if self.blocks else 0,
			"metadata": self.metadata,
			"image_path": self.image_path,
			"error": self.error,
		}


def _run_kordoc_json(path: Path) -> dict:
	"""kordoc CLI로 path를 JSON으로 변환. ESM 환경에서 실행되려면 kordoc-local 디렉토리 안에서 실행."""
	cmd = [
		"npx",
		"--yes",
		"--package",
		"kordoc",
		"--package",
		"pdfjs-dist",
		"kordoc",
		str(path.resolve()),
		"--format",
		"json",
		"--silent",
	]
	result = subprocess.run(
		cmd,
		cwd=str(KORDOC_DIR),
		capture_output=True,
		text=True,
		timeout=120,
	)
	if result.returncode != 0:
		raise RuntimeError(f"kordoc CLI failed (rc={result.returncode}): {result.stderr[-300:]}")
	# stdout has JSON
	try:
		return json.loads(result.stdout)
	except json.JSONDecodeError as e:
		raise RuntimeError(f"kordoc JSON parse failed: {e}; stdout head: {result.stdout[:200]}")


def extract(path: str | Path, *, max_markdown_chars: int = 8000) -> ExtractResult:
	"""파일 1개 추출. 타입에 따라 적절한 처리.

	Args:
		path: 파일 경로 (절대 또는 상대).
		max_markdown_chars: markdown 출력 truncation. agent context bloat 방지.

	Returns:
		ExtractResult — success/file_type/markdown/image_path/error.
	"""
	p = Path(path).expanduser()
	if not p.exists():
		return ExtractResult(success=False, file_type="error", error=f"file not found: {p}")
	if not p.is_file():
		return ExtractResult(success=False, file_type="error", error=f"not a file: {p}")

	ext = p.suffix.lower()

	# 1. 이미지 — Qwen vision에 그대로 넘김
	if ext in IMAGE_EXTS:
		return ExtractResult(
			success=True,
			file_type="image",
			image_path=str(p.resolve()),
			metadata={"size_bytes": p.stat().st_size},
		)

	# 2. 일반 텍스트
	if ext in TEXT_EXTS:
		try:
			text = p.read_text(encoding="utf-8", errors="replace")
			return ExtractResult(
				success=True,
				file_type="text",
				markdown=text[:max_markdown_chars],
				metadata={"size_bytes": p.stat().st_size, "truncated": len(text) > max_markdown_chars},
			)
		except Exception as e:  # noqa: BLE001
			return ExtractResult(success=False, file_type="error", error=f"text read failed: {e}")

	# 3. kordoc 지원 문서
	if ext in KORDOC_EXTS:
		if not (KORDOC_DIR / "node_modules" / "kordoc").exists():
			return ExtractResult(
				success=False,
				file_type="error",
				error=f"kordoc not installed at {KORDOC_DIR}. Run: cd vendor/kordoc-local && npm install kordoc pdfjs-dist",
			)
		try:
			data = _run_kordoc_json(p)
		except Exception as e:  # noqa: BLE001
			return ExtractResult(success=False, file_type="error", error=str(e))

		md = data.get("markdown") or ""
		truncated = len(md) > max_markdown_chars
		return ExtractResult(
			success=bool(data.get("success", True)),
			file_type="document",
			markdown=md[:max_markdown_chars],
			blocks=data.get("blocks"),
			metadata={
				**(data.get("metadata") or {}),
				"ext": ext,
				"size_bytes": p.stat().st_size,
				"truncated": truncated,
			},
			error=data.get("error"),
		)

	# 4. 미지원 확장자
	return ExtractResult(
		success=False,
		file_type="unsupported",
		error=f"확장자 {ext} 지원 안 함. KORDOC_EXTS={sorted(KORDOC_EXTS)} or IMAGE_EXTS={sorted(IMAGE_EXTS)}",
	)


def main(argv: list[str] | None = None) -> int:
	"""CLI: python -m cnu_agent.teacher.attachments <file>"""
	args = argv if argv is not None else sys.argv[1:]
	if not args:
		print("Usage: python -m cnu_agent.teacher.attachments <file>", file=sys.stderr)
		return 2
	result = extract(args[0])
	print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
	if result.success and result.markdown:
		print("\n--- markdown (앞 1000자) ---")
		print(result.markdown[:1000])
	return 0 if result.success else 1


if __name__ == "__main__":
	sys.exit(main())
