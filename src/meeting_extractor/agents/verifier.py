"""Agent 4 – verify that evidence really supports decision/action items."""

from __future__ import annotations

import json

from ..llm import LLMClient, load_prompt
from ..models import Item, ItemType, Utterance, VerifyOutput
from .common import format_utterances, select

VERIFIED_TYPES = {ItemType.decision, ItemType.action}


def needs_verification(item: Item) -> bool:
    return item.type in VERIFIED_TYPES


def verify(llm: LLMClient, model: str, item: Item, utterances: list[Utterance]) -> VerifyOutput:
    evidence = select(utterances, item.evidence)
    if not evidence:
        return VerifyOutput(passed=False, reason="Không có câu bằng chứng hợp lệ.")
    prompt = load_prompt("verify")
    item_view = item.model_dump(
        mode="json", include={"type", "content", "status", "condition", "owner", "deadline"}
    )
    user = prompt.render(
        ITEM=json.dumps(item_view, ensure_ascii=False, indent=1),
        EVIDENCE=format_utterances(evidence),
    )
    return llm.complete_json(model=model, system=prompt.system, user=user, schema=VerifyOutput, purpose="verify")
