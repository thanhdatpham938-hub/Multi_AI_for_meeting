"""Calibration table: how often are items right within each confidence band?

Offline only. Reads eval/results/latest.json -> run_ids -> runs/<id>/result.json
and the answer keys in tests/fixtures. Never calls an API.

    python eval/calibration.py [--results eval/results/latest.json] [--runs-dir runs]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.metrics import accepted_statuses, match_items  # noqa: E402
from meeting_extractor.models import Item, RunResult  # noqa: E402

BANDS: list[tuple[float, float]] = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
FIXTURES = ROOT / "tests" / "fixtures"
MIN_ITEMS_NOTE = 30  # below this total the table is only indicative


@dataclass
class Band:
    low: float
    high: float
    total: int = 0
    correct: int = 0

    @property
    def rate(self) -> float | None:
        return self.correct / self.total if self.total else None

    @property
    def label(self) -> str:
        return f"{self.low:.1f}-{min(self.high, 1.0):.1f}"


def is_correct(item: Item, expected: dict[str, Any] | None) -> bool:
    """Correct = matched an answer-key item and (for decisions) has an accepted status."""
    if not expected:
        return False
    if item.type.value == "decision" and expected.get("status"):
        return item.status is not None and item.status.value in accepted_statuses(expected)
    return True


def judge_items(result: RunResult, answer: dict[str, Any]) -> list[tuple[Item, bool]]:
    """Pair every system item with a correct/incorrect verdict against the answer key."""
    matches = match_items(answer.get("items", []), result.items)
    return [(m.item, is_correct(m.item, m.expected)) for m in matches if m.item is not None]


def bucket(verdicts: list[tuple[Item, bool]]) -> list[Band]:
    bands = [Band(lo, hi) for lo, hi in BANDS]
    for item, ok in verdicts:
        for band in bands:
            if band.low <= item.confidence < band.high:
                band.total += 1
                band.correct += int(ok)
                break
    return bands


def format_table(bands: list[Band]) -> str:
    lines = ["| Khoảng tin cậy | Số mục | Đúng | Tỷ lệ đúng |", "| --- | ---: | ---: | ---: |"]
    for b in bands:
        rate = "-" if b.rate is None else f"{b.rate:.0%}"
        lines.append(f"| {b.label} | {b.total} | {b.correct} | {rate} |")
    total = sum(b.total for b in bands)
    lines.append(f"\nTổng: {total} mục.")
    if total < MIN_ITEMS_NOTE:
        lines.append("Lưu ý: số mục quá ít, bảng chỉ mang tính tham khảo, chưa có ý nghĩa thống kê.")
    return "\n".join(lines)


def collect(results_path: Path, runs_dir: Path, fixtures: Path = FIXTURES) -> tuple[list[tuple[Item, bool]], list[str]]:
    """Gather verdicts from every run listed in latest.json; skipped runs are reported, not fatal."""
    data = json.loads(results_path.read_text(encoding="utf-8"))
    verdicts: list[tuple[Item, bool]] = []
    notes: list[str] = []
    for case, run_ids in data.get("run_ids", {}).items():
        answer_path = fixtures / f"{case.lower()}.expected.json"
        if not answer_path.exists():
            notes.append(f"Bỏ qua {case}: không có đáp án {answer_path.name}")
            continue
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        for run_id in run_ids:
            path = runs_dir / run_id / "result.json"
            if not path.exists():
                notes.append(f"Bỏ qua {run_id}: không có {path}")
                continue
            verdicts += judge_items(RunResult.model_validate_json(path.read_text(encoding="utf-8")), answer)
    return verdicts, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "eval" / "results" / "latest.json")
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "runs")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not args.results.exists():
        print(f"Không tìm thấy {args.results}", file=sys.stderr)
        return 1
    verdicts, notes = collect(args.results, args.runs_dir)
    print(format_table(bucket(verdicts)))
    for note in notes:
        print(note, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
