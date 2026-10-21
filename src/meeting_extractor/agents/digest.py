"""Timeline digest: one cheap call per meeting that lists the key moments, used as context by Agent 3."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from ..llm import LLMClient, load_prompt
from ..models import Utterance
from .common import format_utterances

EVENT_KINDS = ("đề xuất", "phản bác", "chốt", "hoãn", "chuyển chủ đề", "quay lại chủ đề")
MAX_EVENTS = 80
MAX_SUMMARY_CHARS = 140
_ID_IN_TEXT = re.compile(r"\(?\bu\d{3,}\b\)?")
# Agent 3 sees a neutral label for "chốt": the light model's label must never act as a closing signal.
NEUTRAL_KINDS = {"chốt": "có thể là câu chốt (cần tự kiểm câu gốc)"}


class DigestEvent(BaseModel):
    time: str = ""
    speaker: str = ""
    kind: str
    summary: str
    utterance_ids: list[str] = []


class DigestOutput(BaseModel):
    events: list[DigestEvent]


def clean_events(events: list[DigestEvent], utterances: list[Utterance]) -> list[DigestEvent]:
    """Drop unknown utterance ids and unknown event kinds; fill time/speaker from the first cited utterance."""
    by_id = {u.id: u for u in utterances}
    cleaned: list[DigestEvent] = []
    for e in events[:MAX_EVENTS]:
        ids = [i for i in dict.fromkeys(e.utterance_ids) if i in by_id]
        kind = e.kind.strip().lower()
        summary = " ".join(_ID_IN_TEXT.sub("", e.summary).split())[:MAX_SUMMARY_CHARS]
        if kind not in EVENT_KINDS or not ids or not summary:
            continue
        first = by_id[ids[0]]
        cleaned.append(DigestEvent(time=e.time or first.time, speaker=e.speaker or first.speaker,
                                   kind=kind, summary=summary, utterance_ids=ids))
    return cleaned


def format_digest(events: list[DigestEvent]) -> str:
    """Short plain-text outline, one line per moment. Empty string when there is nothing.

    Utterance ids are left out on purpose: the outline is context, never a source of evidence ids.
    """
    return "\n".join(
        f"- [{e.time}] {e.speaker} – {NEUTRAL_KINDS.get(e.kind, e.kind)}: {e.summary}" for e in events
    )


def build_digest(
    llm: LLMClient, model: str, utterances: list[Utterance]
) -> tuple[str, dict[str, Any]]:
    """Return (digest text, debug payload). Raises LLMError when the call fails (caller continues without it)."""
    prompt = load_prompt("digest")
    user = prompt.render(UTTERANCES=format_utterances(utterances))
    out = llm.complete_json(model=model, system=prompt.system, user=user, schema=DigestOutput, purpose="digest")
    events = clean_events(out.events, utterances)
    text = format_digest(events)
    return text, {"events": [e.model_dump() for e in events], "dropped": len(out.events) - len(events)}
