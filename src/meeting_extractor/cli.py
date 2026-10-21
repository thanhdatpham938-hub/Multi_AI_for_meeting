"""Command line entry point.

    python -m meeting_extractor.cli run tests/fixtures/tc1.txt --meta meta.json
    python -m meeting_extractor.cli export runs/<run_id> --format xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .export import export_run
from .llm import LLMError
from .parsing import load_meta
from .pipeline import run, run_audio

STATUS_ICON = {"confirmed": "✔", "conditional": "◐", "deferred": "⏸", "open": "?", "proposed": "…", "superseded": "✗"}


def _print_result(result) -> None:
    print(f"Run: {result.run_id}  ({len(result.utterances)} câu, {len(result.topics)} chủ đề, {len(result.items)} mục)")
    for t in result.topics:
        print(f"  [{t.topic_id}] {t.title}{' (ngoài agenda)' if t.is_off_agenda else ''}: {', '.join(t.utterance_ids)}")
    print()
    for i in result.items:
        status = i.status.value if i.status else "-"
        extra = []
        if i.owner:
            extra.append(f"owner={i.owner}")
        if i.deadline:
            extra.append(f"deadline={i.deadline}")
        if i.condition:
            extra.append(f"điều kiện={i.condition}")
        print(f"{i.item_id:4} {i.type.value:10} {STATUS_ICON.get(status, ' ')} {status:11} "
              f"conf={i.confidence:.2f} {i.content}  {' '.join(extra)}")
        print(f"     evidence={i.evidence} flags={i.flags}")
    if result.warnings:
        print("\nCảnh báo:")
        for w in result.warnings:
            print(f"  - {w}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="meeting_extractor", description="Trích xuất quyết định từ transcript họp")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Phân tích một transcript .txt/.vtt hoặc file audio")
    p_run.add_argument("path", type=Path)
    p_run.add_argument("--audio", action="store_true", help="Coi file là audio (mặc định tự nhận theo đuôi mp3/m4a/wav/mp4)")
    p_run.add_argument("--meta", type=Path, default=None, help="File meeting_meta.json (tùy chọn)")

    p_exp = sub.add_parser("export", help="Xuất kết quả một lần chạy")
    p_exp.add_argument("run_dir", type=Path)
    p_exp.add_argument("--format", choices=["json", "xlsx"], default="xlsx")
    p_exp.add_argument("--all", action="store_true", help="Xuất cả mục chưa duyệt (để duyệt trong Excel)")

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            runner = run_audio if args.audio else run
            result = runner(args.path, load_meta(args.meta), progress=lambda msg, _f: print(f"… {msg}", file=sys.stderr))
            _print_result(result)
            print(f"\nĐã lưu: runs/{result.run_id}/result.json")
        else:
            path = export_run(args.run_dir, args.format, only_reviewed=not args.all)
            print(f"Đã xuất: {path}")
    except (LLMError, ValueError, FileNotFoundError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
