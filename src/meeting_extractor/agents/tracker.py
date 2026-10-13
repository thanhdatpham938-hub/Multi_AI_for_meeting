"""Agent 3 – decision tracking: history, final status, confidence."""

from __future__ import annotations

import json

from ..llm import LLMClient, load_prompt
from ..models import Candidate, Item, MeetingMeta, Topic, TrackOutput, Utterance
from .common import format_participants, format_utterances, select

TRACKER_FLAGS = {"no_closing_signal"}


def format_candidates(candidates: list[Candidate]) -> str:
    if not candidates:
        return "(không có ứng viên)"
    return json.dumps([c.model_dump(mode="json") for c in candidates], ensure_ascii=False, indent=1)


def track(
    llm: LLMClient,
    model: str,
    topic: Topic,
    candidates: list[Candidate],
    utterances: list[Utterance],
    meta: MeetingMeta | None = None,
    feedback: str | None = None,
) -> list[Item]:
    """Return Items for one topic (item_id left empty – rules assign it)."""
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
    out = llm.complete_json(model=model, system=prompt.system, user=user, schema=TrackOutput, purpose="track")

    items: list[Item] = []
    for t in out.items:
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
                confidence=t.confidence,
                flags=[f for f in t.flags if f in TRACKER_FLAGS],
            )
        )
    return items
