"""Run the evaluation suites against the answer keys and print the metrics tables.

    python eval/run_eval.py                 # --suite short (default): all tests/fixtures/*.txt
    python eval/run_eval.py --repeat 3      # + stability across 3 runs
    python eval/run_eval.py --cases tc1,tc4 --no-llm-match
    python eval/run_eval.py --suite quick           # 7 short cases + case2: prints a cost estimate and exits
    python eval/run_eval.py --suite quick --yes     # ... and really runs (PAID API calls)
    python eval/run_eval.py --rescore eval/results/latest.json   # offline: no API, no key
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.metrics import (  # noqa: E402
    COUNT_METRICS,
    LABELS,
    NEW_METRICS,
    OLD_METRICS,
    THRESHOLDS,
    CaseReport,
    ContentJudge,
    Match,
    aggregate,
    aggregate_detail,
    evaluate_case,
    format_metric,
    match_items,
    meets,
    stability,
)
from meeting_extractor.config import load_settings  # noqa: E402
from meeting_extractor.llm import LLMClient, LLMError, load_prompt, make_llm  # noqa: E402
from meeting_extractor.models import RunResult  # noqa: E402
from meeting_extractor.parsing import load_meta, parse_file  # noqa: E402
from meeting_extractor.pipeline import load_result, prompt_versions, run  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
LONG_DIR = ROOT / "test_cases_3_muc_do (1)"
RESULTS = ROOT / "eval" / "results"
QUICK_LONG_CASE = "case2_kho_du_lieu_khong_ro_rang"

COST_SHORT_CASE = 0.026  # USD per short case analysis
COST_PER_UTTERANCE = 0.0026  # USD per utterance for long meetings
MATCH_OVERHEAD = 0.10  # extra share for the LLM content matching
EXIT_NEED_YES = 3
SUITES = ("quick", "short", "long", "all")


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
    return f"{value:.0f}" if name in COUNT_METRICS else f"{value:.1%}"


# ------------------------------------------------------------------ jobs and cost estimate


@dataclass
class Job:
    name: str
    suite: str  # "short" | "long"
    path: Path
    answer_path: Path
    meta_path: Path | None
    n_utt: int
    repeats: int

    @property
    def cost(self) -> float:
        per_run = COST_SHORT_CASE if self.suite == "short" else COST_PER_UTTERANCE * self.n_utt
        return per_run * self.repeats


@dataclass
class SuiteData:
    reports: list[CaseReport] = field(default_factory=list)
    runs_per_case: dict[str, list[list[Match]]] = field(default_factory=dict)
    run_ids: dict[str, list[str]] = field(default_factory=dict)
    repeat: int = 1


def _count_utterances(path: Path) -> int:
    return len(parse_file(path)[0])


def short_jobs(wanted: set[str], repeat: int) -> list[Job]:
    jobs = []
    for path in sorted(FIXTURES.glob("*.txt")):
        answer_path = path.with_name(f"{path.stem}.expected.json")
        if (wanted and path.stem.lower() not in wanted) or not answer_path.exists():
            continue
        meta_path = path.with_name(f"{path.stem}.meta.json")
        jobs.append(Job(path.stem, "short", path, answer_path, meta_path if meta_path.exists() else None,
                        _count_utterances(path), repeat))
    return jobs


def long_jobs(wanted: set[str], repeat: int, only: str | None = None) -> tuple[list[Job], list[str]]:
    jobs: list[Job] = []
    notes: list[str] = []
    for case_dir in sorted(p for p in LONG_DIR.glob("*") if p.is_dir()):
        if (wanted and case_dir.name.lower() not in wanted) or (only and case_dir.name != only):
            continue
        answer_path, transcript = case_dir / "expected.json", case_dir / "transcript.txt"
        if not answer_path.exists() or not transcript.exists():
            notes.append(f"Bỏ qua {case_dir.name}: chưa có expected.json (hoặc transcript.txt).")
            continue
        meta_path = case_dir / "meeting_meta.json"
        jobs.append(Job(case_dir.name, "long", transcript, answer_path, meta_path if meta_path.exists() else None,
                        _count_utterances(transcript), repeat))
    return jobs, notes


def collect_jobs(suite: str, wanted: set[str], repeat: int, repeat_long: int) -> tuple[list[Job], list[str]]:
    jobs: list[Job] = []
    notes: list[str] = []
    if suite in ("quick", "short", "all"):
        jobs += short_jobs(wanted, repeat)
    if suite in ("long", "all"):
        found, notes = long_jobs(wanted, repeat_long)
        jobs += found
    elif suite == "quick":
        found, notes = long_jobs(wanted, repeat_long, only=QUICK_LONG_CASE)
        jobs += found
    return jobs, notes


def estimate_cost(jobs: list[Job], use_judge: bool) -> tuple[float, float]:
    """(base cost, total cost incl. the matching overhead). Needs no API key."""
    base = sum(j.cost for j in jobs)
    return base, base * (1 + MATCH_OVERHEAD) if use_judge else base


def format_estimate(jobs: list[Job], use_judge: bool) -> list[str]:
    lines = ["| Ca | Bộ | Số câu | Số lần phân tích | Ước tính (USD) |", "| --- | --- | --- | --- | --- |"]
    for j in jobs:
        lines.append(f"| {j.name} | {j.suite} | {j.n_utt} | {j.repeats} | ${j.cost:.3f} |")
    base, total = estimate_cost(jobs, use_judge)
    runs = sum(j.repeats for j in jobs)
    lines.append(f"| **Tổng** | | | {runs} | ${base:.3f} |")
    if use_judge:
        lines.append(f"| + {MATCH_OVERHEAD:.0%} so khớp bằng LLM | | | | **${total:.3f}** |")
    lines.append("")
    lines.append(f"Giá mốc: ${COST_SHORT_CASE}/ca ngắn, ${COST_PER_UTTERANCE}/câu cho cuộc họp dài.")
    return lines


# ------------------------------------------------------------------ running


def _load_answer(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def execute(jobs: list[Job], llm: LLMClient, settings: Any, judge: ContentJudge | None) -> dict[str, SuiteData]:
    data: dict[str, SuiteData] = {}
    for job in jobs:
        sd = data.setdefault(job.suite, SuiteData())
        sd.repeat = max(sd.repeat, job.repeats)
        answer = _load_answer(job.answer_path)
        meta = load_meta(job.meta_path) if job.meta_path else None
        case = answer.get("case", job.name)
        sd.runs_per_case[case] = []
        for r in range(job.repeats):
            print(f"▶ {case} (lần {r + 1}/{job.repeats})", file=sys.stderr)
            try:
                result = run(job.path, meta, llm=llm, settings=settings)
            except LLMError as exc:
                print(f"  Lỗi LLM: {exc}", file=sys.stderr)
                record_failure(sd, case, bool(answer.get("known_limitation")), r, exc)
                continue
            sd.run_ids.setdefault(case, []).append(result.run_id)
            add_run(sd, case, result, answer, judge, first=(r == 0))
    return data


def record_failure(sd: SuiteData, case: str, known_limitation: bool, run_index: int, exc: Exception) -> None:
    """First-run failure = case error (non-zero exit); later failed repeats are kept in the report notes."""
    if run_index == 0:
        rep = CaseReport(case, known_limitation, [], [])
        rep.errors.append(f"Pipeline lỗi: {exc}")
        sd.reports.append(rep)
        return
    rep = next((r for r in sd.reports if r.case == case), None)
    if rep is not None:
        rep.notes.append(f"Lần chạy {run_index + 1} lỗi, bị bỏ qua khi tính độ ổn định: {exc}")


def add_run(sd: SuiteData, case: str, result: RunResult, answer: dict[str, Any], judge: ContentJudge | None,
            first: bool) -> None:
    if first:
        sd.reports.append(evaluate_case(result, answer, judge))
    items = [i for i in result.items if i.review != "rejected"]
    sd.runs_per_case.setdefault(case, []).append(match_items(answer.get("items", []), items, judge))


# ------------------------------------------------------------------ rescoring (offline)


def _stem(source_file: str) -> str:
    return re.split(r"[\\/]", source_file)[-1].rsplit(".", 1)[0]


def _long_dir_by_title(title: str | None) -> Path | None:
    if not title:
        return None
    for case_dir in LONG_DIR.glob("*"):
        meta_path = case_dir / "meeting_meta.json"
        if meta_path.exists() and json.loads(meta_path.read_text(encoding="utf-8-sig")).get("title") == title:
            return case_dir
    return None


def resolve_answer(result: RunResult, hint: str | None, overrides: dict[str, Path],
                   fallback: Path | None) -> tuple[Path | None, str]:
    """Find the answer key of a stored run: explicit KEY=FILE > fixtures by name > long case > plain --answer."""
    for key, path in overrides.items():
        if key in result.run_id or (hint and key.lower() == hint.lower()):
            return path, _suite_of(path)
    for stem in filter(None, (hint and hint.lower(), _stem(result.source_file).lower())):
        fixture = FIXTURES / f"{stem}.expected.json"
        if fixture.exists():
            return fixture, "short"
    parts = re.split(r"[\\/]", result.source_file)
    long_dir = next((LONG_DIR / p for p in parts if (LONG_DIR / p).is_dir()), None)
    long_dir = long_dir or _long_dir_by_title(result.meta.title if result.meta else None)
    if long_dir and (long_dir / "expected.json").exists():
        return long_dir / "expected.json", "long"
    if fallback:
        return fallback, _suite_of(fallback)
    return None, "short"


def _suite_of(answer_path: Path) -> str:
    return "short" if answer_path.parent.resolve() == FIXTURES.resolve() else "long"


def expand_targets(paths: list[str], runs_dir: Path) -> list[tuple[str | None, list[Path]]]:
    """latest.json -> one target per case (all its saved runs); a run directory -> a single target."""
    targets: list[tuple[str | None, list[Path]]] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.suffix == ".json":
            for case, ids in json.loads(p.read_text(encoding="utf-8")).get("run_ids", {}).items():
                targets.append((case, [runs_dir / i for i in ids]))
        elif (p / "result.json").exists():
            targets.append((None, [p]))
        else:
            raise FileNotFoundError(f"Không tìm thấy result.json hoặc latest.json tại {p}")
    return targets


def parse_answer_specs(specs: list[str]) -> tuple[dict[str, Path], Path | None]:
    overrides: dict[str, Path] = {}
    fallback: Path | None = None
    for spec in specs:
        if "=" in spec:
            key, _, file = spec.partition("=")
            overrides[key] = Path(file)
        else:
            fallback = Path(spec)
    return overrides, fallback


def rescore(paths: list[str], answer_specs: list[str], runs_dir: Path) -> tuple[dict[str, SuiteData], list[str]]:
    overrides, fallback = parse_answer_specs(answer_specs)
    data: dict[str, SuiteData] = {}
    notes: list[str] = []
    for hint, dirs in expand_targets(paths, runs_dir):
        results = [load_result(d) for d in dirs if (d / "result.json").exists()]
        if not results:
            notes.append(f"Bỏ qua {hint or dirs}: không có result.json.")
            continue
        answer_path, suite = resolve_answer(results[0], hint, overrides, fallback)
        if answer_path is None or not answer_path.exists():
            notes.append(f"Bỏ qua {results[0].run_id}: không tìm thấy đáp án (dùng --answer [KEY=]FILE).")
            continue
        answer = _load_answer(answer_path)
        case = answer.get("case", hint or answer_path.stem)
        sd = data.setdefault(suite, SuiteData())
        sd.repeat = max(sd.repeat, len(results))
        for idx, res in enumerate(results):
            sd.run_ids.setdefault(case, []).append(res.run_id)
            add_run(sd, case, res, answer, None, first=(idx == 0))
        notes.append(f"Chấm lại {case}: {len(results)} run, đáp án {answer_path.name}")
    return data, notes


# ------------------------------------------------------------------ rendering


def suite_stability(sd: SuiteData) -> tuple[float | None, list[str]]:
    """Stability change rate of a suite (None when it was not repeated)."""
    if sd.repeat <= 1:
        return None, []
    return stability(sd.runs_per_case)


def render_group(title: str, sd: SuiteData) -> list[str]:
    metrics = aggregate_detail(sd.reports)
    rate, stab = suite_stability(sd)
    out = [f"## {title}", ""]
    out.append(f"Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: {sd.repeat}):")
    out += ["", "| Chỉ số | Giá trị | Ngưỡng | Đạt |", "| --- | --- | --- | --- |"]
    for name in (*OLD_METRICS, *NEW_METRICS):
        value, n = metrics[name]
        op, bound = THRESHOLDS[name]
        ok = "–" if value is None else ("✅" if meets(name, value) else "❌")
        out.append(f"| {LABELS[name]} | {format_metric(name, value, n)} | {op} {fmt_metric(name, bound)} | {ok} |")
    if rate is not None:
        out.append(f"| {LABELS['stability_change_rate']} | {rate:.1%} | ≤ {fmt_metric('stability_change_rate', 0.1)} "
                   f"| {'✅' if meets('stability_change_rate', rate) else '❌'} |")
    else:
        out.append("| Độ ổn định | (chạy với `--repeat 3`) | ≤ 10% | – |")
    out += ["", "| Ca | Loại | Kết quả |", "| --- | --- | --- |"]
    for rep in sd.reports:
        kind = "giới hạn đã biết" if rep.known_limitation else "chấm điểm"
        out.append(f"| {rep.case} | {kind} | {'✅ đạt' if rep.passed else f'❌ {len(rep.errors)} lỗi'} |")
    out += _details(sd, stab)
    return out


def _details(sd: SuiteData, stab: list[str]) -> list[str]:
    out: list[str] = []
    for rep in (r for r in sd.reports if r.errors):
        out.append(f"\n**{rep.case}**")
        out += [f"- {e}" for e in rep.errors]
    notes = [(r.case, n) for r in sd.reports for n in r.notes]
    if notes:
        out.append("\nGhi chú (không tính là lỗi):")
        out += [f"- {case}: {n}" for case, n in notes]
    if stab:
        out.append("\nMục đổi trạng thái giữa các lần chạy:")
        out += [f"- {d}" for d in stab]
    out.append("")
    return out


def merge(data: dict[str, SuiteData]) -> SuiteData:
    total = SuiteData()
    for sd in data.values():
        total.reports += sd.reports
        total.runs_per_case.update(sd.runs_per_case)
        total.run_ids.update(sd.run_ids)
        total.repeat = max(total.repeat, sd.repeat)
    return total


def render_all(data: dict[str, SuiteData]) -> list[str]:
    titles = {"short": "Bộ ngắn (tests/fixtures)", "long": "Bộ dài (test_cases_3_muc_do)"}
    out: list[str] = []
    for suite in ("short", "long"):
        if suite in data:
            out += render_group(titles[suite], data[suite])
    if len(data) > 1:
        out += render_group("Tổng (ngắn + dài)", merge(data))
    return out


def metrics_json(data: dict[str, SuiteData]) -> dict[str, Any]:
    groups = {**data, **({"total": merge(data)} if len(data) > 1 else {})}
    return {
        name: {k: {"value": v, "samples": n} for k, (v, n) in aggregate_detail(sd.reports).items()}
        for name, sd in groups.items()
    }


def known_limitations_ok(data: dict[str, SuiteData]) -> bool:
    return all(r.passed for sd in data.values() for r in sd.reports if r.known_limitation)


def old_metrics_ok(data: dict[str, SuiteData]) -> bool:
    """The six original metrics (incl. stability when repeated) on every suite, as the exit code before M3."""
    for sd in data.values():
        if any(not meets(name, value) for name, value in legacy_metrics(sd).items()):
            return False
    return True


def legacy_metrics(sd: SuiteData) -> dict[str, float]:
    metrics = aggregate(sd.reports)
    rate, _ = suite_stability(sd)
    if rate is not None:
        metrics["stability_change_rate"] = rate
    return metrics


def pipeline_errors(data: dict[str, SuiteData]) -> bool:
    return any(e.startswith("Pipeline lỗi") for sd in data.values() for r in sd.reports for e in r.errors)


# ------------------------------------------------------------------ main


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=SUITES, default="short",
                    help="quick = 7 ca ngắn + case2; short (mặc định); long; all")
    ap.add_argument("--repeat", type=int, default=1, help="Số lần chạy mỗi ca ngắn (đo độ ổn định)")
    ap.add_argument("--repeat-long", type=int, default=1, help="Số lần chạy mỗi cuộc họp dài")
    ap.add_argument("--cases", default="", help="Danh sách ca, ví dụ tc1,tc4")
    ap.add_argument("--no-llm-match", action="store_true", help="Chỉ khớp theo evidence, không dùng LLM")
    ap.add_argument("--yes", action="store_true", help="Xác nhận chạy thật (tốn tiền API)")
    ap.add_argument("--rescore", nargs="+", metavar="PATH",
                    help="Chấm lại kết quả đã lưu (latest.json hoặc thư mục runs/...), không gọi API")
    ap.add_argument("--answer", action="append", default=[], metavar="[KEY=]FILE",
                    help="Chỉ định đáp án cho --rescore; KEY là một phần run_id hoặc tên ca")
    ap.add_argument("--out", default="", help="Với --rescore: ghi bảng ra file markdown này")
    return ap


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.rescore:
        return main_rescore(args)

    wanted = {c.strip().lower() for c in args.cases.split(",") if c.strip()}
    jobs, notes = collect_jobs(args.suite, wanted, args.repeat, args.repeat_long)
    for n in notes:
        print(f"Ghi chú: {n}", file=sys.stderr)
    if not jobs:
        print("Không có ca kiểm thử nào.", file=sys.stderr)
        return 1
    print("\n".join(["# Ước tính chi phí (chưa gọi API)", "", *format_estimate(jobs, not args.no_llm_match)]))
    if not args.yes:
        print("\nChưa chạy gì. Thêm cờ --yes để chạy thật (sẽ tốn tiền API).", file=sys.stderr)
        return EXIT_NEED_YES

    settings = load_settings()
    try:
        llm = make_llm(settings)
    except LLMError as exc:
        print(f"Lỗi: {exc}\nEval gọi API thật – cần OPENAI_API_KEY (hoặc ANTHROPIC_API_KEY nếu LLM_PROVIDER=anthropic) trong .env.", file=sys.stderr)
        return 2
    judge = None if args.no_llm_match else make_judge(llm, settings.model_light)
    started = time.time()
    data = execute(jobs, llm, settings, judge)
    if not any(sd.reports for sd in data.values()):
        print("Không có ca kiểm thử nào.", file=sys.stderr)
        return 1
    return finish(args, jobs, data, llm, settings, started, notes)


def finish(args: argparse.Namespace, jobs: list[Job], data: dict[str, SuiteData], llm: LLMClient, settings: Any,
           started: float, notes: list[str]) -> int:
    usage = llm.usage.to_dict()
    lines = [f"# Kết quả đánh giá – {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Model: `{settings.model_light}` (Agent 1, 2) / `{settings.model_strong}` (Agent 3, 4); "
             f"bộ: {args.suite}; số lần chạy ca ngắn: {args.repeat}, cuộc họp dài: {args.repeat_long}", ""]
    lines += render_all(data)
    lines += [f"Token: vào {usage['input_tokens']:,} / ra {usage['output_tokens']:,} qua {usage['calls']} lần gọi; "
              f"chi phí ước tính ≈ ${usage['cost_usd_estimate']:.4f}; thời gian {time.time() - started:.0f}s.", "",
              "Ghi chú TC6: hệ thống chỉ gắn cờ `number_check`, không thể phát hiện số sai khi không có audio. "
              "TC7: chỉ yêu cầu không có item `confirmed` bịa cho 'phương án đó'."]
    lines += [f"Ghi chú: {n}" for n in notes]
    report_md = "\n".join(lines)
    print(report_md)
    cost_by_suite = {s: {"estimate_usd": round(sum(j.cost for j in jobs if j.suite == s), 4),
                         "analyses": sum(j.repeats for j in jobs if j.suite == s)} for s in data}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "latest.md").write_text(report_md + "\n", encoding="utf-8")
    short = data.get("short")
    (RESULTS / "latest.json").write_text(json.dumps({
        "metrics": legacy_metrics(short) if short else {},
        "metrics_by_suite": metrics_json(data),
        "cases": {r.case: {"passed": r.passed, "errors": r.errors, "counts": r.counts, "suite": s}
                  for s, sd in data.items() for r in sd.reports},
        "usage": usage,
        "cost_by_suite": cost_by_suite,
        "models": [settings.model_light, settings.model_strong],
        "prompt_versions": prompt_versions(),
        "run_ids": {c: ids for sd in data.values() for c, ids in sd.run_ids.items()},
        "repeat": args.repeat,
        "repeat_long": args.repeat_long,
        "suite": args.suite,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = old_metrics_ok(data) and known_limitations_ok(data) and not pipeline_errors(data)
    return 0 if ok else 1


def main_rescore(args: argparse.Namespace) -> int:
    runs_dir = load_settings().runs_dir  # reading .env is fine; no key is needed
    try:
        data, notes = rescore(args.rescore, args.answer, runs_dir)
    except FileNotFoundError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    if not data:
        print("Không chấm lại được run nào.\n" + "\n".join(notes), file=sys.stderr)
        return 1
    lines = [f"# Chấm lại offline – {datetime.now():%Y-%m-%d %H:%M}", "",
             "Không gọi API; khớp mục chỉ theo evidence (không dùng LLM so khớp). Các run cũ chưa có nhãn mới "
             "nên chỉ số mới ở mức 0% hoặc `không áp dụng` là đúng thực tế.", ""]
    lines += render_all(data)
    lines += [f"- {n}" for n in notes]
    report_md = "\n".join(lines)
    print(report_md)
    if args.out:
        Path(args.out).write_text(report_md + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
