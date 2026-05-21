"""통합테스트 결과(results.csv) → all-task.xlsx 'Task 결과' 시트 병합.

매칭: 시스템 + 시스템_연번. 채우는 열: 성공 여부 / 응답 / 스텝 수 / 걸린 시간 / 스텝당 평균 시간.
원본 보존 — 출력은 별도 파일(--out, 기본 all-task-filled.xlsx).

Run:
  python scripts/merge_results_to_xlsx.py \\
    --results integration_results/results.csv \\
    --xlsx all-task.xlsx \\
    --out all-task-filled.xlsx
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path


METRIC_COLS = ["성공 여부", "응답", "스텝 수", "걸린 시간", "스텝당 평균 시간"]


def main(argv=None) -> int:
	import openpyxl

	p = argparse.ArgumentParser()
	p.add_argument("--results", type=Path, default=Path("integration_results/results.csv"))
	p.add_argument("--xlsx", type=Path, default=Path("all-task.xlsx"))
	p.add_argument("--out", type=Path, default=Path("all-task-filled.xlsx"))
	p.add_argument("--sheet", default="Task 결과")
	args = p.parse_args(argv)

	if not args.results.exists():
		print(f"[FAIL] {args.results} 없음", file=sys.stderr)
		return 2

	def _norm_num(v) -> str:
		"""연번 정규화 — '2', 2, 2.0, '2.0' 모두 '2'로."""
		if v is None:
			return ""
		try:
			return str(int(float(v)))
		except (ValueError, TypeError):
			return str(v).strip()

	# 결과 CSV: (시스템, task본문) → metrics dict  (연번이 xlsx에서 수식일 수 있어 task로 매칭)
	res: dict[tuple[str, str], dict] = {}
	with args.results.open(encoding="utf-8-sig") as f:
		for r in csv.DictReader(f):
			key = ((r.get("시스템") or "").strip(), (r.get("task") or "").strip())
			res[key] = r
	print(f"[INFO] 결과 {len(res)}건 로드")

	# 원본 복사 → 출력에 쓰기
	shutil.copy(args.xlsx, args.out)
	wb = openpyxl.load_workbook(args.out)
	ws = wb[args.sheet]

	header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
	col_idx = {name: i + 1 for i, name in enumerate(header)}  # 1-based
	sys_c = col_idx.get("시스템")
	task_c = col_idx.get("task")
	if not sys_c or not task_c:
		print(f"[FAIL] '시스템'/'task' 열 못 찾음: {header}", file=sys.stderr)
		return 2

	filled = 0
	for row in range(2, ws.max_row + 1):
		s = ws.cell(row=row, column=sys_c).value
		t = ws.cell(row=row, column=task_c).value
		if s is None or t is None:
			continue
		key = (str(s).strip(), str(t).strip())
		if key not in res:
			continue
		r = res[key]
		for mc in METRIC_COLS:
			if mc in col_idx and r.get(mc) not in (None, ""):
				ws.cell(row=row, column=col_idx[mc]).value = r[mc]
		filled += 1

	wb.save(args.out)
	print(f"[DONE] {filled}행 채움 → {args.out}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
