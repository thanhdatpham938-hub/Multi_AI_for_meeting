"""Orchestrator: plain Python calling each agent in sequence (no LLM orchestration)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .agents.extractor import extract
from .agents.segmenter import segment
from .agents.tracker import track
from .agents.verifier import needs_verification, verify
from .config import PROMPTS_DIR, Settings, load_settings
from .llm import LLMClient, LLMError, load_prompt, make_llm
from .models import Item, MeetingMeta, RunResult, Topic, Utterance
from .parsing import parse_file, parse_text
from .rules import apply_rules

ProgressFn = Callable[[str, float], None]

VERIFY_FAILED_CAP = 0.5


@dataclass
class TopicResult:
    items: list[Item]
    debug: dict[str, Any] = field(default_factory=dict)


def _verify_all(
    llm: LLMClient, model: str, items: list[Item], utterances: list[Utterance]
) -> list[tuple[Item, bool, str]]:
    results = []
    for item in items:
        if not needs_verification(item):
            results.append((item, True, "không cần kiểm chứng"))
            continue
        out = verify(llm, model, item, utterances)
        results.append((item, out.passed, out.reason))
    return results


def _feedback(failures: list[tuple[Item, bool, str]]) -> str:
    lines = [f"- [{i.type.value}] \"{i.content}\" (evidence {', '.join(i.evidence)}): {reason}" for i, _, reason in failures]
    return "\n".join(lines)


def process_topic(
    llm: LLMClient,
    model_light: str,
    model_strong: str,
    topic: Topic,
    utterances: list[Utterance],
    meta: MeetingMeta | None = None,
) -> TopicResult:
    """Agent 2 → Agent 3 → Agent 4, with exactly one redo of Agent 2+3 on verify failure."""
    debug: dict[str, Any] = {}
    candidates = extract(llm, model_light, topic, utterances, meta)
    debug["extract"] = [c.model_dump(mode="json") for c in candidates]
    items = track(llm, model_strong, topic, candidates, utterances, meta)
    debug["track"] = [i.model_dump(mode="json") for i in items]

    checks = _verify_all(llm, model_strong, items, utterances)
    debug["verify"] = [{"content": i.content, "passed": ok, "reason": r} for i, ok, r in checks]
    failures = [c for c in checks if not c[1]]
    if not failures:
        return TopicResult(items=items, debug=debug)

    feedback = _feedback(failures)
    debug["retry_feedback"] = feedback
    candidates = extract(llm, model_light, topic, utterances, meta, feedback=feedback)
    debug["retry_extract"] = [c.model_dump(mode="json") for c in candidates]
    items = track(llm, model_strong, topic, candidates, utterances, meta, feedback=feedback)
    debug["retry_track"] = [i.model_dump(mode="json") for i in items]

    checks = _verify_all(llm, model_strong, items, utterances)
    debug["retry_verify"] = [{"content": i.content, "passed": ok, "reason": r} for i, ok, r in checks]
    final: list[Item] = []
    for item, ok, _ in checks:
        if not ok:
            item = item.model_copy(
                update={
                    "flags": [*item.flags, "verify_failed"],
                    "confidence": min(item.confidence, VERIFY_FAILED_CAP),
                }
            )
        final.append(item)
    return TopicResult(items=final, debug=debug)


# ---------------------------------------------------------------- full run


def prompt_versions() -> dict[str, str]:
    return {p.stem: load_prompt(p.stem).version for p in sorted(PROMPTS_DIR.glob("*.md"))}


def new_run_id(source_name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(source_name).stem)[:40] or "transcript"
    return f"{datetime.now():%Y%m%d-%H%M%S-%f}_{stem}"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_utterances(
    utterances: list[Utterance],
    source_name: str,
    meta: MeetingMeta | None = None,
    *,
    llm: LLMClient | None = None,
    settings: Settings | None = None,
    parse_warnings: list[str] | None = None,
    progress: ProgressFn | None = None,
    save: bool = True,
) -> RunResult:
    settings = settings or load_settings()
    llm = llm or make_llm(settings)
    notify = progress or (lambda _msg, _frac: None)
    warnings = list(parse_warnings or [])
    if not utterances:
        raise ValueError("Transcript không có câu hợp lệ nào (kiểm tra định dạng [mm:ss] Tên: nội dung).")

    run_id = new_run_id(source_name)
    run_dir = settings.runs_dir / run_id

    notify("Agent 1 – Chia chủ đề", 0.05)
    topics, seg_debug = segment(llm, settings.model_light, utterances, meta)
    if save:
        _write_json(run_dir / "segment.json", {"topics": [t.model_dump() for t in topics], "debug": seg_debug})

    items: list[Item] = []
    for i, topic in enumerate(topics, start=1):
        notify(f"Agent 2–4 – Chủ đề {i}/{len(topics)}: {topic.title}", 0.1 + 0.8 * (i - 1) / max(len(topics), 1))
        try:
            result = process_topic(llm, settings.model_light, settings.model_strong, topic, utterances, meta)
        except LLMError as exc:
            warnings.append(f"Chủ đề {topic.topic_id} ({topic.title}) lỗi khi gọi LLM: {exc}")
            continue
        items.extend(result.items)
        if save:
            _write_json(run_dir / f"extract_{topic.topic_id}.json", result.debug)

    notify("Quy tắc hậu kiểm", 0.92)
    items, rule_warnings = apply_rules(items, utterances, meta)
    warnings.extend(rule_warnings)

    result = RunResult(
        run_id=run_id,
        source_file=source_name,
        model_light=settings.model_light,
        model_strong=settings.model_strong,
        prompt_versions=prompt_versions(),
        utterances=utterances,
        topics=topics,
        items=items,
        warnings=warnings,
        meta=meta,
    )
    if save:
        save_result(result, run_dir)
        _write_json(run_dir / "usage.json", llm.usage.to_dict())
    notify("Hoàn tất", 1.0)
    return result


def run(
    path: str | Path,
    meta: MeetingMeta | None = None,
    *,
    llm: LLMClient | None = None,
    settings: Settings | None = None,
    progress: ProgressFn | None = None,
    save: bool = True,
) -> RunResult:
    """parse → Agent 1 → (Agent 2 → 3 → 4 per topic) → rules → runs/<run_id>/result.json"""
    utterances, warnings = parse_file(path)
    return run_utterances(utterances, str(path), meta, llm=llm, settings=settings,
                          parse_warnings=warnings, progress=progress, save=save)


def run_text(
    text: str,
    source_name: str,
    meta: MeetingMeta | None = None,
    **kwargs: Any,
) -> RunResult:
    utterances, warnings = parse_text(text, Path(source_name).suffix or ".txt")
    return run_utterances(utterances, source_name, meta, parse_warnings=warnings, **kwargs)


# ---------------------------------------------------------------- storage


def save_result(result: RunResult, run_dir: Path) -> Path:
    path = run_dir / "result.json"
    _write_json(path, result.model_dump(mode="json"))
    return path


def load_result(run_dir: str | Path) -> RunResult:
    return RunResult.model_validate_json((Path(run_dir) / "result.json").read_text(encoding="utf-8"))
