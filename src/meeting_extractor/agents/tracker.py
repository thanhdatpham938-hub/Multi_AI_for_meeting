"""Agent 3 – decision tracking: history, final status and discrete confidence labels."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from ..llm import LLMClient, LLMError, load_prompt
from ..models import (
    CLOSING_SIGNALS,
    COMMITMENTS,
    EVIDENCE_DIRECTNESS,
    FIELD_EVIDENCE_KEYS,
    KNOWLEDGE_SCOPES,
    Candidate,
    HistoryEntry,
    Item,
    MeetingMeta,
    Topic,
    TrackedItem,
    Utterance,
)
from .common import format_participants, format_utterances, select

TRACKER_FLAGS = {"no_closing_signal", "unresolved_reference"}
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

# Placeholder only: rules.py recomputes confidence from the labels (confidence.py).
DEFAULT_CONFIDENCE = 0.5


def format_candidates(candidates: list[Candidate]) -> str:
    if not candidates:
        return "(không có ứng viên)"
    return json.dumps([c.model_dump(mode="json") for c in candidates], ensure_ascii=False, indent=1)


def format_digest_block(digest: str) -> str:
    """Prompt block for the outline; empty when there is none."""
    if not digest.strip():
        return ""
    return (
        "Dàn ý toàn cuộc họp (chỉ để hiểu ngữ cảnh, không phải bằng chứng). Dàn ý chỉ để định hướng: "
        "trạng thái \"confirmed\" chỉ được gán dựa trên chính các câu trong transcript ở trên, "
        "KHÔNG BAO GIỜ dựa vào nhãn trong dàn ý.\n"
        f"<digest>\n{digest.strip()}\n</digest>\n"
    )


def track_detailed(
    llm: LLMClient,
    model: str,
    topic: Topic,
    candidates: list[Candidate],
    utterances: list[Utterance],
    meta: MeetingMeta | None = None,
    feedback: str | None = None,
    digest: str = "",
) -> TrackResult:
    """Return Items (item_id left empty – rules assign it) plus warnings for dropped parts.

    `digest` is the optional whole-meeting outline (context only, never evidence).
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
        DIGEST=format_digest_block(digest),
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
    digest: str = "",
) -> list[Item]:
    """Convenience wrapper around `track_detailed` that drops the warnings."""
    return track_detailed(llm, model, topic, candidates, utterances, meta, feedback, digest).items


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
        for key in BOOL_LABELS:
            data[key], ok = _coerce_bool(data.get(key))
            if not ok:
                warnings.append(f"{tag}: nhãn {key} không hợp lệ ({raw.get(key)!r}) → bỏ nhãn này.")
        warnings.extend(f"{tag}: {w}" for w in clean_new_labels(data))
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


BOOL_LABELS = ("contradicted_later", "in_summary")


def _coerce_bool(value: Any) -> tuple[bool | None, bool]:
    """Return (bool or None, ok). Accepts true/false, "true"/"false", 1/0; anything else -> (None, False)."""
    if value is None or isinstance(value, bool):
        return value, True
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value), True
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true", True
    return None, False


def _clean_enum_label(data: dict[str, Any], key: str, allowed: tuple[str, ...]) -> list[str]:
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, str) and value.strip() in allowed:
        data[key] = value.strip()
        return []
    data[key] = None
    return [f"nhãn {key} không hợp lệ ({value!r}) → bỏ nhãn này."]


def _clean_text_field(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        data[key] = value.strip() or None
        return []
    data[key] = None
    return [f"trường {key} không phải chuỗi ({value!r}) → bỏ."]


def _clean_quotes(data: dict[str, Any]) -> list[str]:
    raw = data.get("evidence_quotes")
    if raw is None:
        data["evidence_quotes"] = {}
        return []
    if not isinstance(raw, dict):
        data["evidence_quotes"] = {}
        return ["evidence_quotes không phải đối tượng → bỏ."]
    evidence = data.get("evidence")
    allowed = {e for e in evidence if isinstance(e, str)} if isinstance(evidence, list) else set()
    kept: dict[str, str] = {}
    bad = 0
    for uid, quote in raw.items():
        if uid in allowed and isinstance(quote, str) and quote.strip():
            kept[uid] = quote
        else:
            bad += 1
    data["evidence_quotes"] = kept
    return [f"bỏ {bad} đoạn trích không hợp lệ trong evidence_quotes."] if bad else []


def _clean_field_evidence(data: dict[str, Any]) -> list[str]:
    raw = data.get("field_evidence")
    if raw is None:
        data["field_evidence"] = {}
        return []
    if not isinstance(raw, dict):
        data["field_evidence"] = {}
        return ["field_evidence không phải đối tượng → bỏ."]
    kept: dict[str, list[str]] = {}
    bad = 0
    for key, value in raw.items():
        if key not in FIELD_EVIDENCE_KEYS:
            bad += 1
            continue
        ids = [value] if isinstance(value, str) else value
        if isinstance(ids, list) and ids and all(isinstance(i, str) for i in ids):
            kept[key] = ids
        else:
            bad += 1
    data["field_evidence"] = kept
    return [f"bỏ {bad} khóa không hợp lệ trong field_evidence."] if bad else []


def clean_new_labels(data: dict[str, Any]) -> list[str]:
    """Sanitise the Mission 3 labels in place so they can never make an item fail validation."""
    warnings: list[str] = []
    warnings += _clean_enum_label(data, "commitment", COMMITMENTS)
    warnings += _clean_enum_label(data, "knowledge_scope", KNOWLEDGE_SCOPES)
    warnings += _clean_quotes(data)
    warnings += _clean_field_evidence(data)
    warnings += _clean_text_field(data, "pending_on")
    warnings += _clean_text_field(data, "follow_up_owner")
    return warnings


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


def _valid_label(value: str | None, allowed: tuple[str, ...]) -> str | None:
    """Unknown label values are treated as missing (None)."""
    return value if value in allowed else None


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
                confidence=DEFAULT_CONFIDENCE,  # any number from the AI is ignored
                closing_signal=_valid_label(t.closing_signal, CLOSING_SIGNALS),
                evidence_directness=_valid_label(t.evidence_directness, EVIDENCE_DIRECTNESS),
                contradicted_later=t.contradicted_later,
                in_summary=t.in_summary,
                commitment=_valid_label(t.commitment, COMMITMENTS),
                evidence_quotes=t.evidence_quotes,
                field_evidence=t.field_evidence,
                knowledge_scope=_valid_label(t.knowledge_scope, KNOWLEDGE_SCOPES),
                pending_on=t.pending_on,
                follow_up_owner=t.follow_up_owner,
                flags=[f for f in t.flags if f in TRACKER_FLAGS],
            )
        )
    return items
