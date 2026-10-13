"""Deterministic post-checks applied after Agent 4 (CLAUDE.md §7, rules 1–8)."""

from __future__ import annotations

import re

from .models import VALID_FLAGS, Item, ItemType, MeetingMeta, Status, Utterance
from .parsing import base_speaker_name, is_anonymous_speaker

LOW_CONFIDENCE = 0.7
AUTHORITY_CAP = 0.6

ID_PREFIX = {
    ItemType.decision: "d",
    ItemType.action: "a",
    ItemType.blocker: "b",
    ItemType.request: "r",
    ItemType.open_issue: "o",
    ItemType.knowledge: "k",
}
TYPE_ORDER = list(ID_PREFIX)

NUMBER_RE = re.compile(
    r"""
    \d[\d.,]*\s*(?:triệu|tr\b|tỷ|tỉ|nghìn|ngàn|k\b|đồng|đ\b|vnd|usd|\$|€)   # money
    | [$€]\s*\d
    | \d[\d.,]*\s*(?:%|phần\s*trăm)                                      # percent
    | \b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b                                   # 15/11, 15/11/2025
    | \bngày\s+\d{1,2}\b | \btháng\s+\d{1,2}\b | \bnăm\s+\d{4}\b          # ngày 15, tháng 11
    """,
    re.IGNORECASE | re.VERBOSE,
)


def has_number(text: str) -> bool:
    return bool(NUMBER_RE.search(text))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _add_flag(item: Item, flag: str) -> None:
    if flag not in item.flags:
        item.flags.append(flag)


def _all_evidence_ids(item: Item) -> list[str]:
    return [*item.evidence, *(eid for h in item.history for eid in h.evidence)]


def _owner_supported(owner: str, evidence: list[Utterance]) -> bool:
    name = _norm(base_speaker_name(owner))
    if not name:
        return False
    for u in evidence:
        if name in _norm(u.text) or name == _norm(base_speaker_name(u.speaker)) or _norm(owner) == _norm(u.speaker):
            return True
    return False


def _deadline_supported(deadline: str, evidence: list[Utterance]) -> bool:
    d = _norm(deadline)
    return bool(d) and any(d in _norm(u.text) for u in evidence)


def _can_decide(speaker: str, meta: MeetingMeta) -> bool:
    name = _norm(base_speaker_name(speaker))
    for p in meta.participants:
        if _norm(p.name) == name or _norm(p.name) == _norm(speaker):
            return p.can_decide
    return False


def apply_rules(
    items: list[Item], utterances: list[Utterance], meta: MeetingMeta | None = None
) -> tuple[list[Item], list[str]]:
    """Return (checked & sorted items with ids, warnings)."""
    by_id = {u.id: u for u in utterances}
    position = {u.id: i for i, u in enumerate(utterances)}
    warnings: list[str] = []
    kept: list[Item] = []

    for original in items:
        item = original.model_copy(deep=True)
        item.flags = [f for f in dict.fromkeys(item.flags) if f in VALID_FLAGS]

        # Rule 1: every cited utterance id must exist.
        missing = [eid for eid in _all_evidence_ids(item) if eid not in by_id]
        if missing or not item.evidence:
            warnings.append(f"Loại item \"{item.content}\": ID bằng chứng không tồn tại {missing or '(trống)'}")
            continue
        evidence = sorted((by_id[e] for e in dict.fromkeys(item.evidence)), key=lambda u: position[u.id])

        # Rule 2: owner/deadline must appear in the evidence.
        if item.owner and not _owner_supported(item.owner, evidence):
            warnings.append(f"Bỏ owner \"{item.owner}\" của \"{item.content}\": không có trong câu bằng chứng")
            item.owner = None
        if item.deadline and not _deadline_supported(item.deadline, evidence):
            warnings.append(f"Bỏ deadline \"{item.deadline}\" của \"{item.content}\": không có trong câu bằng chứng")
            item.deadline = None

        # Rule 3: actions need an owner.
        if item.type == ItemType.action and not item.owner:
            _add_flag(item, "missing_owner")

        # Rule 4: money / percent / dates must be double-checked by a human.
        if has_number(item.content) or (item.condition and has_number(item.condition)):
            _add_flag(item, "number_check")

        # Rule 5: who closed the decision?
        if item.type == ItemType.decision:
            closer = evidence[-1].speaker
            anonymous = is_anonymous_speaker(closer)
            no_right = bool(meta and meta.participants) and not _can_decide(closer, meta)
            if anonymous or no_right:
                _add_flag(item, "authority_unclear")
                item.confidence = min(item.confidence, AUTHORITY_CAP)

        # Rule 6: conditional without a condition is just open.
        if item.status == Status.conditional and not (item.condition or "").strip():
            warnings.append(f"\"{item.content}\": conditional nhưng thiếu điều kiện → chuyển về open")
            item.status = Status.open
            item.condition = None

        # Rule 7: low confidence.
        if item.confidence < LOW_CONFIDENCE:
            _add_flag(item, "low_confidence")

        kept.append(item)

    # Rule 8: ids by type in transcript order, then flagged / low-confidence first.
    def first_pos(it: Item) -> int:
        return min(position[e] for e in it.evidence)

    kept.sort(key=lambda it: (TYPE_ORDER.index(it.type), first_pos(it)))
    counters: dict[ItemType, int] = {}
    for it in kept:
        counters[it.type] = counters.get(it.type, 0) + 1
        it.item_id = f"{ID_PREFIX[it.type]}{counters[it.type]:02d}"
    kept.sort(key=lambda it: (0 if needs_attention(it) else 1, TYPE_ORDER.index(it.type), first_pos(it)))
    return kept, warnings


def needs_attention(item: Item) -> bool:
    return bool(item.flags) or item.confidence < LOW_CONFIDENCE
