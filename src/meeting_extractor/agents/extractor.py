"""Agent 2 – candidate extraction, one topic at a time."""

from __future__ import annotations

from ..llm import LLMClient, load_prompt
from ..models import Candidate, ExtractOutput, MeetingMeta, Topic, Utterance
from .common import format_participants, format_utterances, select


def extract(
    llm: LLMClient,
    model: str,
    topic: Topic,
    utterances: list[Utterance],
    meta: MeetingMeta | None = None,
    feedback: str | None = None,
) -> list[Candidate]:
    prompt = load_prompt("extract")
    topic_utts = select(utterances, topic.utterance_ids)
    fb = ""
    if feedback:
        fb = (
            "\nLưu ý từ bước kiểm chứng (lần trước trích xuất chưa đúng, hãy sửa):\n"
            f"{feedback}\n"
        )
    user = prompt.render(
        TOPIC_ID=topic.topic_id,
        TOPIC_TITLE=topic.title,
        PARTICIPANTS=format_participants(meta),
        UTTERANCES=format_utterances(topic_utts),
        FEEDBACK=fb,
    )
    out = llm.complete_json(model=model, system=prompt.system, user=user, schema=ExtractOutput, purpose="extract")

    known = {u.id for u in utterances}
    candidates: list[Candidate] = []
    for c in out.candidates:
        evidence = [e for e in c.evidence if e in known]
        if not evidence:
            continue
        candidates.append(c.model_copy(update={"topic_id": topic.topic_id, "evidence": evidence}))
    return candidates
