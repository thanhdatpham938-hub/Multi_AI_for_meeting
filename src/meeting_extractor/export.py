"""Reviews (accept / edit / reject, speaker renames) and JSON / Excel export."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from typing import Any, NamedTuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Item, ItemType, RunResult, Utterance

REVIEWS_FILE = "reviews.json"
EXPORTED_REVIEWS = {"accepted", "edited"}
EDITABLE_FIELDS = ("content", "status", "owner", "deadline", "condition", "pending_on", "follow_up_owner")
# Review keys that apply_reviews deliberately ignores: free-text reviewer note and answers to clarification questions.
NOTE_KEYS = ("note", "answers")

TYPE_LABELS = {
    ItemType.decision: "Quyết định",
    ItemType.action: "Việc cần làm",
    ItemType.blocker: "Vướng mắc",
    ItemType.request: "Yêu cầu",
    ItemType.open_issue: "Vấn đề còn mở",
    ItemType.knowledge: "Tri thức mới",
}
STATUS_LABELS = {
    "proposed": "Đề xuất",
    "superseded": "Bị thay thế",
    "confirmed": "Đã chốt",
    "conditional": "Có điều kiện",
    "deferred": "Hoãn",
    "open": "Chưa chốt",
}
FLAG_LABELS = {
    "no_closing_signal": "Không có tín hiệu chốt",
    "authority_unclear": "Chưa rõ thẩm quyền",
    "number_check": "Kiểm tra con số",
    "missing_owner": "Thiếu người phụ trách",
    "verify_failed": "Kiểm chứng không đạt",
    "low_confidence": "Độ tin cậy thấp",
    "tracker_failed": "Lỗi theo dõi quyết định",
    "conflicting_decision": "Quyết định mâu thuẫn",
    "unresolved_reference": "Tham chiếu chưa rõ",
    "needs_recheck": "Cần kiểm tra lại",
    "quote_mismatch": "Trích dẫn không khớp",
}
COMMITMENT_LABELS = {
    "assigned": "Được giao việc",
    "accepted": "Đã nhận việc",
    "volunteered_conditional": "Xung phong (có điều kiện)",
    "already_done": "Đã làm xong",
    "hypothetical": "Giả định",
}
SCOPE_LABELS = {"ephemeral": "Tạm thời", "project": "Theo dự án", "reusable": "Dùng lại nhiều lần"}
KNOWLEDGE_SCOPES_KEPT = ("project", "reusable")
KNOWLEDGE_SHEET = "Kho tri thức"
REVIEW_LABELS = {"pending": "Chờ duyệt", "accepted": "Chấp nhận", "edited": "Đã sửa", "rejected": "Loại"}


# ---------------------------------------------------------------- reviews


def empty_reviews() -> dict[str, Any]:
    return {"items": {}, "speaker_names": {}}


def load_reviews(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir) / REVIEWS_FILE
    if not path.exists():
        return empty_reviews()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"items": data.get("items", {}), "speaker_names": data.get("speaker_names", {})}


def save_reviews(run_dir: str | Path, reviews: dict[str, Any]) -> Path:
    path = Path(run_dir) / REVIEWS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def rename_speakers(text: str | None, names: dict[str, str]) -> str | None:
    if not text or not names:
        return text
    for label, real in names.items():
        if real.strip():
            text = re.sub(rf"\b{re.escape(label)}\b", real.strip(), text)
    return text


def apply_reviews(result: RunResult, reviews: dict[str, Any]) -> RunResult:
    """Return a copy of `result` with review decisions, edits and speaker names applied."""
    names = {k: v for k, v in reviews.get("speaker_names", {}).items() if v and v.strip()}
    out = result.model_copy(deep=True)
    for u in out.utterances:
        u.speaker = rename_speakers(u.speaker, names) or u.speaker
    items: list[Item] = []
    for item in out.items:
        rev = reviews.get("items", {}).get(item.item_id, {})
        updates: dict[str, Any] = {}
        for f in EDITABLE_FIELDS:
            if f in rev:
                updates[f] = rev[f] or None
        if "review" in rev:
            updates["review"] = rev["review"]
        item = item.model_copy(update=updates)
        item = Item.model_validate(item.model_dump())  # re-validate edited status values
        item.owner = rename_speakers(item.owner, names)
        item.content = rename_speakers(item.content, names) or item.content
        items.append(item)
    out.items = items
    return out


# ---------------------------------------------------------------- export


def to_json(result: RunResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _evidence_text(item: Item, result: RunResult) -> str:
    by_id = {u.id: u for u in result.utterances}
    return "\n".join(
        f"{e} [{by_id[e].time}] {by_id[e].speaker}: {by_id[e].text}" for e in item.evidence if e in by_id
    )


def _history_text(item: Item) -> str:
    return "\n".join(
        f"{STATUS_LABELS.get(h.status.value, h.status.value)}: {h.content or ''}"
        f"{f' ({h.reason})' if h.reason else ''} [{', '.join(h.evidence)}]"
        for h in item.history
    )


COLUMNS = [
    ("ID", 7), ("Chủ đề", 22), ("Nội dung", 48), ("Trạng thái", 14), ("Điều kiện", 24),
    ("Người phụ trách", 16), ("Hạn chót", 14), ("Độ tin cậy", 11), ("Cờ", 28),
    ("Trích dẫn", 60), ("Lịch sử", 50), ("Duyệt", 12),
]


def to_excel(result: RunResult, only_reviewed: bool = True) -> bytes:
    """One sheet per item type. By default only accepted/edited items are exported."""
    wb = Workbook()
    wb.remove(wb.active)
    header_fill = PatternFill("solid", fgColor="1F4E79")
    info = wb.create_sheet("Thông tin")
    meta = result.meta
    rows = [
        ("Cuộc họp", (meta.title if meta else None) or result.source_file),
        ("Ngày", meta.date if meta else None),
        ("Thời gian", f"{meta.start_time or ''} – {meta.end_time or ''}" if meta and (meta.start_time or meta.end_time) else None),
        ("Dự án", meta.project if meta else None),
        ("Chương trình", "; ".join(meta.agenda) if meta else None),
        ("Người tham dự", ", ".join(p.name for p in meta.participants) if meta else None),
        ("Run ID", result.run_id),
        ("Model", f"{result.model_light} / {result.model_strong}"),
    ]
    for r in rows:
        info.append([r[0], r[1] or ""])
    info.column_dimensions["A"].width = 18
    info.column_dimensions["B"].width = 70

    for item_type, label in TYPE_LABELS.items():
        items = [
            i for i in result.items
            if i.type == item_type and (not only_reviewed or i.review in EXPORTED_REVIEWS)
        ]
        if not items:
            continue
        ws = wb.create_sheet(label)
        ws.append([c for c, _ in COLUMNS])
        for idx, (_, width) in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=1, column=idx)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            ws.column_dimensions[get_column_letter(idx)].width = width
        for i in items:
            ws.append([
                i.item_id, i.topic, i.content,
                STATUS_LABELS.get(i.status.value, i.status.value) if i.status else "",
                i.condition or "", i.owner or "", i.deadline or "", round(i.confidence, 2),
                ", ".join(FLAG_LABELS.get(f, f) for f in i.flags),
                _evidence_text(i, result), _history_text(i), REVIEW_LABELS.get(i.review, i.review),
            ])
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
    _add_knowledge_sheet(wb, result, only_reviewed, header_fill)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_run(run_dir: str | Path, fmt: str = "xlsx", only_reviewed: bool = True) -> Path:
    from .pipeline import load_result

    run_dir = Path(run_dir)
    result = apply_reviews(load_result(run_dir), load_reviews(run_dir))
    if fmt == "json":
        path = run_dir / "export.json"
        path.write_text(to_json(result), encoding="utf-8")
    elif fmt == "knowledge":
        path = run_dir / "knowledge.json"
        path.write_text(knowledge_to_json(result, only_reviewed=only_reviewed), encoding="utf-8")
    elif fmt == "xlsx":
        path = run_dir / "export.xlsx"
        path.write_bytes(to_excel(result, only_reviewed=only_reviewed))
    else:
        raise ValueError(f"Định dạng không hỗ trợ: {fmt}")
    return path


# ---------------------------------------------------------------- evidence display (pure helpers)


def _fold_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase + collapse whitespace like provenance.normalize_text (without edge stripping).

    Returns the folded string and, for every folded char, the index in `text` it came from.
    """
    folded: list[str] = []
    index: list[int] = []
    prev_space = True  # drops leading whitespace
    for pos, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                folded.append(" ")
                index.append(pos)
            prev_space = True
            continue
        prev_space = False
        for low in ch.lower():
            folded.append(low)
            index.append(pos)
    return "".join(folded), index


def locate_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Span (start, end) of `quote` inside NFC-normalized `text`, matched after normalization; None if absent."""
    from .provenance import normalize_text  # local import keeps export light

    q = normalize_text(quote)
    if not q:
        return None
    folded, index = _fold_with_map(unicodedata.normalize("NFC", text))
    start = folded.find(q)
    if start < 0:
        return None
    return index[start], index[start + len(q) - 1] + 1


def highlight_quote_html(text: str, quote: str | None) -> tuple[str, bool | None]:
    """HTML-escaped `text` with the quote in <b>. Flag: None = no quote given, True = found, False = not found."""
    text = unicodedata.normalize("NFC", text)
    if not quote or not quote.strip():
        return html.escape(text), None
    span = locate_quote(text, quote)
    if span is None:
        return html.escape(text), False
    a, b = span
    return f"{html.escape(text[:a])}<b>{html.escape(text[a:b])}</b>{html.escape(text[b:])}", True


def utterance_context(utterances: list[Utterance], uid: str, n: int = 2) -> tuple[list[Utterance], list[Utterance]]:
    """Up to `n` utterances before and after `uid`; ([], []) when the id is unknown."""
    pos = next((k for k, u in enumerate(utterances) if u.id == uid), None)
    if pos is None:
        return [], []
    return utterances[max(0, pos - n):pos], utterances[pos + 1:pos + 1 + n]


def related_summaries(item: Item, result: RunResult, max_len: int = 80) -> list[tuple[str, str, bool]]:
    """(item_id, short content, exists) for each related item; unknown ids are kept with exists=False."""
    by_id = {i.item_id: i for i in result.items}
    out: list[tuple[str, str, bool]] = []
    for rid in item.related_items:
        other = by_id.get(rid)
        if other is None:
            out.append((rid, "", False))
            continue
        content = other.content if len(other.content) <= max_len else other.content[: max_len - 1].rstrip() + "…"
        out.append((rid, content, True))
    return out


# ---------------------------------------------------------------- clarification questions (pure helpers)

CLARIFY_FLAGS = ("missing_owner", "unresolved_reference", "conflicting_decision", "needs_recheck", "quote_mismatch")
NO_FOLLOW_UP = "no_follow_up"  # pseudo-reason: deferred / conditional item nobody follows up
_NUMBER_RE = re.compile(
    r"\d[\d.,/]*\s?(?:triệu|tỷ|nghìn|ngàn|%|đồng|vnđ|vnd|usd|k|phút|giờ|ngày|tuần|tháng)?(?!\w)", re.IGNORECASE
)


class Clarification(NamedTuple):
    item_id: str
    reason: str  # one of CLARIFY_FLAGS or NO_FOLLOW_UP
    question: str
    answer_field: str  # "owner" | "follow_up_owner" | "note"
    answered: str | None


def _short(text: str, n: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _first_quote(item: Item, result: RunResult) -> str:
    for quote in item.evidence_quotes.values():
        if quote.strip():
            return _short(quote)
    by_id = {u.id: u for u in result.utterances}
    for uid in item.evidence:
        if uid in by_id:
            return _short(by_id[uid].text)
    return _short(item.content)


def _number_in(text: str) -> str | None:
    match = _NUMBER_RE.search(text)
    return match.group(0).strip() if match else None


def _other_decision_text(item: Item, result: RunResult) -> str:
    by_id = {i.item_id: i for i in result.items}
    for rid in item.related_items:
        other = by_id.get(rid)
        if other is not None and other.type == ItemType.decision and other.item_id != item.item_id:
            return _short(other.content)
    return "một quyết định khác trong cuộc họp"


def clarification_question(item: Item, reason: str, result: RunResult) -> str:
    """Vietnamese follow-up question for one reason, from a fixed template (no AI)."""
    content = _short(item.content)
    if reason == "missing_owner":
        return f"Ai chịu trách nhiệm: {content}?"
    if reason == "unresolved_reference":
        return f"'{_first_quote(item, result)}' đang nói tới phương án nào?"
    if reason == "conflicting_decision":
        return f"{content} và {_other_decision_text(item, result)} – quyết định nào là cuối cùng?"
    if reason == "needs_recheck":
        number = _number_in(item.content)
        if number:
            return f"Con số '{number}' còn đúng không?"
        return f"Thông tin '{content}' còn đúng không?"
    if reason == "quote_mismatch":
        return f"Trích dẫn '{_first_quote(item, result)}' không khớp câu gốc – nội dung '{content}' có đúng không?"
    if reason == NO_FOLLOW_UP:
        return f"Ai theo dõi và báo lại (đang chờ: {item.pending_on or 'chưa rõ'}): {content}?"
    return f"{content} – cần làm rõ điều gì?"


def clarification_reasons(item: Item) -> list[str]:
    reasons = [f for f in CLARIFY_FLAGS if f in item.flags]
    status = item.status.value if item.status else None
    if status in ("deferred", "conditional") and not item.follow_up_owner:
        reasons.append(NO_FOLLOW_UP)
    return reasons


def _answer_field(reason: str) -> str:
    return {"missing_owner": "owner", NO_FOLLOW_UP: "follow_up_owner"}.get(reason, "note")


def clarification_items(result: RunResult, reviews: dict[str, Any] | None = None) -> list[Clarification]:
    """Questions for items needing clarification; rejected items are skipped; answered ones keep their answer.

    `result` should be the review-applied result (an answered owner / follow_up_owner already filled in).
    """
    reviews = reviews or {}
    out: list[Clarification] = []
    for item in result.items:
        if item.review == "rejected":
            continue
        answers = reviews.get("items", {}).get(item.item_id, {}).get("answers")
        answers = answers if isinstance(answers, dict) else {}
        for reason in clarification_reasons(item):
            out.append(Clarification(item.item_id, reason, clarification_question(item, reason, result),
                                     _answer_field(reason), answers.get(reason) or None))
        for reason in (r for r in answers if r == NO_FOLLOW_UP and NO_FOLLOW_UP not in clarification_reasons(item)):
            out.append(Clarification(item.item_id, reason, clarification_question(item, reason, result),
                                     _answer_field(reason), answers.get(reason) or None))
    return out


def answer_edits(existing: dict[str, Any], c: Clarification, answer: str) -> dict[str, Any]:
    """Fields to merge into a review entry when the reviewer answers `c` (caller sets review='edited')."""
    answer = answer.strip()
    answers = dict(existing.get("answers") or {})
    answers[c.reason] = answer
    edits: dict[str, Any] = {"answers": answers, "note": "\n".join(f"{k}: {v}" for k, v in answers.items())}
    if c.answer_field != "note":
        edits[c.answer_field] = answer
    return edits


# ---------------------------------------------------------------- knowledge base


def knowledge_entries(result: RunResult, only_reviewed: bool = False) -> list[dict[str, Any]]:
    """Knowledge items with scope project/reusable (never ephemeral, never rejected)."""
    meta = result.meta
    meeting = (meta.title if meta and meta.title else None) or Path(result.source_file).name
    by_id = {u.id: u for u in result.utterances}
    out: list[dict[str, Any]] = []
    for item in result.items:
        if item.type != ItemType.knowledge or item.knowledge_scope not in KNOWLEDGE_SCOPES_KEPT:
            continue
        if item.review == "rejected" or (only_reviewed and item.review not in EXPORTED_REVIEWS):
            continue
        utts = [{"id": u.id, "time": u.time, "speaker": u.speaker, "text": u.text}
                for u in (by_id[e] for e in item.evidence if e in by_id)]
        out.append({
            "item_id": item.item_id, "content": item.content, "topic": item.topic,
            "scope": item.knowledge_scope, "scope_label": SCOPE_LABELS[item.knowledge_scope],
            "needs_recheck": "needs_recheck" in item.flags, "confidence": round(item.confidence, 2),
            "review": item.review,
            "source": {"meeting": meeting, "date": meta.date if meta else None,
                       "project": meta.project if meta else None, "utterances": utts},
        })
    return out


def knowledge_to_json(result: RunResult, only_reviewed: bool = False) -> str:
    return json.dumps({"run_id": result.run_id, "entries": knowledge_entries(result, only_reviewed)},
                      ensure_ascii=False, indent=2)


KNOWLEDGE_COLUMNS = [
    ("ID", 7), ("Nội dung", 52), ("Chủ đề", 22), ("Phạm vi", 18), ("Cần kiểm tra lại", 16),
    ("Cuộc họp", 28), ("Ngày", 12), ("Câu nguồn", 60), ("Độ tin cậy", 11), ("Duyệt", 12),
]


def _add_knowledge_sheet(wb: Workbook, result: RunResult, only_reviewed: bool, header_fill: PatternFill) -> None:
    entries = knowledge_entries(result, only_reviewed)
    if not entries:
        return
    ws = wb.create_sheet(KNOWLEDGE_SHEET)
    ws.append([c for c, _ in KNOWLEDGE_COLUMNS])
    for idx, (_, width) in enumerate(KNOWLEDGE_COLUMNS, start=1):
        cell = ws.cell(row=1, column=idx)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        ws.column_dimensions[get_column_letter(idx)].width = width
    for e in entries:
        src = e["source"]
        cites = "\n".join(f"{u['id']} [{u['time']}] {u['speaker']}: {u['text']}" for u in src["utterances"])
        ws.append([e["item_id"], e["content"], e["topic"], e["scope_label"], "Có" if e["needs_recheck"] else "",
                   src["meeting"], src["date"] or "", cites, e["confidence"],
                   REVIEW_LABELS.get(e["review"], e["review"])])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
