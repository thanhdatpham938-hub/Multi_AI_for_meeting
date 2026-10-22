"""Streamlit review app.

    streamlit run app/review_app.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meeting_extractor.audio import check_audio_file, clip_range, format_time  # noqa: E402
from meeting_extractor.config import load_settings  # noqa: E402
from meeting_extractor.export import (  # noqa: E402
    COMMITMENT_LABELS,
    FLAG_LABELS,
    REVIEW_LABELS,
    SCOPE_LABELS,
    STATUS_LABELS,
    signal_notes,
    split_flags,
    answer_edits,
    apply_reviews,
    clarification_items,
    highlight_quote_html,
    knowledge_entries,
    knowledge_to_json,
    load_reviews,
    md_safe,
    related_summaries,
    resolve_edits,
    save_reviews,
    to_excel,
    to_json,
    utterance_context,
)
from meeting_extractor import audio as _audio  # noqa: E402
from meeting_extractor.llm import LLMError, make_llm  # noqa: E402
from meeting_extractor.models import Item, ItemType, MeetingMeta, Participant, RunResult, Status  # noqa: E402
from meeting_extractor.parsing import is_anonymous_speaker, parse_text  # noqa: E402
from meeting_extractor import pipeline as _pipeline  # noqa: E402
from meeting_extractor import qa as _qa  # noqa: E402
from meeting_extractor.pipeline import load_result, run_text  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "meetsync_logo.png"
ICON = ASSETS / "meetsync_icon.png"
st.set_page_config(page_title="MeetSync", page_icon=str(ICON), layout="wide")
SETTINGS = load_settings()
RUNS_DIR = SETTINGS.runs_dir

GROUPS: list[tuple[str, str, list[ItemType]]] = [
    # key, label, types
    ("decision", "Quyết định", [ItemType.decision]),
    ("action", "Việc cần làm", [ItemType.action]),
    ("open", "Vấn đề còn mở", [ItemType.open_issue]),
    ("other", "Vấn đề khác", [ItemType.blocker, ItemType.request, ItemType.knowledge]),
]
# Line icons (Lucide-style SVG paths): key -> (paths, stroke colour, tile background)
GROUP_ICONS: dict[str, tuple[str, str, str]] = {
    "decision": ('<circle cx="12" cy="12" r="10"/><path d="m8.5 12 2.5 2.5 4.5-5"/>', "#16a34a", "#e3f5e9"),
    "action": ('<path d="m3 6 1.5 1.5L7.5 4.5"/><path d="m3 12.5 1.5 1.5 3-3"/><path d="m3 19 1.5 1.5 3-3"/>'
               '<path d="M11 6h10"/><path d="M11 12.5h10"/><path d="M11 19h10"/>', "#2f5bea", "#e6edfe"),
    "open": ('<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
             '<path d="M12 9v4"/><path d="M12 17h.01"/>', "#d97706", "#fdf0dc"),
    "other": ('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
              '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
              "#7c3aed", "#f0e9fd"),
}


def group_icon(key: str, size: int = 22) -> str:
    paths, color, _ = GROUP_ICONS[key]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'style="vertical-align:-0.2em">{paths}</svg>')
TYPE_LABEL = {
    ItemType.decision: "Quyết định", ItemType.action: "Việc cần làm", ItemType.blocker: "Vướng mắc",
    ItemType.request: "Yêu cầu", ItemType.open_issue: "Vấn đề còn mở", ItemType.knowledge: "Tri thức mới",
}
STATUS_STYLE = {
    "confirmed": ("#e7f6ec", "#1e7b3c"), "conditional": ("#fff3e0", "#b45f06"),
    "deferred": ("#f1ebfb", "#6b3fb3"), "open": ("#fdf6d8", "#8a6d00"),
    "proposed": ("#e8f0fe", "#1a56c4"), "superseded": ("#fde8e8", "#b42318"),
}
FLAG_STYLE = {
    "verify_failed": ("#fde8e8", "#b42318"), "authority_unclear": ("#fff3e0", "#b45f06"),
    "number_check": ("#e8f0fe", "#1a56c4"), "missing_owner": ("#fdf6d8", "#8a6d00"),
    "no_closing_signal": ("#f1ebfb", "#6b3fb3"), "low_confidence": ("#f2f4f7", "#475467"),
    "tracker_failed": ("#fde8e8", "#b42318"), "conflicting_decision": ("#fff3e0", "#b45f06"),
    "unresolved_reference": ("#f1ebfb", "#6b3fb3"), "needs_recheck": ("#e8f0fe", "#1a56c4"),
    "quote_mismatch": ("#fde8e8", "#b42318"),
    "signal_mismatch": ("#fde8e8", "#b42318"), "possible_action": ("#fdf6d8", "#8a6d00"),
    "possible_closing": ("#f1ebfb", "#6b3fb3"), "possible_superseded": ("#fff3e0", "#b45f06"),
    "authority_unconfirmed": ("#fde8e8", "#b42318"), "number_not_in_evidence": ("#fde8e8", "#b42318"),
}
REVIEW_STYLE = {
    "pending": ("#f2f4f7", "#475467"), "accepted": ("#e7f6ec", "#1e7b3c"),
    "edited": ("#e8f0fe", "#1a56c4"), "rejected": ("#fde8e8", "#b42318"),
}

CSS = """
<style>
:root { --brand:#2f5bea; --ink:#101828; --muted:#667085; --line:#eaecf0; --soft:#f7f8fc; }
.stApp { background: var(--soft); }
[data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
[data-testid="stSidebar"] [data-testid="stElementToolbar"] { display:none; }
.block-container { padding-top: 1.6rem; max-width: 1500px; }
.crumb { color:var(--muted); font-size:.85rem; margin-bottom:.2rem; }
.crumb b { color:var(--ink); }
.title { font-size:1.6rem; font-weight:700; color:var(--ink); margin:0 0 .3rem 0; }
.meta-line { color:var(--muted); font-size:.9rem; display:flex; gap:1.2rem; flex-wrap:wrap; align-items:center; }
.chip { background:#eef2ff; color:#3a4ed8; border-radius:999px; padding:.1rem .65rem; font-size:.78rem; }
.card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:1rem 1.1rem; min-height:122px; }
.stat { display:flex; gap:.8rem; align-items:flex-start; }
.stat-ico { flex:0 0 44px; width:44px; height:44px; border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:20px; }
.stat-label { font-weight:600; color:var(--ink); font-size:.92rem; }
.stat-num { font-size:1.7rem; font-weight:700; color:var(--ink); line-height:1.2; }
.stat-sub { color:var(--muted); font-size:.78rem; }
.badge { display:inline-block; border-radius:999px; padding:.08rem .55rem; font-size:.74rem; font-weight:600;
  margin:0 .2rem .2rem 0; white-space:nowrap; line-height:1.35; }
.cite { color:var(--brand); font-size:.82rem; }
.group-head { font-weight:700; color:var(--ink); font-size:1rem; }
.count-pill { background:#eef2ff; color:#3a4ed8; border-radius:999px; padding:0 .5rem; font-size:.75rem; margin-left:.4rem; }
.row-content { color:var(--ink); font-size:.92rem; }
.row-topic { color:var(--muted); font-size:.85rem; }
.rejected { text-decoration: line-through; color:#98a2b3 !important; }
.quote { border-left:3px solid var(--brand); background:#f5f7ff; padding:.5rem .8rem; border-radius:6px; margin:.35rem 0; }
.quote small { color:var(--muted); }
.tl { border-left:2px solid var(--line); margin-left:.4rem; padding-left:1rem; }
.tl-item { position:relative; margin-bottom:.7rem; }
.tl-item:before { content:""; position:absolute; left:-1.42rem; top:.35rem; width:10px; height:10px; border-radius:50%;
  background:var(--brand); }
.side-card { background:linear-gradient(135deg,#eef3ff,#f7f9ff); border:1px solid #dfe6ff; border-radius:14px;
  padding:1rem; color:#2443b8; font-size:.85rem; }
.panel-title { font-weight:700; color:var(--ink); font-size:1.05rem; }
.muted { color:var(--muted); font-size:.85rem; }
/* item tables: one bordered grid per group */
[class*="st-key-tbl-"] { gap:0 !important; border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#fff; }
[class*="st-key-thead-"] { background:#f4f6fb; }
[class*="st-key-trow-"] { border-top:1px solid #e4e7ee; }
[class*="st-key-trow-"]:hover { background:#f8faff; }
[class*="st-key-thead-"] [data-testid="stHorizontalBlock"],
[class*="st-key-trow-"] [data-testid="stHorizontalBlock"] { gap:0 !important; align-items:stretch; }
[class*="st-key-thead-"] [data-testid="stColumn"],
[class*="st-key-trow-"] [data-testid="stColumn"] { padding:.55rem .5rem; min-width:0; height:auto; }
[class*="st-key-thead-"] [data-testid="stColumn"] + [data-testid="stColumn"],
[class*="st-key-trow-"] [data-testid="stColumn"] + [data-testid="stColumn"] { border-left:1px solid var(--line); }
[class*="st-key-trow-"] [data-testid="stColumn"] > div { height:auto !important; }
[class*="st-key-tbl-"] [data-testid="stMarkdownContainer"] p { margin-bottom:0; }
[class*="st-key-trow-"] [data-testid="stColumn"] { padding-bottom:.8rem !important; }
.th { color:#475467; font-weight:700; font-size:.8rem; white-space:nowrap; }
[class*="st-key-trow-"] .row-content, [class*="st-key-trow-"] .row-topic { font-size:.86rem; display:block; line-height:1.5; }
.badge.wrap { white-space:normal; }
.quote.ctx { border-left-color:#d0d5dd; background:#fafafa; color:#98a2b3; font-size:.85rem; padding:.25rem .8rem; }
.quote.ctx small { color:#98a2b3; }
.warn-small { color:#b45f06; font-size:.78rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers


def badge(text: str, colors: tuple[str, str], wrap: bool = False) -> str:
    bg, fg = colors
    cls = "badge wrap" if wrap else "badge"
    return f'<span class="{cls}" style="background:{bg};color:{fg}">{md_safe(text)}</span>'


def status_badge(item: Item) -> str:
    if not item.status:
        return ""
    return badge(STATUS_LABELS.get(item.status.value, item.status.value), STATUS_STYLE.get(item.status.value, ("#eee", "#333")))


LOW_NOTE_STYLE = ("#f2f4f7", "#667085")


def _one_flag_badge(flag: str) -> str:
    return badge(FLAG_LABELS.get(flag, flag), FLAG_STYLE.get(flag, ("#eee", "#333")), wrap=True)


def flag_badges(item: Item, collapse_low: bool = True) -> str:
    """High-level flags as badges; low-level ones collapse into one faint '+n ghi chú' badge."""
    high, low = split_flags(item.flags)
    if not collapse_low:
        return "".join(_one_flag_badge(f) for f in item.flags)
    out = "".join(_one_flag_badge(f) for f in high)
    if low:
        out += badge(f"+{len(low)} ghi chú", LOW_NOTE_STYLE, wrap=True)
    return out


def esc(text: Any) -> str:
    return md_safe(str(text)) if text not in (None, "") else "—"


def list_runs() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted((p for p in RUNS_DIR.iterdir() if (p / "result.json").exists()), reverse=True)


@st.cache_data(show_spinner=False)
def _load_result_cached(path: str, mtime: float) -> RunResult:
    return load_result(path)


def get_result(run_dir: Path) -> RunResult:
    return _load_result_cached(str(run_dir), (run_dir / "result.json").stat().st_mtime)


def run_title(run_dir: Path) -> tuple[str, str]:
    try:
        r = get_result(run_dir)
    except Exception:  # corrupted run folder – still list it
        return run_dir.name, ""
    title = (r.meta.title if r.meta and r.meta.title else None) or Path(r.source_file).name
    when = ""
    if r.meta and (r.meta.date or r.meta.start_time):
        when = " ".join(x for x in [r.meta.start_time and f"{r.meta.start_time}–{r.meta.end_time or ''}", r.meta.date] if x)
    else:
        when = f"{run_dir.name[6:8]}/{run_dir.name[4:6]}/{run_dir.name[:4]} {run_dir.name[9:11]}:{run_dir.name[11:13]}"
    return title, when


def open_run(run_dir: Path) -> None:
    st.session_state.run_dir = str(run_dir)
    st.session_state.page = "run"


def get_reviews(run_dir: Path) -> dict[str, Any]:
    key = f"reviews::{run_dir}"
    if key not in st.session_state:
        st.session_state[key] = load_reviews(run_dir)
    return st.session_state[key]


def persist_reviews(run_dir: Path, reviews: dict[str, Any]) -> None:
    st.session_state[f"reviews::{run_dir}"] = reviews
    save_reviews(run_dir, reviews)


def set_review(run_dir: Path, item_id: str, review: str, edits: dict[str, Any] | None = None) -> None:
    reviews = get_reviews(run_dir)
    entry = dict(reviews["items"].get(item_id, {}))
    if edits:
        entry.update(edits)
    entry["review"] = review
    reviews["items"][item_id] = entry
    persist_reviews(run_dir, reviews)


# ---------------------------------------------------------------- confidence explanation (pure helpers)

TEXT_EXTENSIONS = (".txt", ".vtt")
AUDIO_UPLOAD_EXTENSIONS = (".mp3", ".m4a", ".wav", ".mp4")
LOW_CONFIDENCE = 0.7
POS_COLOR, NEG_COLOR, CAP_COLOR = "#1e7b3c", "#b42318", "#b45f06"
# breakdown key -> Vietnamese label for regular terms
TERM_LABELS = {
    "closing_explicit": "câu chốt rõ", "closing_implicit": "câu chốt ngầm", "closing_none": "không có câu chốt",
    "evidence_inferred": "bằng chứng suy luận", "closer_can_decide": "người chốt có quyền",
    "closer_unknown": "người chốt không có quyền hoặc chưa xác định", "verify_passed": "kiểm chứng đạt",
    "verify_failed": "kiểm chứng không đạt", "multi_evidence": "nhiều câu bằng chứng",
    "contradicted_later": "bị phản bác sau đó", "noisy_evidence": "ghi âm không rõ",
    "in_summary": "được nhắc trong câu tóm lại",
    "signal_strong_conflict": "lệch tín hiệu code (mạnh)", "signal_weak_conflict": "lệch tín hiệu code (nhẹ)",
    "signal_reversal_penalty": "có câu đảo ý ngay sau câu chốt",
    "number_not_in_evidence_penalty": "số không có trong câu gốc",
}
# keys that are limits (caps / clamp), not terms of the sum
CAP_LABELS = {
    "cap_authority": "trần: chưa rõ thẩm quyền", "cap_verify_failed": "trần: kiểm chứng không đạt",
    "cap_tracker_failed": "trần: chủ đề lỗi khi phân tích",
    "cap_signal_unverified": "trần: code không thấy từ chốt",
    "cap_signal_short_ack": "trần: câu chốt chỉ là lời đồng ý ngắn",
    "cap_possible_action": "trần: có thể là việc cần làm",
    "cap_possible_superseded": "trần: có thể đã bị thay thế",
    "cap_superseded_sibling": "trần: có quyết định khác thay thế cùng vấn đề", "clamp": "giới hạn thang điểm",
}


def fmt_num(value: float, signed: bool = False) -> str:
    """0.72 -> '0,72'; with signed=True: '+0,20' / '−0,15' (typographic minus)."""
    text = f"{abs(value):.2f}".replace(".", ",")
    if not signed:
        return f"-{text}" if value < 0 else text
    return f"{'−' if value < 0 else '+'}{text}"


def base_label(item: Item) -> str:
    return f"nền ({TYPE_LABEL[item.type].lower()})"


def confidence_terms(item: Item) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """Split the breakdown into (regular terms, limits) with Vietnamese labels. Base comes first."""
    terms: list[tuple[str, float]] = []
    caps: list[tuple[str, float]] = []
    for key, value in item.confidence_breakdown.items():
        if key == "base":
            terms.insert(0, (base_label(item), value))
        elif key in CAP_LABELS:
            caps.append((CAP_LABELS[key], value))
        else:
            terms.append((TERM_LABELS.get(key, key), value))
    return terms, caps


def _term_html(label: str, value: float, first: bool) -> str:
    color = POS_COLOR if value >= 0 else NEG_COLOR
    num = fmt_num(value) if first else fmt_num(value, signed=True)
    return f'<span style="color:{color};font-weight:600">{num}</span> {md_safe(label)}'


def confidence_explanation_html(item: Item) -> str | None:
    """HTML explaining how the confidence was computed; None for old runs without a breakdown."""
    if not item.confidence_breakdown:
        return None
    terms, caps = confidence_terms(item)
    parts = " ".join(_term_html(label, value, n == 0) for n, (label, value) in enumerate(terms))
    lines = [f"<b>{fmt_num(item.confidence)}</b> = {parts}"]
    for label, value in caps:
        lines.append(f'<span style="color:{CAP_COLOR};font-weight:600">Giới hạn áp dụng: {md_safe(label)} '
                     f"({fmt_num(value, signed=True)})</span>")
    return "<br>".join(lines)


# ---------------------------------------------------------------- audio playback (pure helpers)


class AudioClip(NamedTuple):
    path: Path
    start: float
    end: float
    exists: bool


def wants_audio(item: Item) -> bool:
    return "number_check" in item.flags or item.confidence < LOW_CONFIDENCE


def audio_clip_for(item: Item, result: RunResult, run_dir: Path) -> AudioClip | None:
    """Clip to replay for an item, or None when there is no audio / no reason to listen / no timestamp."""
    if not result.audio_path or not wants_audio(item):
        return None
    by_id = {u.id: u for u in result.utterances}
    utt = next((by_id[e] for e in item.evidence if e in by_id and by_id[e].start_sec is not None), None)
    if utt is None:
        return None
    start, end = clip_range(utt)
    path = run_dir / Path(result.audio_path).name  # file name only: never leave the run folder
    return AudioClip(path, start, end, path.is_file())


def render_audio_player(clip: AudioClip) -> None:
    st.markdown("**Nghe lại đoạn ghi âm**")
    if not clip.exists:
        st.caption("File ghi âm không còn trong thư mục chạy (ví dụ ứng dụng được chạy lại trên máy khác), "
                   "không thể phát lại.")
        return
    st.audio(str(clip.path), start_time=int(clip.start), end_time=int(clip.end) + 1)
    st.caption(f"Đang phát từ {format_time(clip.start)}")


# ---------------------------------------------------------------- sidebar


def sidebar() -> None:
    with st.sidebar:
        st.image(str(LOGO), width="stretch")
        if st.button("🏠  Trang chủ – Phân tích mới", use_container_width=True,
                     type="primary" if st.session_state.page == "new" else "secondary"):
            st.session_state.page = "new"
            st.rerun()
        if st.button("📋  Tất cả cuộc họp", use_container_width=True,
                     type="primary" if st.session_state.page == "all" else "secondary"):
            st.session_state.page = "all"
            st.rerun()

        runs = list_runs()
        if runs:
            st.caption("Gần đây")
            for run_dir in runs[:5]:
                title, when = run_title(run_dir)
                active = st.session_state.get("run_dir") == str(run_dir) and st.session_state.page == "run"
                if st.button(f"🗓️ {title}\n\n{when}", key=f"recent-{run_dir.name}", use_container_width=True,
                             type="primary" if active else "secondary"):
                    open_run(run_dir)
                    st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            '<div class="side-card"><b>AI hỗ trợ, con người quyết định</b><br>'
            "AI chỉ đề xuất. Mọi mục cần được duyệt trước khi xuất biên bản.</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Model: {SETTINGS.model_light} / {SETTINGS.model_strong}")


# ---------------------------------------------------------------- new analysis page


def _meta_defaults() -> dict[str, Any]:
    return st.session_state.setdefault("meta_form", {
        "title": "", "date": date.today(), "start": time(9, 0), "end": time(10, 0), "project": "",
        "agenda": "", "participants": pd.DataFrame([{"name": "", "role": "", "can_decide": False}]),
    })


def _prefill_from_meta(meta: MeetingMeta) -> None:
    form = _meta_defaults()
    form["title"] = meta.title or ""
    form["project"] = meta.project or ""
    form["agenda"] = "\n".join(meta.agenda)
    if meta.date:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                form["date"] = datetime.strptime(meta.date, fmt).date()
                break
            except ValueError:
                continue
    try:
        if meta.start_time:
            form["start"] = datetime.strptime(meta.start_time, "%H:%M").time()
        if meta.end_time:
            form["end"] = datetime.strptime(meta.end_time, "%H:%M").time()
    except ValueError:
        pass  # free-text date/time in meta: keep form defaults
    if meta.participants:
        form["participants"] = pd.DataFrame([p.model_dump() for p in meta.participants])
    form["version"] = form.get("version", 0) + 1


def meeting_info_form() -> MeetingMeta | None:
    """Right-hand panel: meeting information (optional)."""
    form = _meta_defaults()
    v = form.get("version", 0)
    st.markdown('<div class="panel-title">📝 Thông tin cuộc họp</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted">Tùy chọn – giúp chia chủ đề theo chương trình và kiểm tra thẩm quyền chốt.</div>',
                unsafe_allow_html=True)
    meta_file = st.file_uploader("Nạp từ meeting_meta.json", type=["json"], key="meta_upload")
    if meta_file is not None and st.session_state.get("meta_loaded") != meta_file.file_id:
        try:
            _prefill_from_meta(MeetingMeta.model_validate(json.loads(meta_file.getvalue().decode("utf-8-sig"))))
            st.session_state.meta_loaded = meta_file.file_id
            st.rerun()
        except Exception as exc:  # show the parse error to the user
            st.error(f"File meta không hợp lệ: {exc}")

    use_meta = st.toggle("Dùng thông tin cuộc họp", value=True)
    title = st.text_input("Tiêu đề cuộc họp", form["title"], key=f"title{v}", placeholder="Họp triển khai dự án AI – Tuần 3")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    d = c1.date_input("Ngày họp", form["date"], format="DD/MM/YYYY", key=f"date{v}")
    start = c2.time_input("Bắt đầu", form["start"], key=f"start{v}", step=300)
    end = c3.time_input("Kết thúc", form["end"], key=f"end{v}", step=300)
    project = st.text_input("Dự án", form["project"], key=f"project{v}", placeholder="Dự án AI")
    agenda = st.text_area("Chương trình họp (mỗi dòng một mục)", form["agenda"], key=f"agenda{v}", height=90,
                          placeholder="Chọn hạ tầng\nLịch ra mắt beta")
    st.markdown("**Người tham dự**")
    people = st.data_editor(
        form["participants"], key=f"people{v}", num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("Tên", required=True),
            "role": st.column_config.TextColumn("Vai trò"),
            "can_decide": st.column_config.CheckboxColumn("Quyền chốt", default=False),
        },
    )
    if not use_meta:
        return None
    participants = [
        Participant(name=str(r["name"]).strip(), role=(str(r["role"]).strip() or None) if pd.notna(r["role"]) else None,
                    can_decide=bool(r["can_decide"]) if pd.notna(r["can_decide"]) else False)
        for _, r in people.iterrows() if pd.notna(r["name"]) and str(r["name"]).strip()
    ]
    return MeetingMeta(
        title=title.strip() or None, date=d.strftime("%d/%m/%Y") if d else None,
        start_time=start.strftime("%H:%M") if start else None, end_time=end.strftime("%H:%M") if end else None,
        project=project.strip() or None, agenda=[a.strip() for a in agenda.splitlines() if a.strip()],
        participants=participants,
    )


def page_new() -> None:
    st.markdown('<div class="crumb">Trang chủ › <b>Phân tích cuộc họp mới</b></div>', unsafe_allow_html=True)
    st.markdown('<div class="title">Phân tích cuộc họp mới</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted">Tải transcript, điền thông tin cuộc họp rồi bấm <b>Phân tích</b>. '
                "Hệ thống chạy 4 agent: Chia chủ đề → Trích xuất → Theo dõi quyết định → Kiểm chứng.</div>",
                unsafe_allow_html=True)
    st.write("")
    left, right = st.columns([1.55, 1], gap="large")
    with right, st.container(border=True):
        meta = meeting_info_form()
    with left:
        with st.container(border=True):
            st.markdown('<div class="panel-title">📄 Transcript</div>', unsafe_allow_html=True)
            st.markdown('<div class="muted">Định dạng .txt mỗi dòng <code>[mm:ss] Tên: nội dung</code>, .vtt, '
                        "hoặc file ghi âm .mp3 / .m4a / .wav / .mp4 (tối đa 25 MB). Chỉ chọn một file.</div>",
                        unsafe_allow_html=True)
            exts = [e.lstrip(".") for e in TEXT_EXTENSIONS + AUDIO_UPLOAD_EXTENSIONS]
            upload = st.file_uploader("Tải transcript hoặc ghi âm", type=exts, label_visibility="collapsed")
            if upload is not None and Path(upload.name).suffix.lower() in AUDIO_UPLOAD_EXTENSIONS:
                audio_section(upload, meta)
                return
            text, name = "", ""
            if upload is not None:
                text, name = upload.getvalue().decode("utf-8-sig"), upload.name
            utts, warns = parse_text(text, Path(name).suffix or ".txt") if text else ([], [])
            if text:
                speakers = sorted({u.speaker for u in utts})
                st.success(f"Đọc được {len(utts)} câu, {len(speakers)} người nói: {', '.join(speakers)}")
                for w in warns:
                    st.warning(w)
                with st.expander("Xem trước transcript", expanded=False):
                    st.dataframe(pd.DataFrame([u.model_dump() for u in utts]), hide_index=True,
                                 use_container_width=True, height=280)
            go = st.button("🔍  Phân tích", type="primary", disabled=not utts, use_container_width=True)
        if go:
            analyze(text, name, meta)


def audio_section(upload: Any, meta: MeetingMeta | None) -> None:
    """Audio upload: validate size/format locally (no API call), then speech-to-text + pipeline."""
    problem = audio_upload_problem(upload.size)  # size is known before anything touches the disk
    if problem:
        st.error(problem)
        st.button("🔍  Phân tích", type="primary", disabled=True, use_container_width=True)
        return
    st.success(f"Nhận file ghi âm {upload.name} ({upload.size / 1024 / 1024:.1f} MB).")
    st.caption("Hệ thống sẽ chuyển giọng nói thành văn bản (có tách người nói) rồi phân tích như transcript. "
               "Chi phí chuyển giọng nói tính theo thời lượng ghi âm.")
    if st.button("🔍  Phân tích", type="primary", use_container_width=True):
        analyze_with(lambda progress: _run_audio_upload(upload, meta, progress))


def audio_upload_problem(size: int) -> str | None:
    """Vietnamese error when the upload is too large (checked from upload.size, before writing to disk)."""
    limit = _audio.MAX_AUDIO_BYTES
    if size > limit:
        return (f"File audio quá lớn: {size / 1024 / 1024:.1f} MB (giới hạn {limit // 1024 // 1024} MB). "
                "Hãy nén sang mp3 bitrate thấp (ví dụ 32–64 kbps, mono) hoặc cắt ngắn file rồi thử lại.")
    return None


def _run_audio_upload(upload: Any, meta: MeetingMeta | None, progress: Callable[[str, float], None]) -> RunResult:
    """Write the upload to a temp file only when the user clicks Analyze; always clean up."""
    stem = re.sub(r"[^\w\-]+", "_", Path(upload.name).stem, flags=re.ASCII)[:40].strip("_") or "audio"
    tmp_dir = Path(tempfile.mkdtemp(prefix="meetsync_"))
    try:
        path = tmp_dir / f"{stem}{Path(upload.name).suffix.lower()}"
        path.write_bytes(upload.getvalue())
        check_audio_file(path)
        return _pipeline.run_audio(path, meta, settings=SETTINGS, progress=progress)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def analyze(text: str, name: str, meta: MeetingMeta | None) -> None:
    analyze_with(lambda progress: run_text(text, name, meta, settings=SETTINGS, progress=progress))


def analyze_with(runner: Callable[[Callable[[str, float], None]], RunResult]) -> None:
    bar = st.progress(0.0, text="Bắt đầu…")
    error = ""
    with st.status("Đang phân tích…", expanded=True) as status:
        def progress(msg: str, frac: float) -> None:
            bar.progress(min(frac, 1.0), text=msg)
            st.write(f"• {msg}")

        try:
            result = runner(progress)
        except LLMError as exc:
            status.update(label="Lỗi khi gọi LLM", state="error")
            error = f"{exc}\n\nKiểm tra file `.env` (LLM_PROVIDER, OPENAI_API_KEY, MODEL_LIGHT, MODEL_STRONG)."
        except (ValueError, FileNotFoundError) as exc:
            status.update(label="Đầu vào không hợp lệ", state="error")
            error = str(exc)
        except OSError as exc:
            status.update(label="Lỗi ghi file", state="error")
            error = f"Không ghi được file ghi âm tạm hoặc file kết quả: {exc}. Kiểm tra dung lượng ổ đĩa và quyền ghi."
        else:
            status.update(label=f"Hoàn tất – {len(result.items)} mục", state="complete")
    if error:
        st.error(error)
        return
    open_run(RUNS_DIR / result.run_id)
    st.rerun()


# ---------------------------------------------------------------- all meetings page


def page_all() -> None:
    st.markdown('<div class="crumb">Trang chủ › <b>Tất cả cuộc họp</b></div>', unsafe_allow_html=True)
    st.markdown('<div class="title">Tất cả cuộc họp</div>', unsafe_allow_html=True)
    runs = list_runs()
    if not runs:
        st.info("Chưa có cuộc họp nào được phân tích.")
        return
    for run_dir in runs:
        title, when = run_title(run_dir)
        try:
            r = get_result(run_dir)
        except Exception as exc:
            st.warning(f"{run_dir.name}: không đọc được ({exc})")
            continue
        reviews = load_reviews(run_dir)
        done = sum(1 for v in reviews["items"].values() if v.get("review") in ("accepted", "edited", "rejected"))
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"**{md_safe(title)}**  \n<span class='muted'>{md_safe(when)} · "
                        f"{md_safe(Path(r.source_file).name)}</span>", unsafe_allow_html=True)
            c2.markdown(f"<span class='muted'>{len(r.items)} mục · đã duyệt {done}/{len(r.items)}</span>",
                        unsafe_allow_html=True)
            if c3.button("Mở", key=f"open-{run_dir.name}", use_container_width=True):
                open_run(run_dir)
                st.rerun()


# ---------------------------------------------------------------- run page


def group_items(items: list[Item], types: list[ItemType]) -> list[Item]:
    return [i for i in items if i.type in types]


def stat_cards(items: list[Item]) -> None:
    undecided = sum(1 for i in items if i.type == ItemType.decision and i.status in (Status.open, Status.deferred))
    cols = st.columns(4)
    for col, (key, label, types) in zip(cols, GROUPS):
        n = len(group_items(items, types))
        sub = "đã trích xuất"
        if key == "open" and undecided:
            sub = f"+ {undecided} quyết định chưa chốt/hoãn"
        col.markdown(
            f'<div class="card stat"><div class="stat-ico" style="background:{GROUP_ICONS[key][2]}">{group_icon(key)}</div>'
            f'<div><div class="stat-label">{label}</div><div class="stat-num">{n}</div>'
            f'<div class="stat-sub">{sub}</div></div></div>',
            unsafe_allow_html=True,
        )


def item_table(run_dir: Path, result: RunResult, items: list[Item], kind: str, prefix: str) -> None:
    """Grid table: header band, row and column dividers; the last cell opens the detail dialog."""
    is_action = kind == "action"
    if is_action:
        widths = [0.3, 2.3, 1.1, 0.95, 0.9, 0.95, 1.45, 1.1, 0.45]
        heads = ["#", "Nội dung", "Chủ đề", "Phụ trách", "Hạn chót", "Trích dẫn", "Cờ", "Duyệt", ""]
    else:
        widths = [0.3, 2.5, 1.2, 1.1, 0.95, 1.5, 1.1, 0.45]
        heads = ["#", "Nội dung", "Chủ đề", "Trạng thái", "Trích dẫn", "Cờ", "Duyệt", ""]
    with st.container(key=f"tbl-{prefix}"):
        with st.container(key=f"thead-{prefix}"):
            for c, h in zip(st.columns(widths, gap="small"), heads):
                c.markdown(f"<span class='th'>{h}</span>", unsafe_allow_html=True)
        for n, item in enumerate(items, start=1):
            with st.container(key=f"trow-{prefix}-{item.item_id}"):
                cols = st.columns(widths, gap="small")
                cls = "row-content rejected" if item.review == "rejected" else "row-content"
                conf = f"<br><span class='muted'>tin cậy {fmt_num(item.confidence)}</span>{row_extras(item)}"
                type_tag = "" if kind in ("decision", "action", "open") else f"<span class='muted'>{TYPE_LABEL[item.type]} · </span>"
                cites = "<br>".join(f"#{e}" for e in item.evidence)
                review = badge(REVIEW_LABELS.get(item.review, item.review), REVIEW_STYLE.get(item.review, ("#eee", "#333")))
                dash = "<span class='muted'>—</span>"
                cells = [
                    f"<span class='muted'>{n}</span>",
                    f"<div class='{cls}'>{type_tag}{esc(item.content)}{conf}</div>",
                    f"<span class='row-topic'>{esc(item.topic)}</span>",
                ]
                if is_action:
                    cells += [f"<span class='row-content'>{esc(item.owner)}</span>",
                              f"<span class='row-content'>{esc(item.deadline)}</span>"]
                else:
                    cells.append(status_badge(item) or dash)
                cells += [f"<span class='cite'>{cites}</span>", flag_badges(item) or dash, review]
                for col, html_cell in zip(cols, cells):
                    col.markdown(html_cell, unsafe_allow_html=True)
                if cols[-1].button("", icon=":material/chevron_right:", key=f"open-{prefix}-{item.item_id}",
                                   help="Xem chi tiết & duyệt"):
                    item_dialog(run_dir, result, item.item_id)


def row_extras(item: Item) -> str:
    """Small extra lines under the content cell: commitment label, what an unresolved item waits for."""
    lines: list[str] = []
    if item.commitment in COMMITMENT_LABELS:
        lines.append(f"Cam kết: {COMMITMENT_LABELS[item.commitment]}")
    if item.status in (Status.open, Status.deferred, Status.conditional):
        if item.pending_on:
            lines.append(f"Đang chờ: {item.pending_on}")
        if item.follow_up_owner:
            lines.append(f"Theo dõi: {item.follow_up_owner}")
    return "".join(f"<br><span class='muted'>{md_safe(x)}</span>" for x in lines)


def _utt_line(u: Any, cls: str, body_html: str) -> str:
    return (f"<div class='quote{cls}'><small>{md_safe(u.id)} · {md_safe(u.time)} · "
            f"<b>{md_safe(u.speaker)}</b></small><br>{body_html}</div>")


def evidence_html(item: Item, result: RunResult, uid: str, context: int = 2) -> str | None:
    """One evidence utterance: quote in bold, +-`context` neighbours dimmed. None when the id is unknown."""
    by_id = {u.id: u for u in result.utterances}
    u = by_id.get(uid)
    if u is None:
        return None
    before, after = utterance_context(result.utterances, uid, context)
    body, found = highlight_quote_html(u.text, item.evidence_quotes.get(uid))
    if found is False:
        body += "<br><span class='warn-small'>Không tìm thấy đoạn trích trong câu này.</span>"
    parts = [_utt_line(c, " ctx", md_safe(c.text)) for c in before]
    parts.append(_utt_line(u, "", body))
    parts += [_utt_line(c, " ctx", md_safe(c.text)) for c in after]
    return "".join(parts)


FIELD_SOURCE_LABELS = (("owner", "Phụ trách"), ("deadline", "Hạn chót"), ("condition", "Điều kiện"))


def field_sources_html(item: Item, result: RunResult) -> str:
    """Per-field source sentences (owner / deadline / condition); empty string when none recorded."""
    by_id = {u.id: u for u in result.utterances}
    rows: list[str] = []
    for key, label in FIELD_SOURCE_LABELS:
        for uid in item.field_evidence.get(key, []):
            u = by_id.get(uid)
            if u:
                rows.append(f"<small><b>{label}</b> ← {md_safe(u.id)} · {md_safe(u.time)} "
                            f"{md_safe(u.speaker)}: “{md_safe(u.text)}”</small>")
    return "<br>".join(rows)


def contradicted_html(item: Item, result: RunResult) -> str:
    by_id = {u.id: u for u in result.utterances}
    rows = [f"<small>{md_safe(u.id)} · {md_safe(u.time)} <b>{md_safe(u.speaker)}</b>: "
            f"“{md_safe(u.text)}”</small>"
            for u in (by_id.get(e) for e in item.field_evidence.get("contradicted_by", [])) if u]
    return "<br>".join(rows)


def render_evidence(item: Item, result: RunResult) -> None:
    st.markdown("**Trích dẫn nguyên văn**")
    if "quote_mismatch" in item.flags:
        st.warning("Đoạn trích AI đưa ra không khớp nguyên văn câu gốc. Hãy tự đối chiếu với câu gốc trước khi chấp nhận.")
    shown = False
    for e in item.evidence:
        block = evidence_html(item, result, e)
        if block:
            shown = True
            st.markdown(block, unsafe_allow_html=True)
    if not shown:
        st.caption("Không có câu bằng chứng hợp lệ.")
    sources = field_sources_html(item, result)
    if sources:
        st.markdown("**Nguồn của từng trường**")
        st.markdown(sources, unsafe_allow_html=True)
    against = contradicted_html(item, result)
    if against:
        st.markdown("**Bị phản bác bởi**")
        st.markdown(against, unsafe_allow_html=True)


def code_check_html(item: Item, result: RunResult) -> str:
    """HTML lines for signal_check.notes (note text, plus the quoted utterance when it exists); '' when none."""
    by_id = {u.id: u for u in result.utterances}
    rows: list[str] = []
    for note in signal_notes(item):
        text = note.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        row = f"• {md_safe(text)}"
        u = by_id.get(note.get("utterance"))
        if u:
            row += (f"<br><small>{md_safe(u.id)} · {md_safe(u.time)} <b>{md_safe(u.speaker)}</b>: "
                    f"“{md_safe(u.text)}”</small>")
        rows.append(f"<div style='margin-bottom:.4rem'>{row}</div>")
    return "".join(rows)


def render_code_check(item: Item, result: RunResult) -> None:
    html_rows = code_check_html(item, result)
    if html_rows:
        st.markdown("**Kiểm tra bằng code**")
        st.markdown(html_rows, unsafe_allow_html=True)


def render_related(item: Item, result: RunResult) -> None:
    related = related_summaries(item, result)
    if not related:
        return
    st.markdown("**Mục liên quan**")
    lines = [f"• **{md_safe(rid)}** — {md_safe(text) if ok else '(mục không còn trong kết quả)'}"
             for rid, text, ok in related]
    st.markdown("  \n".join(lines), unsafe_allow_html=True)


@st.dialog("Chi tiết mục", width="large")
def item_dialog(run_dir: Path, result: RunResult, item_id: str) -> None:
    item = next(i for i in result.items if i.item_id == item_id)
    by_id = {u.id: u for u in result.utterances}
    st.markdown(f"**{item.item_id} · {TYPE_LABEL[item.type]}** — {esc(item.topic)}")
    st.markdown(f"### {md_safe(item.content)}", unsafe_allow_html=True)
    high_flags, low_flags = split_flags(item.flags)
    st.markdown(status_badge(item) + "".join(_one_flag_badge(f) for f in high_flags)
                + badge(REVIEW_LABELS.get(item.review, item.review), REVIEW_STYLE[item.review]),
                unsafe_allow_html=True)
    info = []
    if item.condition:
        info.append(f"**Điều kiện:** {md_safe(item.condition)}")
    info.append(f"**Phụ trách:** {md_safe(item.owner or '—')}  ·  **Hạn chót:** {md_safe(item.deadline or '—')}  ·  "
                f"**Độ tin cậy:** {fmt_num(item.confidence)}")
    if item.commitment in COMMITMENT_LABELS:
        info.append(f"**Cam kết:** {COMMITMENT_LABELS[item.commitment]}")
    if item.pending_on:
        info.append(f"**Đang chờ:** {md_safe(item.pending_on)}")
    if item.follow_up_owner:
        info.append(f"**Người theo dõi:** {md_safe(item.follow_up_owner)}")
    st.markdown("  \n".join(info))
    explanation = confidence_explanation_html(item)
    if explanation:
        with st.expander("Vì sao độ tin cậy là " + fmt_num(item.confidence) + "?", expanded=True):
            st.markdown(explanation, unsafe_allow_html=True)
    else:
        st.caption("Độ tin cậy: chưa có phân tích chi tiết (kết quả chạy trước khi có tính năng này).")
    if low_flags:
        with st.expander(f"Ghi chú khác ({len(low_flags)})"):
            st.markdown("".join(_one_flag_badge(f) for f in low_flags), unsafe_allow_html=True)
    render_code_check(item, result)
    clip = audio_clip_for(item, result, run_dir)
    if clip:
        render_audio_player(clip)

    render_evidence(item, result)
    render_related(item, result)
    if item.history:
        st.markdown("**Lịch sử thay đổi**")
        rows = []
        for h in item.history:
            quotes = "<br>".join(f"<small>{by_id[e].time} {md_safe(by_id[e].speaker)}: “{md_safe(by_id[e].text)}”</small>"
                                 for e in h.evidence if e in by_id)
            reason = f" — <i>{md_safe(h.reason)}</i>" if h.reason else ""
            rows.append(f"<div class='tl-item'>{badge(STATUS_LABELS.get(h.status.value, h.status.value), STATUS_STYLE.get(h.status.value, ('#eee', '#333')))}"
                        f" {esc(h.content)}{reason}<br>{quotes}</div>")
        st.markdown(f"<div class='tl'>{''.join(rows)}</div>", unsafe_allow_html=True)

    st.divider()
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ Chấp nhận", use_container_width=True, type="primary"):
        set_review(run_dir, item_id, "accepted")
        st.rerun()
    if c2.button("🗑️ Loại", use_container_width=True):
        set_review(run_dir, item_id, "rejected")
        st.rerun()
    if c3.button("↺ Đặt lại", use_container_width=True):
        reviews = get_reviews(run_dir)
        reviews["items"].pop(item_id, None)
        persist_reviews(run_dir, reviews)
        st.rerun()
    with st.expander("✏️ Sửa mục này", expanded=False), st.form(f"edit-{item_id}"):
        content = st.text_area("Nội dung", item.content)
        statuses = [""] + [s.value for s in Status]
        status = st.selectbox("Trạng thái", statuses,
                              index=statuses.index(item.status.value) if item.status else 0,
                              format_func=lambda s: STATUS_LABELS.get(s, "(không có)"))
        condition = st.text_input("Điều kiện", item.condition or "")
        e1, e2 = st.columns(2)
        owner = e1.text_input("Người phụ trách", item.owner or "")
        deadline = e2.text_input("Hạn chót", item.deadline or "")
        e3, e4 = st.columns(2)
        pending_on = e3.text_input("Đang chờ", item.pending_on or "")
        follow_up = e4.text_input("Người theo dõi", item.follow_up_owner or "")
        if st.form_submit_button("Lưu chỉnh sửa", type="primary"):
            set_review(run_dir, item_id, "edited", {
                "content": content.strip(), "status": status or None, "condition": condition.strip() or None,
                "owner": owner.strip() or None, "deadline": deadline.strip() or None,
                "pending_on": pending_on.strip() or None, "follow_up_owner": follow_up.strip() or None,
            })
            st.rerun()


def meeting_panel(run_dir: Path, raw: RunResult, result: RunResult, reviews: dict[str, Any]) -> None:
    meta = result.meta
    st.markdown('<div class="panel-title">📝 Thông tin cuộc họp</div>', unsafe_allow_html=True)
    rows = [
        ("Tiêu đề", meta.title if meta else None),
        ("Ngày", meta.date if meta else None),
        ("Thời gian", f"{meta.start_time or ''} – {meta.end_time or ''}" if meta and meta.start_time else None),
        ("Dự án", meta.project if meta else None),
        ("File", Path(result.source_file).name),
    ]
    st.markdown("  \n".join(f"**{k}:** {md_safe(str(v)) if v else '—'}" for k, v in rows))
    if meta and meta.agenda:
        st.markdown("**Chương trình:**  \n" + "  \n".join(f"• {md_safe(a)}" for a in meta.agenda))
    if meta and meta.participants:
        st.dataframe(pd.DataFrame([{"Tên": p.name, "Vai trò": p.role or "", "Chốt": p.can_decide}
                                   for p in meta.participants]), hide_index=True, use_container_width=True,
                     column_config={"Tên": st.column_config.TextColumn(width=62),
                                    "Vai trò": st.column_config.TextColumn(width=104),
                                    "Chốt": st.column_config.CheckboxColumn(width=46, help="Có quyền chốt")})
    else:
        st.caption("Không có danh sách người tham dự – hệ thống không kiểm tra thẩm quyền chốt.")

    anon = sorted({u.speaker for u in raw.utterances if is_anonymous_speaker(u.speaker)})
    if anon:
        st.markdown('<div class="panel-title">👤 Gán tên người nói</div>', unsafe_allow_html=True)
        st.caption("Áp dụng một lần cho toàn bộ transcript và các mục.")
        with st.form("speaker-names"):
            names = {s: st.text_input(s, reviews["speaker_names"].get(s, ""), key=f"spk-{s}") for s in anon}
            if st.form_submit_button("Lưu tên"):
                reviews["speaker_names"] = {k: v.strip() for k, v in names.items() if v.strip()}
                persist_reviews(run_dir, reviews)
                st.rerun()

    st.markdown('<div class="panel-title">📊 Tiến độ duyệt</div>', unsafe_allow_html=True)
    counts = {k: sum(1 for i in result.items if i.review == k) for k in REVIEW_LABELS}
    total = max(len(result.items), 1)
    st.progress((total - counts["pending"]) / total if result.items else 0.0,
                text=f"Đã duyệt {len(result.items) - counts['pending']}/{len(result.items)}")
    st.markdown(" ".join(badge(f"{REVIEW_LABELS[k]}: {v}", REVIEW_STYLE[k]) for k, v in counts.items()),
                unsafe_allow_html=True)
    if result.warnings:
        with st.expander(f"⚠️ Cảnh báo ({len(result.warnings)})"):
            for w in result.warnings:
                st.caption(w)
    with st.expander("🔧 Thông tin kỹ thuật"):
        st.caption(f"Run ID: {result.run_id}")
        st.caption(f"Model: {result.model_light} / {result.model_strong}")
        st.json(result.prompt_versions, expanded=False)


SIGNAL_WARNING_PREFIX = "[Cảnh báo cờ]"


def signal_run_warnings(result: RunResult) -> list[str]:
    return [w for w in result.warnings if w.startswith(SIGNAL_WARNING_PREFIX)]


def failed_topics_banner(run_dir: Path, result: RunResult) -> bool:
    """Show a red error for topics that failed; return True when quick-approve may be used."""
    if not result.failed_topics:
        return True
    titles = {t.topic_id: t.title for t in result.topics}
    names = ", ".join(f"“{titles.get(tid, tid)}”" for tid in result.failed_topics)
    st.error(
        f"**Một số chủ đề bị lỗi khi phân tích:** {names}.\n\n"
        "Kết quả có thể thiếu hoặc chưa đầy đủ ở các chủ đề này (mục chỉ mang tính tham khảo, "
        "chưa có trạng thái quyết định đã được kiểm chứng). Hãy đọc lại phần transcript tương ứng "
        "hoặc chạy phân tích lại."
    )
    return st.checkbox("Tôi đã đọc cảnh báo và hiểu kết quả có thể thiếu", key=f"failed-ack::{run_dir}")


def qa_history(run_dir: Path) -> list[dict[str, Any]]:
    """Q&A history lives in session_state per run, so meetings never mix."""
    return st.session_state.setdefault(f"qa::{run_dir}", [])


def render_qa_entry(entry: dict[str, Any], result: RunResult) -> None:
    st.markdown(f"**Hỏi:** {md_safe(entry['question'])}", unsafe_allow_html=True)
    if entry.get("error"):
        st.error(entry["error"])
        return
    answer = _qa.QAAnswer.model_validate(entry["answer"])
    if answer.warning:
        st.warning(answer.warning)
    if answer.out_of_scope:
        st.info(answer.text or _qa.OUT_OF_SCOPE_TEXT)
        return
    st.markdown(f"**Trả lời:** {md_safe(answer.text)}", unsafe_allow_html=True)
    by_id = {u.id: u for u in result.utterances}
    for e in answer.evidence:
        u = by_id.get(e)
        if u:
            st.markdown(f"<div class='quote'><small>{u.id} · {u.time} · <b>{md_safe(u.speaker)}</b></small>"
                        f"<br>{md_safe(u.text)}</div>", unsafe_allow_html=True)


def ask_question(question: str, result: RunResult) -> dict[str, Any]:
    """Call the Q&A module; failures become a Vietnamese error entry instead of a crash."""
    try:
        answer = _qa.answer(question, result, make_llm(SETTINGS), SETTINGS)
    except LLMError as exc:
        return {"question": question, "error": f"Không trả lời được câu hỏi: {exc}"}
    return {"question": question, "answer": answer.model_dump()}


def qa_tab(run_dir: Path, result: RunResult) -> None:
    st.caption("Hỏi về cuộc họp này. Chỉ các mục đã Chấp nhận / Đã sửa được dùng làm căn cứ, "
               "kèm nguyên văn câu bằng chứng. Mỗi câu hỏi gọi AI, ước tính ~$0,01–0,02 với cuộc họp ~140 câu.")
    history = qa_history(run_dir)
    with st.form(f"qa-form::{run_dir}", clear_on_submit=True):
        question = st.text_area("Câu hỏi", placeholder="Ví dụ: Ai phụ trách tài liệu API và hạn là khi nào?", height=80)
        sent = st.form_submit_button("Gửi câu hỏi", type="primary")
    if sent and question.strip():
        history.append(ask_question(question.strip(), result))
    for entry in reversed(history):
        with st.container(border=True):
            render_qa_entry(entry, result)


REASON_BADGES = {
    "missing_owner": "Thiếu người phụ trách", "unresolved_reference": "Tham chiếu chưa rõ",
    "conflicting_decision": "Quyết định mâu thuẫn", "needs_recheck": "Cần kiểm tra lại",
    "quote_mismatch": "Trích dẫn không khớp", "no_follow_up": "Chưa có người theo dõi",
    "signal_mismatch": "Lệch tín hiệu code/AI", "possible_action": "Có thể là việc cần làm",
    "possible_closing": "Có thể đã chốt", "possible_superseded": "Có thể đã bị thay thế",
    "authority_unconfirmed": "Người chốt chưa được xác nhận", "number_not_in_evidence": "Số không có trong câu gốc",
}


def clarify_tab(run_dir: Path, result: RunResult, reviews: dict[str, Any]) -> None:
    entries = clarification_items(result, reviews)
    if not entries:
        st.info("Không có mục nào cần làm rõ.")
        return
    by_id = {i.item_id: i for i in result.items}
    open_count = sum(1 for c in entries if not c.answered)
    st.caption(f"{open_count}/{len(entries)} câu hỏi chưa được trả lời. Câu hỏi sinh theo mẫu, không dùng AI; "
               "câu trả lời được lưu như chỉnh sửa của người duyệt.")
    for c in entries:
        item = by_id[c.item_id]
        key = f"{c.item_id}-{c.reason}"
        with st.container(border=True, key=f"clarify-{key}"):
            st.markdown(f"**{md_safe(item.item_id)}** · {badge(REASON_BADGES.get(c.reason, c.reason), ('#fff3e0', '#b45f06'))}"
                        f" {md_safe(item.content)}", unsafe_allow_html=True)
            st.markdown(f"❓ {md_safe(c.question)}", unsafe_allow_html=True)
            if c.answered:
                st.caption(f"Đã trả lời: {md_safe(c.answered)}")
            with st.form(f"clarify-form-{key}", clear_on_submit=True):
                answer = st.text_input("Trả lời", key=f"clarify-answer-{key}", label_visibility="collapsed",
                                       placeholder="Nhập câu trả lời ngắn")
                if st.form_submit_button("Lưu trả lời", key=f"clarify-submit-{key}") and answer.strip():
                    existing = get_reviews(run_dir)["items"].get(c.item_id, {})
                    # only answers that set a real field count as an edit; notes keep the review state
                    review = "edited" if c.answer_field != "note" else existing.get("review", item.review)
                    set_review(run_dir, c.item_id, review, answer_edits(existing, c, answer))
                    st.rerun()
            if st.button("Đã làm rõ", key=f"clarify-resolve-{key}", help="Ẩn câu hỏi này khỏi danh sách"):
                existing = get_reviews(run_dir)["items"].get(c.item_id, {})
                set_review(run_dir, c.item_id, existing.get("review", item.review), resolve_edits(existing, c.reason))
                st.rerun()


def knowledge_tab(result: RunResult, run_dir: Path) -> None:
    entries = knowledge_entries(result)
    unlabeled = sum(1 for i in result.items if i.type == ItemType.knowledge and not i.knowledge_scope)
    if unlabeled:
        st.caption(f"{unlabeled} mục tri thức chưa có nhãn phạm vi (kết quả chạy trước khi có tính năng này) "
                   "nên chưa vào kho.")
    if not entries:
        st.info("Chưa có tri thức nào thuộc phạm vi dự án hoặc dùng lại nhiều lần.")
        return
    st.download_button("⬇ knowledge.json", knowledge_to_json(result), file_name=f"{run_dir.name}.knowledge.json",
                       mime="application/json")
    rows = []
    for e in entries:
        src = e["source"]
        rows.append({
            "ID": e["item_id"], "Nội dung": e["content"], "Phạm vi": e["scope_label"],
            "Cần kiểm tra lại": "Có" if e["needs_recheck"] else "",
            "Nguồn": " · ".join(x for x in [src["meeting"], src["date"]] if x),
            "Câu nguồn": "\n".join(f"{u['id']} [{u['time']}] {u['speaker']}: {u['text']}" for u in src["utterances"]),
            "Duyệt": REVIEW_LABELS.get(e["review"], e["review"]),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def page_run() -> None:
    run_dir = Path(st.session_state.run_dir)
    if not (run_dir / "result.json").exists():
        st.session_state.page = "new"
        st.rerun()
    raw = get_result(run_dir)
    reviews = get_reviews(run_dir)
    result = apply_reviews(raw, reviews)
    meta = result.meta
    title = (meta.title if meta and meta.title else None) or Path(result.source_file).name

    main, side = st.columns([2.55, 1], gap="large")
    with main:
        st.markdown(f'<div class="crumb">Tất cả cuộc họp › <b>{md_safe(title)}</b></div>'
                    f'<div class="title">{md_safe(title)}</div>', unsafe_allow_html=True)
        parts = []
        if meta and (meta.start_time or meta.date):
            parts.append(f"🗓️ {md_safe(' – '.join(x for x in [meta.start_time, meta.end_time] if x))}"
                         f"{', ' + md_safe(meta.date) if meta.date else ''}")
        speakers = {u.speaker for u in result.utterances}
        n_people = len(meta.participants) if meta and meta.participants else len(speakers)
        parts.append(f"👥 {n_people} người tham dự")
        parts.append(f"💬 {len(result.utterances)} câu · {len(result.topics)} chủ đề")
        if meta and meta.project:
            parts.append(f"<span class='chip'>{md_safe(meta.project)}</span>")
        st.markdown(f"<div class='meta-line'>{''.join(f'<span>{p}</span>' for p in parts)}</div>",
                    unsafe_allow_html=True)
        st.write("")
        failed_ack = failed_topics_banner(run_dir, raw)
        for w in signal_run_warnings(raw):
            st.warning(md_safe(w))
        _, a1, a2, a3, a4 = st.columns([2.2, 1, 1, 1, 1.5])
        if a1.button("↻ Tải lại", use_container_width=True):
            st.session_state.pop(f"reviews::{run_dir}", None)
            st.cache_data.clear()
            st.rerun()
        a2.download_button("⬇ JSON", to_json(result), file_name=f"{run_dir.name}.json",
                           mime="application/json", use_container_width=True)
        a3.download_button("⬇ Excel", to_excel(result), file_name=f"{run_dir.name}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True, help="Chỉ gồm các mục đã Chấp nhận / Đã sửa")
        if a4.button("✔ Duyệt nhanh", type="primary", use_container_width=True, disabled=not failed_ack,
                     help="Chấp nhận mọi mục chưa duyệt không có cờ và độ tin cậy ≥ 0,70"):
            for i in result.items:
                if i.review == "pending" and not i.flags and i.confidence >= 0.7:
                    set_review(run_dir, i.item_id, "accepted")
            st.rerun()
        st.write("")
        stat_cards(result.items)
        st.write("")
        tabs = st.tabs(["Tổng quan"] + [g[1] for g in GROUPS] + ["Cần làm rõ", "Kho tri thức", "Hỏi đáp"])
        with tabs[0]:
            st.markdown(f"**Danh sách kết quả** <span class='count-pill'>{len(result.items)} mục</span> "
                        "<span class='muted'>· mục có cờ hoặc độ tin cậy thấp được đưa lên đầu</span>",
                        unsafe_allow_html=True)
            for key, label, types in GROUPS:
                items = group_items(result.items, types)
                if not items:
                    continue
                with st.container(border=True):
                    st.markdown(f"<span class='group-head'>{group_icon(key, 18)}&nbsp; {label} ({len(items)})</span>",
                                unsafe_allow_html=True)
                    item_table(run_dir, result, items, key, f"ov-{key}")
        with tabs[-1]:
            qa_tab(run_dir, result)
        with tabs[-3]:
            clarify_tab(run_dir, result, reviews)
        with tabs[-2]:
            knowledge_tab(result, run_dir)
        for tab, (key, label, types) in zip(tabs[1:1 + len(GROUPS)], GROUPS):
            with tab:
                items = group_items(result.items, types)
                if not items:
                    st.info(f"Không có mục nào thuộc nhóm {label.lower()}.")
                    continue
                with st.container(border=True):
                    item_table(run_dir, result, items, key, f"tab-{key}")
        with st.expander(f"📜 Transcript ({len(result.utterances)} câu)"):
            topic_of = {uid: t.title for t in result.topics for uid in t.utterance_ids}
            st.dataframe(pd.DataFrame([{"ID": u.id, "Thời gian": u.time, "Người nói": u.speaker, "Nội dung": u.text,
                                        "Chủ đề": topic_of.get(u.id, "")} for u in result.utterances]),
                         hide_index=True, use_container_width=True, height=320)
    with side, st.container(border=True):
        meeting_panel(run_dir, raw, result, reviews)


# ---------------------------------------------------------------- main

st.session_state.setdefault("page", "new")
sidebar()
if st.session_state.page == "run" and st.session_state.get("run_dir"):
    page_run()
elif st.session_state.page == "all":
    page_all()
else:
    page_new()
