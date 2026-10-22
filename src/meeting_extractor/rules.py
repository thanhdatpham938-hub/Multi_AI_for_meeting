"""Deterministic post-checks applied after Agent 4 (CLAUDE.md §7, rules 1–8)."""

from __future__ import annotations

import re

from .confidence import apply_cap, closer_status, compute_confidence, load_weights
from .models import VALID_FLAGS, Item, ItemType, MeetingMeta, Status, Utterance
from .parsing import base_speaker_name
from .provenance import (
    check_quotes,
    deadline_from_sources,
    owner_from_sources,
    sanitize_field_evidence,
)
from .signal_rules import (
    SIGNAL_FLAGS,
    WARN_PREFIX,
    A1Plan,
    Adj,
    Ctx,
    action_row10,
    add_flag,
    apply_siblings,
    build_ctx,
    carry_sticky,
    decision_signals,
    merge_duplicates,
    number_signals,
    owner_signals,
    plan_a1,
    run_warnings,
    write_signal_check,
)

LOW_CONFIDENCE = 0.7

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


QUANTITY_RE = re.compile(
    r"\d[\d.,]*\s*(?:đơn|giờ|phút|giây|người|user|khách|lần|ticket|request|node|server|máy|gb|mb|tb)\b",
    re.IGNORECASE,
)


def has_number(text: str) -> bool:
    return bool(NUMBER_RE.search(text))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


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


def has_quantity(text: str) -> bool:
    """Money, percent, date or a counted quantity ("5.000 đơn", "24 giờ")."""
    return has_number(text) or bool(QUANTITY_RE.search(text))


def _apply_commitment(item: Item, warnings: list[str]) -> None:
    """Turn non-commitments into other types; never drop the item silently."""
    if item.type != ItemType.action:
        return
    label = item.commitment
    if label == "already_done":
        who = f" (người làm: {item.owner})" if item.owner else ""
        warnings.append(f"\"{item.content}\": việc đã làm xong, không phải việc cần làm → chuyển thành knowledge{who}")
        item.type = ItemType.knowledge  # owner is kept

    elif label == "hypothetical":
        warnings.append(f"\"{item.content}\": giả định, chưa phải việc cần làm → chuyển thành open_issue")
        item.type = ItemType.open_issue
    elif label == "volunteered_conditional":
        who = item.owner
        warnings.append(
            f"\"{item.content}\": xung phong có điều kiện, chưa được giao – chuyển thành vấn đề còn mở"
            + (f" (người xung phong: {who})" if who else "")
        )
        if who and who.lower() not in item.content.lower():
            item.content = f"Đề nghị hỗ trợ (chưa được giao) – {who}: {item.content}"
        elif who:
            item.content = f"Đề nghị hỗ trợ (chưa được giao): {item.content}"
        item.type, item.owner = ItemType.open_issue, None


def _drop_decision_deadline(item: Item, warnings: list[str]) -> None:
    if item.type == ItemType.decision and item.deadline:
        warnings.append(f"Hạn '{item.deadline}' gắn vào quyết định đã được bỏ: \"{item.content}\"")
        item.deadline = None


def _check_provenance(item: Item, by_id: dict[str, Utterance], warnings: list[str]) -> None:
    """Verify verbatim quotes and drop field-evidence ids that do not exist."""
    quotes, mismatched, orphans = check_quotes(item, by_id)
    if orphans:
        warnings.append(f"Bỏ đoạn trích của \"{item.content}\": ID {orphans} không nằm trong evidence")
    item.evidence_quotes = quotes
    if mismatched:
        warnings.append(f"\"{item.content}\": đoạn trích không khớp câu gốc ở {mismatched}")
        add_flag(item, "quote_mismatch")
    item.field_evidence, dropped = sanitize_field_evidence(item.field_evidence, by_id)
    if dropped:
        warnings.append(f"Bỏ ID nguồn không tồn tại {dropped} khỏi field_evidence của \"{item.content}\"")


def _check_owner_deadline(
    item: Item,
    evidence: list[Utterance],
    by_id: dict[str, Utterance],
    utterances: list[Utterance],
    meta: MeetingMeta | None,
    warnings: list[str],
) -> None:
    """Rule 2: field_evidence first, then the older check against the cited evidence."""
    if item.owner:
        src = [by_id[i] for i in item.field_evidence.get("owner", [])]
        if not (owner_from_sources(item.owner, src, utterances, meta) or _owner_supported(item.owner, evidence)):
            warnings.append(f"Bỏ owner \"{item.owner}\" của \"{item.content}\": không có trong câu bằng chứng")
            item.owner = None
    if item.deadline:
        src = [by_id[i] for i in item.field_evidence.get("deadline", [])]
        if not (deadline_from_sources(item.deadline, src) or _deadline_supported(item.deadline, evidence)):
            warnings.append(f"Bỏ deadline \"{item.deadline}\" của \"{item.content}\": không có trong câu bằng chứng")
            item.deadline = None



# ------------------------------------------------------------------ scoring and orchestration


MAX_PASSES = 5


def _score(item: Item, utterances: list[Utterance], meta: MeetingMeta | None, adj: Adj | None = None) -> None:
    """Formula first (plus signal penalties), then hard caps (recorded in the breakdown)."""
    adj = adj or Adj()
    w = load_weights()
    score, breakdown = compute_confidence(item, utterances, meta, adj.terms, closer_id=adj.closing)
    if "authority_unclear" in item.flags:
        score = apply_cap(score, breakdown, "cap_authority", w["cap_authority"])
    if "verify_failed" in item.flags:
        score = apply_cap(score, breakdown, "cap_verify_failed", w["cap_verify_failed"])
    if "tracker_failed" in item.flags:
        score = apply_cap(score, breakdown, "cap_tracker_failed", w["cap_tracker_failed"])
    for name in dict.fromkeys(adj.caps):
        score = apply_cap(score, breakdown, name, w[name])
    item.confidence = score
    item.confidence_breakdown = breakdown


def _prepare(original: Item, by_id: dict[str, Utterance], warnings: list[str]) -> Item | None:
    item = original.model_copy(deep=True)
    # Flags recomputed on every run must not survive a second run (quote_mismatch, low_confidence, signal flags).
    drop = ("low_confidence", "quote_mismatch", *SIGNAL_FLAGS)
    item.flags = [f for f in dict.fromkeys(item.flags) if f in VALID_FLAGS and f not in drop]
    # Rule 1: every cited utterance id must exist.
    missing = [eid for eid in _all_evidence_ids(item) if eid not in by_id]
    if missing or not item.evidence:
        warnings.append(f"Loại item \"{item.content}\": ID bằng chứng không tồn tại {missing or '(trống)'}")
        return None
    return item


def _process_item(item: Item, ctx: Ctx, plan: A1Plan, warnings: list[str]) -> Adj:
    """Rules 2-6 plus the signal layer for one item. Returns the score adjustments."""
    adj = Adj()
    by_id, position, meta = ctx.by_id, ctx.position, ctx.meta
    carry_sticky(item, adj)

    def cited() -> list[Utterance]:
        return sorted((by_id[e] for e in dict.fromkeys(item.evidence)), key=lambda u: position[u.id])

    # Mission 3 rules: commitment labels, decision deadlines, quote provenance.
    _apply_commitment(item, warnings)
    _drop_decision_deadline(item, warnings)
    _check_provenance(item, by_id, warnings)

    # Rule 2: owner/deadline must appear in the evidence (field_evidence first).
    _check_owner_deadline(item, cited(), by_id, ctx.utterances, meta, warnings)

    # Signal layer: open call / volunteer before rule 3; decision table and A1 (may add an evidence id).
    owner_signals(item, ctx, adj, warnings)
    decision_signals(item, ctx, adj, plan)
    action_row10(item, ctx, adj)
    evidence = cited()

    # Rule 3: actions need an owner.
    if item.type == ItemType.action and not item.owner:
        add_flag(item, "missing_owner")

    # Rule 4: money / percent / dates must be double-checked by a human.
    if has_number(item.content) or (item.condition and has_number(item.condition)):
        add_flag(item, "number_check")
    if item.type == ItemType.action and item.deadline and has_number(item.deadline):
        add_flag(item, "number_check")
    number_signals(item, by_id, adj)

    # Knowledge about the project that carries a figure may go stale.
    if item.type == ItemType.knowledge and item.knowledge_scope == "project" and has_quantity(item.content):
        add_flag(item, "needs_recheck")

    # Rule 5: who closed the decision? (the confidence cap for it is applied in _score)
    if item.type == ItemType.decision:
        closer = by_id[adj.closing] if adj.closing else evidence[-1]
        if closer_status(closer.speaker, meta) == "cannot":
            add_flag(item, "authority_unclear")

    # Rule 6: conditional without a condition is just open.
    if item.status == Status.conditional and not (item.condition or "").strip():
        warnings.append(f"\"{item.content}\": conditional nhưng thiếu điều kiện → chuyển về open")
        item.status = Status.open
        item.condition = None
    return adj


def _assign_ids(kept: list[Item], position: dict[str, int]) -> list[Item]:
    # Rule 8: ids by type in transcript order, then flagged / low-confidence first.
    def first_pos(it: Item) -> int:
        return min(position[e] for e in it.evidence)

    kept.sort(key=lambda it: (TYPE_ORDER.index(it.type), first_pos(it)))
    counters: dict[ItemType, int] = {}
    for it in kept:
        counters[it.type] = counters.get(it.type, 0) + 1
        it.item_id = f"{ID_PREFIX[it.type]}{counters[it.type]:02d}"
    kept.sort(key=lambda it: (0 if needs_attention(it) else 1, TYPE_ORDER.index(it.type), first_pos(it)))
    return kept


def _single_pass(
    items: list[Item], utterances: list[Utterance], meta: MeetingMeta | None
) -> tuple[list[Item], list[str]]:
    ctx = build_ctx(utterances, meta)
    warnings: list[str] = []
    prepared = [it for o in items if (it := _prepare(o, ctx.by_id, warnings)) is not None]
    plans = plan_a1(prepared, ctx, warnings)
    adjs = {id(it): _process_item(it, ctx, plans[id(it)], warnings) for it in prepared}
    for it in prepared:
        _score(it, utterances, meta, adjs[id(it)])  # preliminary: picks the winner of a merge
    kept, merge_warnings = merge_duplicates(prepared, ctx.position)
    warnings.extend(merge_warnings)
    apply_siblings(kept, adjs, ctx)
    for it in kept:
        adj = adjs[id(it)]
        _score(it, utterances, meta, adj)
        if it.confidence < LOW_CONFIDENCE:
            add_flag(it, "low_confidence")
        write_signal_check(it, adj)
    return _assign_ids(kept, ctx.position), warnings


def apply_rules(
    items: list[Item], utterances: list[Utterance], meta: MeetingMeta | None = None
) -> tuple[list[Item], list[str]]:
    """Return (checked & sorted items with ids, warnings).

    The pass is repeated until the result stops changing (merging duplicates or a code demotion can change what the
    next pass derives), so ``apply_rules(apply_rules(x))`` equals ``apply_rules(x)``.
    """
    warnings: list[str] = []
    current, signature = items, None
    for _ in range(MAX_PASSES):
        current, found = _single_pass(current, utterances, meta)
        warnings.extend(w for w in found if w not in warnings)
        new_signature = [it.model_dump_json() for it in current]
        if new_signature == signature:
            break
        signature = new_signature
    else:
        warnings.append(f"{WARN_PREFIX} Quy tắc hậu kiểm chưa ổn định sau {MAX_PASSES} lượt; kết quả có thể thay đổi nếu chạy lại.")
    warnings.extend(run_warnings(current))
    return current, warnings


def needs_attention(item: Item) -> bool:
    return bool(item.flags) or item.confidence < LOW_CONFIDENCE
