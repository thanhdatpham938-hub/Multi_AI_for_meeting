"""Orchestrator: plain Python calling each agent in sequence (no LLM orchestration)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agents.extractor import extract
from .agents.tracker import track
from .agents.verifier import needs_verification, verify
from .llm import LLMClient
from .models import Item, MeetingMeta, Topic, Utterance

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
