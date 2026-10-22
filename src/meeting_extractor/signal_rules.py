"""Signal layer of the post-checks (PLAN_SIGNALS.md sections 4-5, 14-19). Pure code, no LLM.

`rules.apply_rules` orchestrates; everything that reads the lexical signals of `signals.py` lives here: the
comparison table for decisions, P3 (reversal), P1 (siblings), A1/A2 (authority), VO_CHU / XUNG_PHONG (owners), N1
(numbers), duplicate merging and the run-level warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .confidence import closer_status, load_weights
from .conflicts import sibling_pairs
from .models import HistoryEntry, Item, ItemType, MeetingMeta, Status, Utterance
from .parsing import base_speaker_name, is_anonymous_speaker
from .signals import (
    GROUP_A,
    GROUP_B,
    TAG_LABELS,
    Signal,
    _transcript_names,
    closing_utterance_id,
    normalize,
    tag_transcript,
    tag_utterance,
    tags_of,
    windows,
)

SIGNAL_FLAGS = (
    "signal_mismatch", "possible_action", "possible_closing", "possible_superseded",
    "authority_unconfirmed", "number_not_in_evidence",
)  # fmt: skip
WARN_PREFIX = "[Cảnh báo cờ]"
A1_FUSE_RATIO = 0.4  # A1 is switched off for a run when it would demote more than this share ...
A1_FUSE_MIN = 5  # ... of the decisions that were confirmed (only meaningful from this many decisions)
RUN_WARN_MIN = 5  # minimum number of decisions before the run-level flag-rate warning applies
MISMATCH_WARN_RATIO = 0.30
SUPERSEDED_WARN_RATIO = 0.25
MERGE_OVERLAP = 0.8
MERGE_SCORE_TIE = 0.05  # scores this close: prefer the longer content
WEAK_C_TAGS = frozenset({"HOAN", "DIEU_KIEN", "DE_XUAT", "MIA_MAI", "CHUYEN_Y"})
REVERSAL_TAGS = frozenset({"DAO_NGUOC", "BO_SUNG_NGUOC", "HOAN"})
STICKY_RULES = frozenset({"authority_confirmed", "merged", "no_owner", "volunteer"})  # cannot be re-derived
NOTE_ORDER = ("authority_confirmed", "no_owner", "volunteer", "group_b", "possible_action", "short_ack", "weak",
              "unverified", "possible_closing", "authority_unconfirmed", "reversal", "sibling", "number", "merged")  # fmt: skip
TASK_PHRASES = ("tự quyết", "tự đề xuất", "tự cân đối", "tự lo")

ROW1_RE = re.compile(r"^Code: câu (u\d+) có dấu hiệu")
A1_RE = re.compile(r"^Code: .* không có quyền chốt và không ai có quyền xác nhận")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+")
_NUM_RE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?:/\d+)*")
_WORD_RE = re.compile(r"\w+")


# ------------------------------------------------------------------ context and adjustments


@dataclass
class Ctx:
    utterances: list[Utterance]
    meta: MeetingMeta | None
    by_id: dict[str, Utterance]
    position: dict[str, int]
    tagged: dict[str, list[Signal]]
    names: list[str]
    has_decider: bool

    def tags(self, uid: str) -> set[str]:
        return tags_of(self.tagged.get(uid, []))

    def after(self, uid: str, n: int) -> list[Utterance]:
        pos = self.position[uid]
        return self.utterances[pos + 1 : pos + 1 + n]

    def can_decide(self, u: Utterance) -> bool:
        return closer_status(u.speaker, self.meta) == "can"

    def closing(self, item: Item) -> str | None:
        return closing_utterance_id(item.evidence, self.tagged, self.position)


@dataclass
class Adj:
    """Score adjustments and explanation produced by the signal layer for one item."""

    terms: dict[str, float] = field(default_factory=dict)
    caps: list[str] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    closing: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    missing_numbers: list[str] = field(default_factory=list)

    def note(self, rule: str, utterance: str | None, text: str) -> None:
        entry = {"rule": rule, "utterance": utterance, "text": text}
        if entry not in self.notes:
            self.notes.append(entry)


@dataclass
class A1Plan:
    kind: str = "none"  # "none" | "confirm" | "demote"
    uid: str | None = None  # confirming utterance (kind == "confirm")
    closing: str | None = None  # closing utterance of the item (decisions only)


def build_ctx(utterances: list[Utterance], meta: MeetingMeta | None) -> Ctx:
    return Ctx(
        utterances=utterances,
        meta=meta,
        by_id={u.id: u for u in utterances},
        position={u.id: i for i, u in enumerate(utterances)},
        tagged=tag_transcript(utterances, meta),
        names=_transcript_names(utterances, meta),
        has_decider=bool(meta and any(p.can_decide for p in meta.participants)),
    )


# ------------------------------------------------------------------ small helpers


def add_flag(item: Item, flag: str) -> None:
    if flag not in item.flags:
        item.flags.append(flag)


def _penalize(item: Item, adj: Adj, flag: str, term: str | None = None, cap: str | None = None) -> None:
    """Flag the item and record a score term and/or a hard cap for `_score`."""
    add_flag(item, flag)
    if term:
        adj.terms[term] = load_weights()[term]
    if cap and cap not in adj.caps:
        adj.caps.append(cap)


def _demote(item: Item, uid: str, reason: str) -> None:
    """Lower a decision to `proposed` and record why (never deletes anything)."""
    item.status = Status.proposed
    item.history.append(HistoryEntry(status=Status.proposed, content=item.content, evidence=[uid], reason=reason))


def _label(tag: str) -> str:
    return TAG_LABELS.get(tag, tag)


def _short(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _tags_dict(sigs: list[Signal]) -> dict[str, str]:
    return {s.tag: s.phrase for s in sigs}


def _code_entry(item: Item, regex: re.Pattern[str]) -> HistoryEntry | None:
    for h in reversed(item.history):
        if h.reason and regex.match(h.reason):
            return h
    return None


def _has_code_demotion(item: Item) -> bool:
    return item.status == Status.proposed and bool(_code_entry(item, ROW1_RE) or _code_entry(item, A1_RE))


def _non_code_history_ids(item: Item) -> set[str]:
    return {e for h in item.history if not (h.reason or "").startswith("Code:") for e in h.evidence}


def _name_in_text(name: str, text: str) -> bool:
    n = normalize(base_speaker_name(name))
    return bool(n) and bool(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", normalize(text)))


# ------------------------------------------------------------------ A1 / A2 (section 15)


def _confirming_utterance(item: Item, closing: str, ctx: Ctx) -> str | None:
    """A group A utterance by someone who can decide: cited by the item, else within the next few utterances."""
    candidates = [ctx.by_id[e] for e in item.evidence if e in ctx.by_id]
    candidates += ctx.after(closing, windows()["authority_confirm_after"])
    for u in sorted({u.id: u for u in candidates}.values(), key=lambda u: ctx.position[u.id]):
        tg = ctx.tags(u.id)
        if ctx.can_decide(u) and tg & GROUP_A and not tg & GROUP_B and "DAO_NGUOC" not in tg:
            return u.id
    return None


def _a1_outcome(item: Item, closing: str | None, ctx: Ctx) -> tuple[str, str | None]:
    """("confirm", utterance id) | ("demote", None) | ("none", None)."""
    if not ctx.has_decider or closing is None:
        return "none", None
    closer = ctx.by_id[closing]
    if is_anonymous_speaker(closer.speaker) or closer_status(closer.speaker, ctx.meta) != "cannot":
        return "none", None
    confirmer = _confirming_utterance(item, closing, ctx)
    if confirmer:
        return "confirm", confirmer
    return ("demote", None) if ctx.tags(closing) & GROUP_A else ("none", None)


def _undo_a1_demotion(item: Item) -> None:
    item.history = [h for h in item.history if not (h.reason and A1_RE.match(h.reason))]
    item.status = Status.confirmed


def plan_a1(items: list[Item], ctx: Ctx, warnings: list[str]) -> dict[int, A1Plan]:
    """Decide A1 for the whole run. The fuse counts decisions that were confirmed before ANY code demotion, so the
    verdict is the same on every pass. When it trips, A1 demotions from an earlier pass are undone."""
    plans = {id(it): A1Plan(closing=ctx.closing(it) if it.type == ItemType.decision else None) for it in items}
    eligible = [it for it in items if it.type == ItemType.decision and (it.status == Status.confirmed or _has_code_demotion(it))]
    for it in eligible:
        plan = plans[id(it)]
        plan.kind, plan.uid = _a1_outcome(it, plan.closing, ctx)
    demotes = sum(plans[id(it)].kind == "demote" for it in eligible)
    fused = len(eligible) >= A1_FUSE_MIN and demotes / len(eligible) > A1_FUSE_RATIO
    if fused:
        warnings.append(
            f"{WARN_PREFIX} Kiểm tra thẩm quyền (A1) định hạ {demotes}/{len(eligible)} quyết định đã chốt "
            f"({demotes / len(eligible):.0%}, vượt {A1_FUSE_RATIO:.0%}) nên bị bỏ cho lần chạy này. "
            "Có thể danh sách người dự (quyền chốt) đang sai, hãy kiểm tra lại."
        )
    for it in eligible:
        plan = plans[id(it)]
        if (fused or plan.kind != "demote") and it.status == Status.proposed and _code_entry(it, A1_RE):
            _undo_a1_demotion(it)
        if fused:
            plans[id(it)] = A1Plan(closing=plan.closing)
    return plans


def _apply_a1_confirm(item: Item, uid: str, ctx: Ctx, adj: Adj) -> None:
    item.evidence = sorted(dict.fromkeys([*item.evidence, uid]), key=lambda e: ctx.position[e])
    item.flags = [f for f in item.flags if f != "authority_unclear"]
    who = base_speaker_name(ctx.by_id[uid].speaker)
    adj.note("authority_confirmed", uid, f"{who} có quyền chốt đã xác nhận ở câu {uid}; dùng câu này làm câu chốt.")


def _demote_a1(item: Item, cid: str, ctx: Ctx, adj: Adj) -> None:
    who = base_speaker_name(ctx.by_id[cid].speaker)
    n = windows()["authority_confirm_after"]
    _demote(item, cid, f"Code: {who} không có quyền chốt và không ai có quyền xác nhận trong {n} câu sau")
    _note_a1_unconfirmed(item, cid, who, adj)


def _note_a1_unconfirmed(item: Item, cid: str, who: str, adj: Adj) -> None:
    add_flag(item, "authority_unconfirmed")
    adj.note("authority_unconfirmed", cid, f"{who} không có quyền chốt và chưa ai có quyền xác nhận; đã hạ về 'proposed'.")


# ------------------------------------------------------------------ decision: comparison table (section 5)


def _clean_closing_in_clause(uid: str, ctx: Ctx) -> bool:
    """True when some single sentence of the utterance has CHOT_RO and no group B tag ("Chốt vậy nhé. Có ai ... không?")."""
    u = ctx.by_id[uid]
    pos = ctx.position[uid]
    prev = ctx.utterances[pos - 1] if pos > 0 else None
    for part in _SENTENCE_SPLIT.split(u.text):
        if not part.strip():
            continue
        tg = tags_of(tag_utterance(u.model_copy(update={"text": part}), prev, ctx.names))
        if "CHOT_RO" in tg and not tg & GROUP_B:
            return True
    return False


def _demote_group_b(item: Item, uid: str, sigs: list[Signal], adj: Adj, restore: bool) -> None:
    bad = next(s for s in sigs if s.tag in GROUP_B)
    label = _label(bad.tag)
    if not restore:
        _demote(item, uid, f"Code: câu {uid} có dấu hiệu {label} ('{bad.phrase}')")
    _penalize(item, adj, "signal_mismatch", term="signal_strong_conflict")
    adj.note("group_b", uid, f"Câu {uid} có dấu hiệu {label} ('{bad.phrase}') nên không được coi là câu chốt; đã hạ về 'proposed'.")


def _task_like(item: Item, ctx: Ctx) -> bool:
    norm = normalize(item.content)
    if any(p in norm for p in TASK_PHRASES):
        return True
    return any(len(n := normalize(name)) >= 2 and re.match(rf"{re.escape(n)}(?!\w)", norm) for name in ctx.names)


def _table_confirmed(item: Item, cid: str, sigs: list[Signal], ctx: Ctx, adj: Adj) -> None:
    """Rows 1-7 for a `confirmed` decision whose closing utterance is `cid`."""
    tags = tags_of(sigs)
    phrases = _tags_dict(sigs)
    group_b = tags & GROUP_B
    if group_b:
        if "CHOT_RO" in tags and _clean_closing_in_clause(cid, ctx):
            labels = ", ".join(_label(t) for t in sorted(group_b))
            _penalize(item, adj, "signal_mismatch", term="signal_weak_conflict")
            adj.note("weak", cid, f"Câu {cid} vừa có từ chốt vừa có dấu hiệu {labels}, nhưng có một câu con chốt rõ: chỉ trừ điểm nhẹ.")
        else:
            _demote_group_b(item, cid, sigs, adj, restore=False)
        return
    if "CHOT_RO" in tags:
        pass
    elif "GIAO_VIEC" in tags and _task_like(item, ctx):
        _penalize(item, adj, "possible_action", cap="cap_possible_action")
        adj.note("possible_action", cid, f"Câu {cid} có dấu hiệu giao việc ('{phrases['GIAO_VIEC']}'): có thể đây là việc cần làm, không phải quyết định.")
    elif "CHOT_NGAM" in tags:
        pass
    elif "DONG_Y_NGAN" in tags:
        _penalize(item, adj, "signal_mismatch", cap="cap_signal_short_ack")
        adj.note("short_ack", cid, f"Câu chốt {cid} chỉ là lời đồng ý ngắn ('{phrases['DONG_Y_NGAN']}'), không nêu nội dung.")
    elif tags & WEAK_C_TAGS:
        labels = ", ".join(_label(t) for t in sorted(tags & WEAK_C_TAGS))
        _penalize(item, adj, "signal_mismatch", term="signal_weak_conflict")
        adj.note("weak", cid, f"Câu chốt {cid} có dấu hiệu {labels}, chưa chắc là chốt dứt khoát.")
    elif not tags:
        adj.caps.append("cap_signal_unverified")
        adj.note("unverified", cid, f"Code không thấy từ chốt hay đồng ý trong câu {cid}.")
    if "TAM_THOI" in tags:
        _penalize(item, adj, "signal_mismatch", cap="cap_signal_unverified")
        adj.note("weak", cid, f"Câu chốt {cid} chỉ là chốt tạm ('{phrases['TAM_THOI']}').")


def _apply_reversal(item: Item, cid: str, ctx: Ctx, adj: Adj) -> None:
    """P3: one of the next utterances flips / defers the decision and the item did not account for it."""
    own = set(item.evidence) | _non_code_history_ids(item)
    for nxt in ctx.after(cid, windows()["reversal_after"]):
        tg = ctx.tags(nxt.id)
        if not tg & REVERSAL_TAGS or nxt.id in own or "CHOT_RO" in tg:
            continue
        reason = f"Code: ngay sau câu chốt có câu {nxt.id} '{_short(nxt.text)}'"
        if not any(h.reason == reason for h in item.history):
            item.history.append(HistoryEntry(status=Status.confirmed, content=item.content, reason=reason, evidence=[cid]))
        _penalize(item, adj, "possible_superseded", term="signal_reversal_penalty", cap="cap_possible_superseded")
        adj.note("reversal", nxt.id, f"Ngay sau câu chốt có câu {nxt.id} '{_short(nxt.text)}' có thể đã đổi hoặc hoãn quyết định này.")
        return


def _restore_marker(item: Item, ctx: Ctx, adj: Adj) -> bool:
    """Re-derive notes/flags of a demotion done by code in an earlier pass (no new history step)."""
    if item.status != Status.proposed:
        return False
    entry = _code_entry(item, ROW1_RE)
    if entry and entry.evidence:
        uid = entry.evidence[0]
        sigs = ctx.tagged.get(uid, [])
        if any(s.tag in GROUP_B for s in sigs):
            adj.closing, adj.tags = uid, _tags_dict(sigs)
            _demote_group_b(item, uid, sigs, adj, restore=True)
            return True
    entry = _code_entry(item, A1_RE)
    if entry and entry.evidence:
        uid = entry.evidence[0]
        adj.closing, adj.tags = uid, _tags_dict(ctx.tagged.get(uid, []))
        _note_a1_unconfirmed(item, uid, base_speaker_name(ctx.by_id[uid].speaker), adj)
        return True
    return False


def decision_signals(item: Item, ctx: Ctx, adj: Adj, plan: A1Plan) -> None:
    if item.type != ItemType.decision or item.status is None:
        return
    if _restore_marker(item, ctx, adj):
        return
    cid = plan.closing
    if cid is None:
        return
    if item.status == Status.confirmed and plan.kind == "confirm" and plan.uid:
        _apply_a1_confirm(item, plan.uid, ctx, adj)
        cid = plan.uid  # the utterance of the person who can decide is the closing one
    sigs = ctx.tagged.get(cid, [])
    adj.closing, adj.tags = cid, _tags_dict(sigs)
    tags = tags_of(sigs)
    if item.status == Status.confirmed:
        _table_confirmed(item, cid, sigs, ctx, adj)
        if item.status == Status.confirmed and plan.kind == "demote":
            _demote_a1(item, cid, ctx, adj)
        if item.status == Status.confirmed:
            _apply_reversal(item, cid, ctx, adj)
    elif item.status in (Status.open, Status.proposed) and "CHOT_RO" in tags and not tags & GROUP_B:
        add_flag(item, "possible_closing")
        adj.note("possible_closing", cid, f"Câu {cid} có từ chốt rõ ('{_tags_dict(sigs)['CHOT_RO']}') nhưng mục chưa ở trạng thái đã chốt.")


# ------------------------------------------------------------------ action: row 10, VO_CHU / XUNG_PHONG (section 16)


def action_row10(item: Item, ctx: Ctx, adj: Adj) -> None:
    if item.type != ItemType.action or item.commitment not in ("assigned", "accepted") or not item.evidence:
        return
    tag_sets = [ctx.tags(e) for e in item.evidence]
    if all("CAU_HOI" in t for t in tag_sets) and not any("GIAO_VIEC" in t for t in tag_sets):
        _penalize(item, adj, "signal_mismatch", term="signal_weak_conflict")
        adj.note("weak", item.evidence[-1], "Mọi câu bằng chứng đều là câu hỏi, không có câu giao việc rõ ràng.")


def _volunteer_confirmed(owner: str, src_uid: str, ctx: Ctx) -> bool:
    for nxt in ctx.after(src_uid, windows()["volunteer_confirm_after"]):
        tg = ctx.tags(nxt.id)
        if ctx.can_decide(nxt) and (tg & GROUP_A or ("GIAO_VIEC" in tg and _name_in_text(owner, nxt.text))):
            return True
    return False


def _clear_owner(item: Item) -> None:
    item.owner = None
    item.field_evidence = {k: v for k, v in item.field_evidence.items() if k != "owner"}


def _owner_is_stated(item: Item, ev: list[str], ctx: Ctx) -> bool:
    """The owner is named in a cited sentence, or speaks a cited / source sentence that is not an open call."""
    owner = item.owner or ""
    if any(_name_in_text(owner, ctx.by_id[e].text) for e in ev):
        return True
    own = normalize(base_speaker_name(owner))
    spoken = [*ev, *(e for e in item.field_evidence.get("owner", []) if e in ctx.by_id)]
    return any(
        normalize(base_speaker_name(ctx.by_id[e].speaker)) == own and "VO_CHU" not in ctx.tags(e) for e in spoken
    )


def owner_signals(item: Item, ctx: Ctx, adj: Adj, warnings: list[str]) -> None:
    if item.type != ItemType.action or not item.owner:
        return
    owner = item.owner
    ev = [e for e in item.evidence if e in ctx.by_id]
    open_call = [e for e in ev if "VO_CHU" in ctx.tags(e)]
    if open_call and not _owner_is_stated(item, ev, ctx):
        warnings.append(f"Bỏ owner \"{owner}\" của \"{item.content}\": câu gốc chỉ kêu gọi người nhận việc, không nêu tên")
        adj.note("no_owner", open_call[-1], f"Câu {open_call[-1]} chỉ hỏi 'ai làm', không nêu tên ai; bỏ owner '{owner}'.")
        _clear_owner(item)
        return
    if not ctx.has_decider:
        return
    own = normalize(base_speaker_name(owner))
    sources = item.field_evidence.get("owner") or [
        e for e in ev if normalize(base_speaker_name(ctx.by_id[e].speaker)) == own
    ]
    volunteers = [e for e in sources if e in ctx.by_id and "XUNG_PHONG" in ctx.tags(e)]
    if volunteers:
        src = max(volunteers, key=lambda e: ctx.position[e])
        if not _volunteer_confirmed(owner, src, ctx):
            warnings.append(f"Bỏ owner \"{owner}\" của \"{item.content}\": mới xung phong, chưa được giao")
            adj.note("volunteer", src, f"{owner} mới xung phong ở câu {src}, chưa có người có quyền giao việc; bỏ owner.")
            _clear_owner(item)


# ------------------------------------------------------------------ N1 (section 18)


def _canon_part(part: str) -> str:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", part):
        part = part.replace(".", "")
    else:
        part = part.replace(",", ".")
    head, _, tail = part.partition(".")
    tail = tail.rstrip("0")
    return (head.lstrip("0") or "0") + (f".{tail}" if tail else "")


def _number_tokens(text: str) -> list[tuple[str, list[str]]]:
    """[(original token, canonical parts)] for every number in `text` ("15/11" has two parts)."""
    return [(m.group(0), [_canon_part(p) for p in m.group(0).split("/")]) for m in _NUM_RE.finditer(text)]


def _content_numbers(item: Item) -> set[str]:
    return {"/".join(parts) for _, parts in _number_tokens(item.content)}


def _missing_numbers(item: Item, by_id: dict[str, Utterance]) -> list[str]:
    content_nums = _number_tokens(item.content)
    if not content_nums:
        return []
    ids = [*item.evidence, *(e for h in item.history for e in h.evidence), *(e for v in item.field_evidence.values() for e in v)]
    seen: set[str] = set()
    for uid in dict.fromkeys(ids):
        if uid in by_id:
            for _, parts in _number_tokens(by_id[uid].text):
                seen.update(parts)
                seen.add("/".join(parts))
    missing = [tok for tok, parts in content_nums if "/".join(parts) not in seen and not all(p in seen for p in parts)]
    return list(dict.fromkeys(missing))


def number_signals(item: Item, by_id: dict[str, Utterance], adj: Adj) -> None:
    missing = _missing_numbers(item, by_id)
    if not missing:
        return
    _penalize(item, adj, "number_not_in_evidence", term="number_not_in_evidence_penalty")
    adj.missing_numbers = missing
    shown = ", ".join(f"'{m}'" for m in missing)
    adj.note("number", None, f"Số {shown} trong nội dung không có trong các câu gốc được dẫn.")


# ------------------------------------------------------------------ merge duplicates (section 17.2 step 2)


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _differs(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and normalize(a or "") != normalize(b or "")


def _numbers_conflict(a: Item, b: Item) -> bool:
    na, nb = _content_numbers(a), _content_numbers(b)
    return not (na <= nb or nb <= na)  # one side may simply omit the figures, but not disagree


def _is_duplicate(a: Item, b: Item) -> bool:
    if a.type != b.type or a.status != b.status or not set(a.evidence) & set(b.evidence):
        return False
    if _differs(a.owner, b.owner) or _differs(a.deadline, b.deadline) or _differs(a.condition, b.condition):
        return False
    if _numbers_conflict(a, b):
        return False
    ta, tb = _tokens(a.content), _tokens(b.content)
    return bool(ta) and bool(tb) and len(ta & tb) / min(len(ta), len(tb)) >= MERGE_OVERLAP


def _pick_winner(a: Item, b: Item) -> tuple[Item, Item]:
    """(winner, loser): close scores prefer the longer content, otherwise the higher score, then more evidence."""
    if abs(a.confidence - b.confidence) <= MERGE_SCORE_TIE + 1e-9 and len(a.content) != len(b.content):
        return (a, b) if len(a.content) > len(b.content) else (b, a)
    key_a, key_b = (a.confidence, len(set(a.evidence))), (b.confidence, len(set(b.evidence)))
    return (b, a) if key_b > key_a else (a, b)  # a tie keeps the earlier item


def _fill_missing(winner: Item, loser: Item) -> None:
    for name in ("owner", "deadline", "condition", "commitment", "pending_on", "follow_up_owner"):
        if getattr(winner, name) is None and getattr(loser, name) is not None:
            setattr(winner, name, getattr(loser, name))
    for key, ids in loser.field_evidence.items():
        winner.field_evidence.setdefault(key, ids)
    if winner.owner is not None:
        winner.flags = [f for f in winner.flags if f != "missing_owner"]


def _absorb(winner: Item, loser: Item, position: dict[str, int]) -> None:
    winner.evidence = sorted(dict.fromkeys([*winner.evidence, *loser.evidence]), key=lambda e: position[e])
    _fill_missing(winner, loser)
    flags = [f for f in loser.flags if f not in ("low_confidence", "missing_owner")]
    winner.flags = list(dict.fromkeys([*winner.flags, *flags]))
    if winner.owner is None and "missing_owner" in loser.flags:
        add_flag(winner, "missing_owner")
    known = {(h.status, h.content, tuple(h.evidence)) for h in winner.history}
    winner.history += [h for h in loser.history if (h.status, h.content, tuple(h.evidence)) not in known]
    ref = f"{loser.item_id} " if loser.item_id else ""
    winner.history.append(HistoryEntry(
        status=winner.status or Status.open, content=loser.content, evidence=list(loser.evidence),
        reason=f"Code: gộp với mục trùng {ref}'{_short(loser.content)}'",
    ))  # fmt: skip
    note = {"rule": "merged", "utterance": None, "text": f"Đã gộp với mục trùng {ref}'{_short(loser.content)}'."}
    notes = [n for n in winner.signal_check.get("notes", []) if isinstance(n, dict)]
    winner.signal_check = {**winner.signal_check, "notes": [*notes, note]}


def merge_duplicates(items: list[Item], position: dict[str, int]) -> tuple[list[Item], list[str]]:
    """Merge items of one type/status that share evidence and whose contents overlap (vs. the shorter one).

    Never merges items that disagree on owner, deadline, condition or figures. A warning is emitted per merge.
    """
    items, warnings = list(items), []
    while True:
        pair = next(((a, b) for i, a in enumerate(items) for b in items[i + 1 :] if _is_duplicate(a, b)), None)
        if pair is None:
            return items, warnings
        winner, loser = _pick_winner(*pair)
        _absorb(winner, loser, position)
        items.remove(loser)
        warnings.append(f"Gộp hai mục trùng: \"{loser.content}\" vào \"{winner.content}\"")


# ------------------------------------------------------------------ P1 siblings (section 14.3)


def apply_siblings(items: list[Item], adjs: dict[int, Adj], ctx: Ctx) -> None:
    """P1 (narrow): of two `confirmed` decisions about the same issue, the one closed earlier may be superseded."""
    closing = {id(it): ctx.closing(it) for it in items if it.type == ItemType.decision}
    pos = lambda it: ctx.position[closing[id(it)]] if closing.get(id(it)) else -1  # noqa: E731
    for a, b in sibling_pairs(items):
        if pos(a) == pos(b):
            continue
        earlier, later = (a, b) if pos(a) < pos(b) else (b, a)
        adj = adjs.setdefault(id(earlier), Adj())
        _penalize(earlier, adj, "possible_superseded", cap="cap_superseded_sibling")
        adj.note("sibling", closing[id(later)], f"Có quyết định đã chốt khác về cùng vấn đề, chốt muộn hơn: '{_short(later.content)}'.")


# ------------------------------------------------------------------ notes and run-level warnings


def carry_sticky(item: Item, adj: Adj) -> None:
    """Notes that cannot be re-derived (written by an earlier pass) stay on the item."""
    for n in item.signal_check.get("notes", []):
        if isinstance(n, dict) and n.get("rule") in STICKY_RULES:
            adj.note(n["rule"], n.get("utterance"), str(n.get("text", "")))


def write_signal_check(item: Item, adj: Adj) -> None:
    for n in item.signal_check.get("notes", []):  # notes written by the merge step of this pass
        if isinstance(n, dict) and n.get("rule") == "merged":
            adj.note("merged", n.get("utterance"), str(n.get("text", "")))
    order = {r: i for i, r in enumerate(NOTE_ORDER)}
    notes = sorted(adj.notes, key=lambda n: order.get(n["rule"], len(order)))  # stable
    check: dict[str, Any] = {}
    if item.type == ItemType.decision or notes:
        check = {"closing_utterance": adj.closing, "tags": adj.tags, "notes": notes}
        if adj.missing_numbers:
            check["missing_numbers"] = adj.missing_numbers
    item.signal_check = check


def run_warnings(items: list[Item]) -> list[str]:
    decisions = [i for i in items if i.type == ItemType.decision]
    if len(decisions) < RUN_WARN_MIN:  # a ratio over 1-4 decisions says nothing
        return []
    out: list[str] = []
    for flag, limit, what in (
        ("signal_mismatch", MISMATCH_WARN_RATIO, "lệch tín hiệu code/AI"),
        ("possible_superseded", SUPERSEDED_WARN_RATIO, "có thể đã bị thay thế"),
    ):
        n = sum(1 for d in decisions if flag in d.flags)
        if n / len(decisions) > limit:
            out.append(
                f"{WARN_PREFIX} {n}/{len(decisions)} quyết định ({n / len(decisions):.0%}) bị cờ '{what}', "
                f"vượt {limit:.0%}: bộ dò tín hiệu có thể đang quá nhạy, hãy xem lại trước khi tin các cờ này."
            )
    return out
