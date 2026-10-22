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
from .agents.digest import build_digest
from .agents.reconciler import reconcile
from .agents.segmenter import merge_topics, segment
from .agents.tracker import TrackResult, candidates_to_items, track_detailed
from .agents.verifier import apply_contradiction, needs_verification, verify
from .audio import save_audio, transcribe_with_warnings
from .config import PROMPTS_DIR, Settings, load_settings
from .llm import LLMClient, LLMError, load_prompt, make_llm
from .models import HistoryEntry, Item, ItemType, MeetingMeta, RunResult, Status, Topic, Utterance
from .parsing import parse_file, parse_text
from .conflicts import flag_conflicts
from .rules import apply_rules

ProgressFn = Callable[[str, float], None]

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".mp4")

VERIFY_FAILED_CAP = 0.5


@dataclass
class TopicResult:
    items: list[Item]
    debug: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failed: bool = False  # True when any agent failed for this topic (results may be incomplete)


# One verification outcome: passed is None when Agent 4 errored or the item type is not verified.
Check = tuple[Item, bool | None, str]


def _verify_all(
    llm: LLMClient, model: str, items: list[Item], utterances: list[Utterance],
    warnings: list[str] | None = None,
) -> list[Check]:
    """Verify each item against the FULL transcript; contradicting later utterances are written onto the item.

    Warnings about dropped contradicted_by ids are appended to `warnings` when given.
    """
    results: list[Check] = []
    for item in items:
        if not needs_verification(item):
            results.append((item, None, "không cần kiểm chứng"))
            continue
        try:
            out = verify(llm, model, item, utterances)
        except LLMError as exc:
            results.append((item, None, f"LỖI: {exc}"))
            continue
        if warnings is not None:
            warnings.extend(f"Mục \"{item.content[:60]}\": {w}" for w in out.warnings)
        results.append((apply_contradiction(item, out), out.passed, out.reason))
    return results


def _feedback(failures: list[Check]) -> str:
    lines = [f"- [{i.type.value}] \"{i.content}\" (evidence {', '.join(i.evidence)}): {reason}" for i, _, reason in failures]
    return "\n".join(lines)


def _verify_errors(topic: Topic, checks: list[Check]) -> list[str]:
    return [
        f"Chủ đề {topic.topic_id} ({topic.title}): Agent 4 lỗi, mục \"{i.content[:60]}\" chưa được kiểm chứng. {r}"
        for i, ok, r in checks
        if ok is None and needs_verification(i)
    ]


def _debug_checks(checks: list[Check]) -> list[dict[str, Any]]:
    return [{"content": i.content, "passed": ok, "reason": r} for i, ok, r in checks]


def _finalize(checks: list[Check], flag_failures: bool) -> list[Item]:
    """Write verify_passed into each item; optionally flag the failed ones."""
    final: list[Item] = []
    for item, ok, _ in checks:
        update: dict[str, Any] = {"verify_passed": ok if needs_verification(item) else None}
        if ok is False and flag_failures:
            update["flags"] = [*item.flags, "verify_failed"]
            update["confidence"] = min(item.confidence, VERIFY_FAILED_CAP)
        final.append(item.model_copy(update=update))
    return final


def _track_or_fallback(
    llm: LLMClient, model: str, topic: Topic, candidates: list[Candidate],
    utterances: list[Utterance], meta: MeetingMeta | None, feedback: str | None = None,
    digest: str = "",
) -> tuple[list[Item], list[str], bool, bool]:
    """Run Agent 3; on total failure keep Agent 2's candidates.

    Returns (items, warnings, tracker_failed, dropped_any_item).
    """
    try:
        res = track_detailed(llm, model, topic, candidates, utterances, meta, feedback, digest)
    except LLMError as exc:
        warn = f"Chủ đề {topic.topic_id} ({topic.title}): Agent 3 lỗi, giữ kết quả thô của Agent 2. {exc}"
        return candidates_to_items(candidates, topic), [warn], True, False
    return res.items, res.warnings, False, res.dropped_items > 0


OVERLAP_MIN = 0.6
DEMOTION_REASON = "Kiểm chứng không đạt và lần làm lại không còn giữ kết luận này"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _same_issue(a: Item, b: Item) -> bool:
    """Same issue = same type AND shared evidence AND similar content.

    "Similar" = token overlap against the SHORTER content, |A&B| / min(|A|, |B|) >= 0.6, so a
    retry that merely trims a longer first-pass sentence still matches. Content must always agree,
    even with identical evidence: two different decisions can cite the same utterance.
    """
    if a.type != b.type or not (set(a.evidence) & set(b.evidence)):
        return False
    ta, tb = _tokens(a.content), _tokens(b.content)
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= OVERLAP_MIN


def _demote_unconfirmed(item: Item) -> Item:
    """A decision that failed verification and was not re-affirmed by the retry cannot stay confirmed."""
    if item.type != ItemType.decision or item.status != Status.confirmed:
        return item
    entry = HistoryEntry(status=Status.proposed, content=item.content, reason=DEMOTION_REASON,
                         evidence=list(item.evidence))
    return item.model_copy(update={"status": Status.proposed, "history": [*item.history, entry]})


def _merge_retry(
    llm: LLMClient, model: str, topic: Topic, utterances: list[Utterance],
    first: list[Check], retry: TrackResult, debug: dict[str, Any],
) -> tuple[list[Item], list[str], bool]:
    """Combine first-pass and retry results so the retry can never silently shrink the output.

    - First-pass items that did not fail verification are always kept; retry items matching one
      (`_same_issue`) are dropped as duplicates, with a warning quoting both contents.
    - Other retry items are verified again. A failed first-pass item is replaced only if a retry
      item matches it; otherwise it is kept with `verify_failed` (confidence <= 0.5).
    Returns (items, warnings, topic_failed).
    """
    kept_items = [c[0] for c in first if c[1] is not False]
    failed_first = [c for c in first if c[1] is False]
    warnings: list[str] = []
    replacements: list[Item] = []
    for r in retry.items:
        dup = next((k for k in kept_items if _same_issue(r, k)), None)
        if dup is None:
            replacements.append(r)
        else:
            warnings.append(
                f"Chủ đề {topic.topic_id} ({topic.title}): bỏ mục làm lại \"{r.content}\" vì trùng mục đã "
                f"được kiểm chứng \"{dup.content}\"."
            )
    checks = _verify_all(llm, model, replacements, utterances, warnings)
    debug["retry_verify"] = _debug_checks(checks)
    errors = _verify_errors(topic, checks)
    warnings += errors
    unmatched = [c for c in failed_first if not any(_same_issue(r, c[0]) for r in replacements)]
    final = _finalize([(i, ok, r) for i, ok, r in first if ok is not False], False)
    flagged = _finalize(unmatched, True)
    demoted = [_demote_unconfirmed(i) for i in flagged]
    final += _finalize(checks, True) + demoted
    warnings += [
        f"Chủ đề {topic.topic_id} ({topic.title}): hạ \"{b.content}\" từ confirmed về proposed vì kiểm chứng "
        "không đạt và lần làm lại không còn giữ kết luận này."
        for b, a in zip(flagged, demoted) if a.status != b.status
    ]
    if unmatched and replacements:
        warnings.append(
            f"Chủ đề {topic.topic_id} ({topic.title}): {len(unmatched)} mục chưa được sửa ở lần làm lại, "
            "giữ kèm cờ verify_failed."
        )
    if not retry.items:
        warnings.append(
            f"Chủ đề {topic.topic_id} ({topic.title}): lần làm lại không trả mục nào, giữ kết quả lần đầu."
        )
        return final, warnings, True
    return final, warnings, bool(errors)


def process_topic(
    llm: LLMClient,
    model_light: str,
    model_strong: str,
    topic: Topic,
    utterances: list[Utterance],
    meta: MeetingMeta | None = None,
    digest: str = "",
) -> TopicResult:
    """Agent 2 → Agent 3 → Agent 4, with exactly one redo of Agent 2+3 on verify failure.

    Agent failures never drop the topic silently: they set `failed` and add warnings.
    """
    debug: dict[str, Any] = {}
    try:
        candidates = extract(llm, model_light, topic, utterances, meta)
    except LLMError as exc:
        warn = f"Chủ đề {topic.topic_id} ({topic.title}): Agent 2 lỗi, chủ đề không có kết quả. {exc}"
        return TopicResult(items=[], debug={"error": str(exc)}, warnings=[warn], failed=True)
    debug["extract"] = [c.model_dump(mode="json") for c in candidates]
    items, warnings, tracker_failed, dropped = _track_or_fallback(
        llm, model_strong, topic, candidates, utterances, meta, digest=digest
    )
    debug["track"] = [i.model_dump(mode="json") for i in items]
    if tracker_failed:
        return TopicResult(items=items, debug=debug, warnings=warnings, failed=True)

    warnings = list(warnings)
    # Agent 4 runs on the light model to cut cost (one call per decision/action).
    checks = _verify_all(llm, model_light, items, utterances, warnings)
    debug["verify"] = _debug_checks(checks)
    errors = _verify_errors(topic, checks)
    failures = [c for c in checks if c[1] is False]
    if not failures:
        return TopicResult(items=_finalize(checks, False), debug=debug, warnings=warnings + errors,
                           failed=bool(errors) or dropped)

    feedback = _feedback(failures)
    debug["retry_feedback"] = feedback
    try:
        candidates = extract(llm, model_light, topic, utterances, meta, feedback=feedback)
        debug["retry_extract"] = [c.model_dump(mode="json") for c in candidates]
        retry = track_detailed(llm, model_strong, topic, candidates, utterances, meta, feedback=feedback,
                                digest=digest)
    except LLMError as exc:
        # Redo failed: keep the first-pass items, flagging the ones that did not pass.
        warn = f"Chủ đề {topic.topic_id} ({topic.title}): lỗi khi làm lại sau kiểm chứng, giữ kết quả lần đầu. {exc}"
        return TopicResult(items=_finalize(checks, True), debug=debug, warnings=warnings + errors + [warn],
                           failed=True)
    debug["retry_track"] = [i.model_dump(mode="json") for i in retry.items]
    final, retry_warnings, retry_failed = _merge_retry(llm, model_light, topic, utterances, checks, retry, debug)
    return TopicResult(items=final, debug=debug, warnings=warnings + retry.warnings + retry_warnings,
                       failed=retry_failed or dropped or retry.dropped_items > 0)


# ---------------------------------------------------------------- full run


def prompt_versions() -> dict[str, str]:
    return {p.stem: load_prompt(p.stem).version for p in sorted(PROMPTS_DIR.glob("*.md"))}


def new_run_id(source_name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(source_name).stem)[:40] or "transcript"
    return f"{datetime.now():%Y%m%d-%H%M%S-%f}_{stem}"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_step(
    llm: LLMClient, settings: Settings, topics: list[Topic], utterances: list[Utterance],
    meta: MeetingMeta | None, seg_debug: dict[str, Any], warnings: list[str], notify: ProgressFn,
    run_dir: Path | None,
) -> list[Topic]:
    """L3: one merge call over all topics. Failure keeps the unmerged topics (warning only)."""
    if "merge" in seg_debug:  # long transcripts were already merged inside segment()
        return topics
    notify("Agent 1 – Gộp chủ đề trùng", 0.07)
    try:
        merged, debug = merge_topics(llm, settings.model_light, topics, utterances, meta)
    except LLMError as exc:
        warnings.append(f"Gộp chủ đề lỗi, giữ các chủ đề chưa gộp. {exc}")
        return topics
    if run_dir is not None:
        _write_json(run_dir / "segment.json", {"topics": [t.model_dump() for t in merged],
                                               "debug": {**seg_debug, "merge": debug}})
    return merged


def _digest_step(
    llm: LLMClient, settings: Settings, utterances: list[Utterance], warnings: list[str],
    notify: ProgressFn, run_dir: Path | None,
) -> str:
    """One digest call per meeting. Failure -> run on without an outline (warning only)."""
    notify("Dàn ý dòng thời gian", 0.09)
    try:
        text, debug = build_digest(llm, settings.model_light, utterances)
    except LLMError as exc:
        warnings.append(f"Lập dàn ý lỗi, chạy tiếp không có dàn ý. {exc}")
        return ""
    if run_dir is not None:
        _write_json(run_dir / "digest.json", {"text": text, **debug})
    return text


def _reconcile_step(
    llm: LLMClient, settings: Settings, items: list[Item], utterances: list[Utterance],
    meta: MeetingMeta | None, warnings: list[str], notify: ProgressFn, run_dir: Path | None,
) -> list[Item]:
    """Reconcile (AI links/conflicts), then code conflict flags, then re-run rules so flags reach scoring/sorting.

    apply_rules is idempotent and keeps item ids stable, so related_items stay valid.
    """
    notify("Đối soát toàn cuộc họp", 0.95)
    try:
        rec_warnings, debug = reconcile(llm, settings.model_strong, items, utterances)
        warnings.extend(rec_warnings)
        if run_dir is not None:
            _write_json(run_dir / "reconcile.json", debug)
    except LLMError as exc:
        warnings.append(f"Đối soát lỗi, bỏ qua bước này. {exc}")
    flag_conflicts(items)
    items, again = apply_rules(items, utterances, meta)
    warnings.extend(w for w in again if w not in warnings)
    return items


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
    run_id: str | None = None,
    audio_path: str | None = None,
) -> RunResult:
    settings = settings or load_settings()
    llm = llm or make_llm(settings)
    notify = progress or (lambda _msg, _frac: None)
    warnings = list(parse_warnings or [])
    if not utterances:
        raise ValueError("Transcript không có câu hợp lệ nào (kiểm tra định dạng [mm:ss] Tên: nội dung).")

    run_id = run_id or new_run_id(source_name)
    run_dir = settings.runs_dir / run_id

    notify("Agent 1 – Chia chủ đề", 0.05)
    topics, seg_debug = segment(llm, settings.model_light, utterances, meta)
    if save:
        _write_json(run_dir / "segment.json", {"topics": [t.model_dump() for t in topics], "debug": seg_debug})

    topics = _merge_step(llm, settings, topics, utterances, meta, seg_debug, warnings, notify, run_dir if save else None)
    digest = _digest_step(llm, settings, utterances, warnings, notify, run_dir if save else None)

    items: list[Item] = []
    failed_topics: list[str] = []
    for i, topic in enumerate(topics, start=1):
        notify(f"Agent 2–4 – Chủ đề {i}/{len(topics)}: {topic.title}", 0.1 + 0.8 * (i - 1) / max(len(topics), 1))
        try:
            result = process_topic(llm, settings.model_light, settings.model_strong, topic, utterances, meta, digest)
        except LLMError as exc:  # safety net: process_topic handles agent errors itself
            warnings.append(f"Chủ đề {topic.topic_id} ({topic.title}) lỗi khi gọi LLM: {exc}")
            failed_topics.append(topic.topic_id)
            continue
        items.extend(result.items)
        warnings.extend(result.warnings)
        if result.failed:
            failed_topics.append(topic.topic_id)
        if save:
            _write_json(run_dir / f"extract_{topic.topic_id}.json", result.debug)

    notify("Quy tắc hậu kiểm", 0.92)
    items, rule_warnings = apply_rules(items, utterances, meta)
    warnings.extend(rule_warnings)
    items = _reconcile_step(llm, settings, items, utterances, meta, warnings, notify, run_dir if save else None)

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
        failed_topics=failed_topics,
        meta=meta,
        audio_path=audio_path,
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
    """parse → Agent 1 → (Agent 2 → 3 → 4 per topic) → rules → runs/<run_id>/result.json

    Audio files (see AUDIO_EXTENSIONS) are routed to `run_audio`.
    """
    if Path(path).suffix.lower() in AUDIO_EXTENSIONS:
        return run_audio(path, meta, llm=llm, settings=settings, progress=progress, save=save)
    utterances, warnings = parse_file(path)
    return run_utterances(utterances, str(path), meta, llm=llm, settings=settings,
                          parse_warnings=warnings, progress=progress, save=save)


def run_audio(
    path: str | Path,
    meta: MeetingMeta | None = None,
    *,
    llm: LLMClient | None = None,
    settings: Settings | None = None,
    progress: ProgressFn | None = None,
    save: bool = True,
    transcribe_client: Any = None,
) -> RunResult:
    """Speech-to-text (with speaker diarization) → the normal pipeline.

    The audio is copied to runs/<run_id>/audio.<ext> and `RunResult.audio_path` holds that file's
    name relative to the run directory (e.g. "audio.mp3").
    """
    settings = settings or load_settings()
    notify = progress or (lambda _msg, _frac: None)
    notify("Chuyển giọng nói thành văn bản", 0.01)
    utterances, warnings = transcribe_with_warnings(path, settings, client=transcribe_client)
    run_id = new_run_id(str(path))
    audio_name: str | None = None
    if save:
        audio_name = save_audio(path, settings.runs_dir / run_id).name
    return run_utterances(
        utterances, str(path), meta, llm=llm, settings=settings, parse_warnings=warnings,
        progress=progress, save=save, run_id=run_id, audio_path=audio_name,
    )


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
