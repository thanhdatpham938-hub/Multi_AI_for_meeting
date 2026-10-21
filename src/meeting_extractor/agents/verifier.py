"""Agent 4 – verify that evidence really supports decision/action items."""

from __future__ import annotations

import json
from typing import Any

from pydantic import model_validator

from ..counter_evidence import find_counter_candidates
from ..llm import LLMClient, load_prompt
from ..models import Item, ItemType, Utterance, VerifyOutput
from .common import format_utterances, select

VERIFIED_TYPES = {ItemType.decision, ItemType.action}


def needs_verification(item: Item) -> bool:
    return item.type in VERIFIED_TYPES


class VerifyOutputV2(VerifyOutput):
    """Agent 4 output plus the later utterances that contradict the item (decisions only)."""

    contradicted_by: list[str] = []
    warnings: list[str] = []  # filled by code (not by the LLM), e.g. malformed or unknown ids that were dropped

    @model_validator(mode="before")
    @classmethod
    def _coerce_contradicted_by(cls, data: Any) -> Any:
        """Never reject the whole verdict because of a malformed `contradicted_by`."""
        if not isinstance(data, dict):
            return data
        raw = data.get("contradicted_by")
        warnings: list[str] = []
        if raw is None:
            ids: list[str] = []
        elif isinstance(raw, str):
            ids = [raw] if raw.strip() else []
        elif isinstance(raw, list):
            ids = [x for x in raw if isinstance(x, str)]
            if len(ids) != len(raw):
                warnings.append("Agent 4 trả contradicted_by có phần tử không phải chuỗi, đã bỏ các phần tử đó.")
        else:
            ids = []
            warnings.append("Agent 4 trả contradicted_by sai kiểu (không phải danh sách), bỏ qua.")
        return {**data, "contradicted_by": ids, "warnings": warnings}


def format_counter_block(candidates: list[Utterance]) -> str:
    if not candidates:
        return ""
    return (
        "\nCác câu nói SAU câu bằng chứng (có thể phản bác, thay đổi hoặc rút lại item này):\n"
        f"<later_utterances>\n{format_utterances(candidates)}\n</later_utterances>\n"
    )


def filter_contradicted(raw: list[str], candidates: list[Utterance]) -> tuple[list[str], list[str]]:
    """Keep only ids that were actually sent (deduplicated, in order). Returns (valid ids, warnings)."""
    allowed = {u.id for u in candidates}
    valid: list[str] = []
    warnings: list[str] = []
    for cid in raw:
        if cid in allowed:
            if cid not in valid:
                valid.append(cid)
        else:
            warnings.append(f"Agent 4 trả contradicted_by với ID \"{cid}\" không nằm trong các câu đã gửi, bỏ qua.")
    return valid, warnings


def verify(llm: LLMClient, model: str, item: Item, utterances: list[Utterance]) -> VerifyOutputV2:
    evidence = select(utterances, item.evidence)
    if not evidence:
        return VerifyOutputV2(passed=False, reason="Không có câu bằng chứng hợp lệ.")
    prompt = load_prompt("verify")
    item_view = item.model_dump(
        mode="json", include={"type", "content", "status", "condition", "owner", "deadline"}
    )
    candidates = find_counter_candidates(item, utterances)
    user = prompt.render(
        ITEM=json.dumps(item_view, ensure_ascii=False, indent=1),
        EVIDENCE=format_utterances(evidence),
        COUNTER=format_counter_block(candidates),
    )
    out = llm.complete_json(model=model, system=prompt.system, user=user, schema=VerifyOutputV2, purpose="verify")
    out.contradicted_by, dropped = filter_contradicted(out.contradicted_by, candidates)
    out.warnings = [*out.warnings, *dropped]
    return out


def apply_contradiction(item: Item, out: VerifyOutputV2) -> Item:
    """Copy of `item` with `contradicted_later`/`field_evidence['contradicted_by']` set when Agent 4 found any.

    No valid contradicting id -> the item (and the AI's earlier `contradicted_later` label) is left untouched.
    """
    if not out.contradicted_by:
        return item
    field_evidence = {**item.field_evidence, "contradicted_by": list(out.contradicted_by)}
    return item.model_copy(update={"contradicted_later": True, "field_evidence": field_evidence})
