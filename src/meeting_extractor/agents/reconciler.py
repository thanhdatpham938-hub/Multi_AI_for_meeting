"""Reconciliation: one strong-model call after all topics, linking items and spotting conflicts.

The model sees item summaries plus their verbatim evidence sentences (never the full transcript).
Code applies the answer: only real item ids are accepted, nothing is deleted, no status is changed.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..conflicts import CONFLICT_FLAG
from ..llm import LLMClient, load_prompt
from ..models import Item, Utterance
from .common import select

MAX_QUOTE_CHARS = 200


class LinkPair(BaseModel):
    a: str
    b: str
    relation: str = ""


class ConflictPair(BaseModel):
    a: str
    b: str
    reason: str = ""


class ReconcileOutput(BaseModel):
    related: list[LinkPair] = []
    conflicts: list[ConflictPair] = []


def format_items(items: list[Item], utterances: list[Utterance]) -> str:
    """One block per item: id, type, status, topic, content and its evidence sentences verbatim."""
    blocks: list[str] = []
    for it in items:
        status = it.status.value if it.status else "-"
        lines = [f"{it.item_id} | {it.type.value} | {status} | chủ đề: {it.topic} | {it.content}"]
        for u in select(utterances, it.evidence):
            lines.append(f"    {u.id} [{u.time}] {u.speaker}: {u.text[:MAX_QUOTE_CHARS]}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def apply_reconcile(items: list[Item], out: ReconcileOutput) -> list[str]:
    """Write related_items (both directions) and conflict flags in place. Returns warnings.

    Unknown ids and self-pairs are ignored. A suspected conflict is flagged only when both items are decisions.
    """
    by_id = {i.item_id: i for i in items}
    warnings: list[str] = []
    for p in out.related:
        a, b = by_id.get(p.a), by_id.get(p.b)
        if a is None or b is None or a is b:
            continue
        if b.item_id not in a.related_items:
            a.related_items.append(b.item_id)
        if a.item_id not in b.related_items:
            b.related_items.append(a.item_id)
    for c in out.conflicts:
        a, b = by_id.get(c.a), by_id.get(c.b)
        if a is None or b is None or a is b:
            continue
        if a.type.value != "decision" or b.type.value != "decision":
            continue
        for it in (a, b):
            if CONFLICT_FLAG not in it.flags:
                it.flags.append(CONFLICT_FLAG)
        warnings.append(f"Nghi mâu thuẫn giữa {a.item_id} và {b.item_id}: {c.reason or 'AI đối soát nghi mâu thuẫn'}")
    return warnings


def reconcile(
    llm: LLMClient, model: str, items: list[Item], utterances: list[Utterance]
) -> tuple[list[str], dict[str, Any]]:
    """Run the call and apply it to `items` in place. Returns (warnings, debug).

    Fewer than 2 items -> no call. Raises LLMError when the call fails (caller skips with a warning).
    """
    if len(items) < 2:
        return [], {"skipped": True}
    prompt = load_prompt("reconcile")
    user = prompt.render(ITEMS=format_items(items, utterances))
    out = llm.complete_json(model=model, system=prompt.system, user=user, schema=ReconcileOutput, purpose="reconcile")
    warnings = apply_reconcile(items, out)
    return warnings, out.model_dump()
