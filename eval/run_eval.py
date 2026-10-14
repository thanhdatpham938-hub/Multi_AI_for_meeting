"""Run the full fixture suite against the answer key and print the §9 metrics table.

    python eval/run_eval.py                 # all tests/fixtures/*.txt
    python eval/run_eval.py --repeat 3      # + stability across 3 runs
    python eval/run_eval.py --cases tc1,tc4 --no-llm-match
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.metrics import (  # noqa: E402
    LABELS,
    THRESHOLDS,
    CaseReport,
    ContentJudge,
    Match,
    aggregate,
    evaluate_case,
    match_items,
    meets,
    stability,
)
from meeting_extractor.config import load_settings  # noqa: E402
from meeting_extractor.llm import LLMClient, LLMError, load_prompt, make_llm  # noqa: E402
from meeting_extractor.parsing import load_meta  # noqa: E402
from meeting_extractor.pipeline import prompt_versions, run  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
RESULTS = ROOT / "eval" / "results"


class MatchOutput(BaseModel):
    same: bool


def make_judge(llm: LLMClient, model: str) -> ContentJudge:
    prompt = load_prompt("match")

    def judge(a: str, b: str) -> bool:
        user = prompt.render(A=a, B=b)
        return llm.complete_json(model=model, system=prompt.system, user=user, schema=MatchOutput,
                                 purpose="match").same

    return judge


def fmt_metric(name: str, value: float) -> str:
    return f"{value:.0f}" if name == "fabricated_fields" else f"{value:.1%}"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1, help="Số lần chạy mỗi ca (đo độ ổn định)")
    ap.add_argument("--cases", default="", help="Danh sách ca, ví dụ tc1,tc4")
    ap.add_argument("--no-llm-match", action="store_true", help="Chỉ khớp theo evidence, không dùng LLM")
    args = ap.parse_args(argv)

    settings = load_settings()
    try:
        llm = make_llm(settings)
    except LLMError as exc:
        print(f"Lỗi: {exc}\nEval gọi API thật – cần OPENAI_API_KEY (hoặc ANTHROPIC_API_KEY nếu LLM_PROVIDER=anthropic) trong .env.", file=sys.stderr)
        return 2
    judge = None if args.no_llm_match else make_judge(llm, settings.model_light)

    wanted = {c.strip().lower() for c in args.cases.split(",") if c.strip()}
    cases = [p for p in sorted(FIXTURES.glob("*.txt")) if not wanted or p.stem.lower() in wanted]
    started = time.time()
    reports: list[CaseReport] = []
    runs_per_case: dict[str, list[list[Match]]] = {}
    run_ids: dict[str, list[str]] = {}

    for path in cases:
        answer_path = path.with_name(f"{path.stem}.expected.json")
        if not answer_path.exists():
            continue
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        meta_path = path.with_name(f"{path.stem}.meta.json")
        meta = load_meta(meta_path) if meta_path.exists() else None
        case = answer.get("case", path.stem)
        runs_per_case[case] = []
        for r in range(args.repeat):
            print(f"▶ {case} (lần {r + 1}/{args.repeat})", file=sys.stderr)
            try:
                result = run(path, meta, llm=llm, settings=settings)
            except LLMError as exc:
                print(f"  Lỗi LLM: {exc}", file=sys.stderr)
                rep = CaseReport(case, bool(answer.get("known_limitation")), [], [])
                rep.errors.append(f"Pipeline lỗi: {exc}")
                if r == 0:
                    reports.append(rep)
                continue
            run_ids.setdefault(case, []).append(result.run_id)
            if r == 0:
                reports.append(evaluate_case(result, answer, judge))
            items = [i for i in result.items if i.review != "rejected"]
            runs_per_case[case].append(match_items(answer.get("items", []), items, judge))

    if not reports:
        print("Không có ca kiểm thử nào.", file=sys.stderr)
        return 1

    metrics = aggregate(reports)
    stab_details: list[str] = []
    if args.repeat > 1:
        metrics["stability_change_rate"], stab_details = stability(runs_per_case)

    lines: list[str] = []
    out = lines.append
    out(f"# Kết quả đánh giá – {datetime.now():%Y-%m-%d %H:%M}")
    out("")
    out(f"Model: `{settings.model_light}` (Agent 1, 2) / `{settings.model_strong}` (Agent 3, 4); "
        f"số lần chạy mỗi ca: {args.repeat}")
    out("")
    out("Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (TC1–TC5):")
    out("")
    out("| Chỉ số | Giá trị | Ngưỡng | Đạt |")
    out("| --- | --- | --- | --- |")
    for name, value in metrics.items():
        op, bound = THRESHOLDS[name]
        bound_s = fmt_metric(name, bound)
        out(f"| {LABELS[name]} | {fmt_metric(name, value)} | {op} {bound_s} | {'✅' if meets(name, value) else '❌'} |")
    if args.repeat == 1:
        out("| Độ ổn định | (chạy với `--repeat 3`) | ≤ 10% | – |")
    out("")
    out("| Ca | Loại | Kết quả |")
    out("| --- | --- | --- |")
    for rep in reports:
        kind = "giới hạn đã biết" if rep.known_limitation else "chấm điểm"
        out(f"| {rep.case} | {kind} | {'✅ đạt' if rep.passed else f'❌ {len(rep.errors)} lỗi'} |")
    out("")
    failing = [r for r in reports if r.errors]
    if failing:
        out("## Chi tiết ca sai")
        for rep in failing:
            out(f"\n**{rep.case}**")
            for e in rep.errors:
                out(f"- {e}")
    if stab_details:
        out("\n## Mục đổi trạng thái giữa các lần chạy")
        for d in stab_details:
            out(f"- {d}")
    usage = llm.usage.to_dict()
    out("")
    out(f"Token: vào {usage['input_tokens']:,} / ra {usage['output_tokens']:,} qua {usage['calls']} lần gọi; "
        f"chi phí ước tính ≈ ${usage['cost_usd_estimate']:.4f}; thời gian {time.time() - started:.0f}s.")
    out("")
    out("Ghi chú TC6: hệ thống chỉ gắn cờ `number_check`, không thể phát hiện số sai khi không có audio. "
        "TC7: chỉ yêu cầu không có item `confirmed` bịa cho 'phương án đó'.")
    report_md = "\n".join(lines)
    print(report_md)

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "latest.md").write_text(report_md + "\n", encoding="utf-8")
    (RESULTS / "latest.json").write_text(json.dumps({
        "metrics": metrics,
        "cases": {r.case: {"passed": r.passed, "errors": r.errors, "counts": r.counts} for r in reports},
        "usage": usage,
        "models": [settings.model_light, settings.model_strong],
        "prompt_versions": prompt_versions(),
        "run_ids": run_ids,
        "repeat": args.repeat,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    all_ok = all(meets(k, v) for k, v in metrics.items()) and all(
        r.passed for r in reports if r.known_limitation
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
