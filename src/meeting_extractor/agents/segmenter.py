"""Agent 1 – topic segmentation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..llm import LLMClient, load_prompt
from ..models import MeetingMeta, SegmentOutput, Topic, Utterance
from .common import format_agenda, format_utterances, select

LONG_TRANSCRIPT = 300
WINDOW_SIZE = 150
WINDOW_OVERLAP = 20


class MergeGroup(BaseModel):
    title: str
    topic_ids: list[str]
    is_off_agenda: bool = False


class MergeOutput(BaseModel):
    groups: list[MergeGroup]


def make_windows(n: int, size: int = WINDOW_SIZE, overlap: int = WINDOW_OVERLAP) -> list[tuple[int, int]]:
    """[start, end) index ranges covering n items with the given overlap."""
    if n <= 0:
        return []
    step = size - overlap
    windows = []
    start = 0
    while True:
        end = min(start + size, n)
        windows.append((start, end))
        if end >= n:
            return windows
        start += step


def normalize_topics(topics: list[Topic], utterances: list[Utterance]) -> list[Topic]:
    """Drop unknown/duplicate ids, empty topics; order by first utterance; renumber t01…"""
    order = {u.id: i for i, u in enumerate(utterances)}
    seen: set[str] = set()
    cleaned: list[Topic] = []
    for t in topics:
        ids = sorted({i for i in t.utterance_ids if i in order and i not in seen}, key=order.__getitem__)
        if not ids:
            continue
        seen.update(ids)
        cleaned.append(Topic(topic_id="", title=t.title.strip() or "Chủ đề", utterance_ids=ids,
                             is_off_agenda=t.is_off_agenda))
    cleaned.sort(key=lambda t: order[t.utterance_ids[0]])
    return [t.model_copy(update={"topic_id": f"t{i:02d}"}) for i, t in enumerate(cleaned, start=1)]


def _segment_once(llm: LLMClient, model: str, utterances: list[Utterance], meta: MeetingMeta | None) -> SegmentOutput:
    prompt = load_prompt("segment")
    user = prompt.render(AGENDA=format_agenda(meta), UTTERANCES=format_utterances(utterances))
    return llm.complete_json(model=model, system=prompt.system, user=user, schema=SegmentOutput, purpose="segment")


def _merge_windows(
    llm: LLMClient, model: str, window_topics: list[Topic], utterances: list[Utterance], meta: MeetingMeta | None
) -> tuple[list[Topic], dict[str, Any]]:
    prompt = load_prompt("segment_merge")
    lines = []
    for t in window_topics:
        sample = " | ".join(u.text for u in select(utterances, t.utterance_ids[:3]))
        lines.append(f"{t.topic_id}: {t.title} — {sample[:300]}")
    user = prompt.render(AGENDA=format_agenda(meta), TOPICS="\n".join(lines))
    merged = llm.complete_json(model=model, system=prompt.system, user=user, schema=MergeOutput, purpose="merge")

    by_id = {t.topic_id: t for t in window_topics}
    used: set[str] = set()
    topics: list[Topic] = []
    for g in merged.groups:
        members = [by_id[i] for i in g.topic_ids if i in by_id and i not in used]
        used.update(m.topic_id for m in members)
        if members:
            ids = [uid for m in members for uid in m.utterance_ids]
            topics.append(Topic(topic_id="", title=g.title, utterance_ids=ids, is_off_agenda=g.is_off_agenda))
    # Any topic the merge step forgot is kept as-is rather than silently lost.
    topics.extend(t for t in window_topics if t.topic_id not in used)
    return topics, merged.model_dump()


def merge_topics(
    llm: LLMClient, model: str, topics: list[Topic], utterances: list[Utterance], meta: MeetingMeta | None = None
) -> tuple[list[Topic], dict[str, Any]]:
    """One LLM call that groups duplicate topics of the whole meeting (L3).

    Fewer than 2 topics -> no call. Raises LLMError when the call fails: the caller keeps the
    unmerged topics and records a warning.
    """
    if len(topics) < 2:
        return topics, {"skipped": True}
    merged, raw = _merge_windows(llm, model, topics, utterances, meta)
    result = normalize_topics(merged, utterances)
    if not result:
        return topics, {"skipped": True, "reason": "merge returned nothing", "raw": raw}
    return result, {"raw": raw, "before": len(topics), "after": len(result)}


def segment(
    llm: LLMClient, model: str, utterances: list[Utterance], meta: MeetingMeta | None = None
) -> tuple[list[Topic], dict[str, Any]]:
    """Return (topics, debug_payload)."""
    debug: dict[str, Any] = {}
    if len(utterances) <= LONG_TRANSCRIPT:
        out = _segment_once(llm, model, utterances, meta)
        debug["raw"] = out.model_dump()
        topics = out.topics
    else:
        window_topics: list[Topic] = []
        debug["windows"] = []
        for w, (start, end) in enumerate(make_windows(len(utterances)), start=1):
            out = _segment_once(llm, model, utterances[start:end], meta)
            debug["windows"].append({"range": [start, end], "raw": out.model_dump()})
            window_topics.extend(t.model_copy(update={"topic_id": f"w{w}_{t.topic_id}"}) for t in out.topics)
        topics, debug["merge"] = _merge_windows(llm, model, window_topics, utterances, meta)

    result = normalize_topics(topics, utterances)
    if not result and utterances:
        # Fallback: never lose the whole meeting because segmentation returned nothing.
        result = [Topic(topic_id="t01", title="Toàn bộ cuộc họp", utterance_ids=[u.id for u in utterances])]
    return result, debug
