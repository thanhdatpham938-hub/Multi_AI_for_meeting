"""Reviews (accept / edit / reject, speaker renames) and JSON / Excel export."""

from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Item, ItemType, RunResult

REVIEWS_FILE = "reviews.json"
EXPORTED_REVIEWS = {"accepted", "edited"}
EDITABLE_FIELDS = ("content", "status", "owner", "deadline", "condition")

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
    elif fmt == "xlsx":
        path = run_dir / "export.xlsx"
        path.write_bytes(to_excel(result, only_reviewed=only_reviewed))
    else:
        raise ValueError(f"Định dạng không hỗ trợ: {fmt}")
    return path
