"""Agent 3 – decision tracking: history, final status, confidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from ..llm import LLMClient, LLMError, load_prompt
from ..models import Candidate, HistoryEntry, Item, MeetingMeta, Topic, TrackedItem, Utterance
from .common import format_participants, format_utterances, select

TRACKER_FLAGS = {"no_closing_signal"}
FALLBACK_CONFIDENCE = 0.3


class RawTrackOutput(BaseModel):
    """Loose schema: items are validated one by one afterwards."""

    items: list[Any]


class TrackerFailed(LLMError):
    """Agent 3 returned items but none survived validation."""


@dataclass
class TrackResult:
    items: list[Item]
    warnings: list[str] = field(default_factory=list)
    dropped_items: int = 0  # whole items dropped by validation (history-entry drops do not count)
# Placeholder until rules.py computes confidence from labels (phase 3A).
DEFAULT_CONFIDENCE = 0.5


def format_candidates(candidates: list[Candidate]) -> str:
    if not candidates:
        return "(không có ứng viên)"
    return json.dumps([c.model_dump(mode="json") for c in candidates], ensure_ascii=False, indent=1)


def track_detailed(
    llm: LLMClient,
    model: str,
    topic: Topic,
    candidates: list[Candidate],
    utterances: list[Utterance],
    meta: MeetingMeta | None = None,
    feedback: str | None = None,
) -> TrackResult:
    """Return Items (item_id left empty – rules assign it) plus warnings for dropped parts.

    Raises LLMError (or TrackerFailed) when Agent 3 produced nothing usable.
    """
    prompt = load_prompt("track")
    fb = ""
    if feedback:
        fb = f"\nLưu ý từ bước kiểm chứng (kết quả lần trước bị đánh giá sai, hãy sửa):\n{feedback}\n"
    user = prompt.render(
        TOPIC_ID=topic.topic_id,
        TOPIC_TITLE=topic.title,
        PARTICIPANTS=format_participants(meta),
        UTTERANCES=format_utterances(select(utterances, topic.utterance_ids)),
        CANDIDATES=format_candidates(candidates),
        FEEDBACK=fb,
    )
    raw = llm.complete_json(model=model, system=prompt.system, user=user, schema=RawTrackOutput, purpose="track")
    if candidates and not raw.items:
        raise TrackerFailed(f"[track] Chủ đề {topic.topic_id}: Agent 3 không trả mục nào dù có {len(candidates)} ứng viên.")
    tracked, warnings, dropped = validate_raw_items(raw.items, topic)
    if raw.items and not tracked:
        raise TrackerFailed(f"[track] Chủ đề {topic.topic_id}: không còn mục hợp lệ nào. " + " | ".join(warnings[:3]))
    return TrackResult(items=build_items(tracked, topic), warnings=warnings, dropped_items=dropped)


def track(
    llm: LLMClient,
    model: str,
    topic: Topic,
    candidates: list[Candidate],
    utterances: list[Utterance],
    meta: MeetingMeta | None = None,
    feedback: str | None = None,
) -> list[Item]:
    """Convenience wrapper around `track_detailed` that drops the warnings."""
    return track_detailed(llm, model, topic, candidates, utterances, meta, feedback).items


def validate_raw_items(raw_items: list[Any], topic: Topic) -> tuple[list[TrackedItem], list[str], int]:
    """Validate each raw item on its own; drop bad history entries / bad items, never the whole answer."""
    tracked: list[TrackedItem] = []
    warnings: list[str] = []
    dropped = 0
    for n, raw in enumerate(raw_items, start=1):
        tag = f"Chủ đề {topic.topic_id}, mục {n}"
        if not isinstance(raw, dict):
            warnings.append(f"{tag}: bỏ vì không phải đối tượng JSON.")
            dropped += 1
            continue
        data = dict(raw)
        data["history"], bad_history = _clean_history(data.get("history"))
        if bad_history:
            warnings.append(f"{tag}: bỏ {bad_history} mục lịch sử không hợp lệ (thiếu/sai trạng thái).")
        try:
            tracked.append(TrackedItem.model_validate(data))
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            warnings.append(f"{tag}: bỏ vì không hợp lệ ({where}: {first['msg']}).")
            dropped += 1
    return tracked, warnings, dropped


def _clean_history(raw_history: Any) -> tuple[list[dict[str, Any]], int]:
    if raw_history is None:
        return [], 0
    if not isinstance(raw_history, list):
        return [], 1
    kept: list[dict[str, Any]] = []
    for entry in raw_history:
        try:
            HistoryEntry.model_validate(entry)
        except ValidationError:
            continue
        kept.append(entry)
    return kept, len(raw_history) - len(kept)


def candidates_to_items(candidates: list[Candidate], topic: Topic) -> list[Item]:
    """Fallback when Agent 3 fails: keep Agent 2's raw candidates as low-confidence items."""
    return [
        Item(
            item_id="",
            type=c.type,
            topic_id=topic.topic_id,
            topic=topic.title,
            content=c.content.strip(),
            status=None,
            owner=c.owner,
            deadline=c.deadline,
            evidence=c.evidence,
            confidence=FALLBACK_CONFIDENCE,
            flags=["tracker_failed"],
        )
        for c in candidates
    ]


def build_items(tracked: list[TrackedItem], topic: Topic) -> list[Item]:
    items: list[Item] = []
    for t in tracked:
        items.append(
            Item(
                item_id="",
                type=t.type,
                topic_id=topic.topic_id,
                topic=topic.title,
                content=t.content.strip(),
                status=t.status,
                condition=(t.condition or "").strip() or None,
                history=t.history,
                owner=t.owner,
                deadline=t.deadline,
                evidence=t.evidence,
                confidence=t.confidence if t.confidence is not None else DEFAULT_CONFIDENCE,
                flags=[f for f in t.flags if f in TRACKER_FLAGS],
            )
        )
    return items
