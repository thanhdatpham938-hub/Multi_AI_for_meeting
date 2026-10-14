"""Streamlit review app.

    streamlit run app/review_app.py
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meeting_extractor.config import load_settings  # noqa: E402
from meeting_extractor.export import (  # noqa: E402
    FLAG_LABELS,
    REVIEW_LABELS,
    STATUS_LABELS,
    apply_reviews,
    load_reviews,
    save_reviews,
    to_excel,
    to_json,
)
from meeting_extractor.llm import LLMError  # noqa: E402
from meeting_extractor.models import Item, ItemType, MeetingMeta, Participant, RunResult, Status  # noqa: E402
from meeting_extractor.parsing import is_anonymous_speaker, parse_text  # noqa: E402
from meeting_extractor.pipeline import load_result, run_text  # noqa: E402

st.set_page_config(page_title="Meeting AI", page_icon="🗂️", layout="wide")
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
.block-container { padding-top: 1.6rem; max-width: 1500px; }
.brand { display:flex; gap:.6rem; align-items:center; margin-bottom:1rem; }
.brand-logo { width:38px; height:38px; border-radius:10px; background:linear-gradient(135deg,#3b6cf6,#2443b8);
  color:#fff; display:flex; align-items:center; justify-content:center; font-size:20px; }
.brand-name { font-weight:700; font-size:1.15rem; color:var(--ink); line-height:1.1; }
.brand-sub { font-size:.75rem; color:var(--muted); }
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
  margin:0 .2rem .2rem 0; white-space:normal; line-height:1.35; }
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
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers


def badge(text: str, colors: tuple[str, str]) -> str:
    bg, fg = colors
    return f'<span class="badge" style="background:{bg};color:{fg}">{html.escape(text)}</span>'


def status_badge(item: Item) -> str:
    if not item.status:
        return ""
    return badge(STATUS_LABELS.get(item.status.value, item.status.value), STATUS_STYLE.get(item.status.value, ("#eee", "#333")))


def flag_badges(item: Item) -> str:
    return "".join(badge(FLAG_LABELS.get(f, f), FLAG_STYLE.get(f, ("#eee", "#333"))) for f in item.flags)


def esc(text: Any) -> str:
    return html.escape(str(text)) if text not in (None, "") else "—"


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


# ---------------------------------------------------------------- sidebar


def sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div class="brand"><div class="brand-logo">☁</div><div><div class="brand-name">Meeting AI</div>'
            '<div class="brand-sub">Trích xuất quyết định cuộc họp</div></div></div>',
            unsafe_allow_html=True,
        )
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
    try:
        if meta.date:
            form["date"] = datetime.strptime(meta.date, "%d/%m/%Y").date()
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
            st.markdown('<div class="muted">Định dạng .txt mỗi dòng <code>[mm:ss] Tên: nội dung</code> hoặc .vtt</div>',
                        unsafe_allow_html=True)
            upload = st.file_uploader("Tải transcript", type=["txt", "vtt"], label_visibility="collapsed")
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


def analyze(text: str, name: str, meta: MeetingMeta | None) -> None:
    bar = st.progress(0.0, text="Bắt đầu…")
    error = ""
    with st.status("Đang phân tích…", expanded=True) as status:
        def progress(msg: str, frac: float) -> None:
            bar.progress(min(frac, 1.0), text=msg)
            st.write(f"• {msg}")

        try:
            result = run_text(text, name, meta, settings=SETTINGS, progress=progress)
        except LLMError as exc:
            status.update(label="Lỗi khi gọi LLM", state="error")
            error = f"{exc}\n\nKiểm tra file `.env` (LLM_PROVIDER, OPENAI_API_KEY, MODEL_LIGHT, MODEL_STRONG)."
        except ValueError as exc:
            status.update(label="Transcript không hợp lệ", state="error")
            error = str(exc)
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
            c1.markdown(f"**{html.escape(title)}**  \n<span class='muted'>{html.escape(when)} · "
                        f"{html.escape(Path(r.source_file).name)}</span>", unsafe_allow_html=True)
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
    is_action = kind == "action"
    widths = [0.4, 3.2, 1.4, 1.1, 1.1, 1.2, 2.0, 0.6] if is_action else [0.4, 3.8, 1.5, 1.3, 1.4, 2.0, 0.6]
    heads = (["#", "Nội dung", "Chủ đề", "Phụ trách", "Hạn chót", "Trích dẫn", "Cờ / Duyệt", ""] if is_action
             else ["#", "Nội dung", "Chủ đề", "Trạng thái", "Trích dẫn", "Cờ / Duyệt", ""])
    hcols = st.columns(widths)
    for c, h in zip(hcols, heads):
        c.markdown(f"<span class='muted'><b>{h}</b></span>", unsafe_allow_html=True)
    for n, item in enumerate(items, start=1):
        cols = st.columns(widths, vertical_alignment="center")
        cls = "row-content rejected" if item.review == "rejected" else "row-content"
        conf = f"<br><span class='muted'>tin cậy {item.confidence:.0%}</span>"
        type_tag = "" if kind in ("decision", "action", "open") else f"<span class='muted'>{TYPE_LABEL[item.type]} · </span>"
        cols[0].markdown(f"<span class='muted'>{n}</span>", unsafe_allow_html=True)
        cols[1].markdown(f"<div class='{cls}'>{type_tag}{esc(item.content)}{conf}</div>", unsafe_allow_html=True)
        cols[2].markdown(f"<span class='row-topic'>{esc(item.topic)}</span>", unsafe_allow_html=True)
        cites = ", ".join(f"#{e}" for e in item.evidence)
        review = badge(REVIEW_LABELS.get(item.review, item.review), REVIEW_STYLE.get(item.review, ("#eee", "#333")))
        if is_action:
            cols[3].markdown(f"<span class='row-content'>{esc(item.owner)}</span>", unsafe_allow_html=True)
            cols[4].markdown(f"<span class='row-content'>{esc(item.deadline)}</span>", unsafe_allow_html=True)
            cols[5].markdown(f"<span class='cite'>{cites}</span>", unsafe_allow_html=True)
            cols[6].markdown(flag_badges(item) + review, unsafe_allow_html=True)
        else:
            cols[3].markdown(status_badge(item) or "<span class='muted'>—</span>", unsafe_allow_html=True)
            cols[4].markdown(f"<span class='cite'>{cites}</span>", unsafe_allow_html=True)
            cols[5].markdown(flag_badges(item) + review, unsafe_allow_html=True)
        if cols[-1].button("", icon=":material/chevron_right:", key=f"open-{prefix}-{item.item_id}", help="Xem chi tiết & duyệt"):
            item_dialog(run_dir, result, item.item_id)


@st.dialog("Chi tiết mục", width="large")
def item_dialog(run_dir: Path, result: RunResult, item_id: str) -> None:
    item = next(i for i in result.items if i.item_id == item_id)
    by_id = {u.id: u for u in result.utterances}
    st.markdown(f"**{item.item_id} · {TYPE_LABEL[item.type]}** — {esc(item.topic)}")
    st.markdown(f"### {html.escape(item.content)}")
    st.markdown(status_badge(item) + flag_badges(item)
                + badge(REVIEW_LABELS.get(item.review, item.review), REVIEW_STYLE[item.review]),
                unsafe_allow_html=True)
    info = []
    if item.condition:
        info.append(f"**Điều kiện:** {item.condition}")
    info.append(f"**Phụ trách:** {item.owner or '—'}  ·  **Hạn chót:** {item.deadline or '—'}  ·  "
                f"**Độ tin cậy:** {item.confidence:.0%}")
    st.markdown("  \n".join(info))

    st.markdown("**Trích dẫn nguyên văn**")
    for e in item.evidence:
        u = by_id.get(e)
        if u:
            st.markdown(f"<div class='quote'><small>{u.id} · {u.time} · <b>{html.escape(u.speaker)}</b></small>"
                        f"<br>{html.escape(u.text)}</div>", unsafe_allow_html=True)
    if item.history:
        st.markdown("**Lịch sử thay đổi**")
        rows = []
        for h in item.history:
            quotes = "<br>".join(f"<small>{by_id[e].time} {html.escape(by_id[e].speaker)}: “{html.escape(by_id[e].text)}”</small>"
                                 for e in h.evidence if e in by_id)
            reason = f" — <i>{html.escape(h.reason)}</i>" if h.reason else ""
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
        if st.form_submit_button("Lưu chỉnh sửa", type="primary"):
            set_review(run_dir, item_id, "edited", {
                "content": content.strip(), "status": status or None, "condition": condition.strip() or None,
                "owner": owner.strip() or None, "deadline": deadline.strip() or None,
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
    st.markdown("  \n".join(f"**{k}:** {html.escape(str(v)) if v else '—'}" for k, v in rows))
    if meta and meta.agenda:
        st.markdown("**Chương trình:**  \n" + "  \n".join(f"• {html.escape(a)}" for a in meta.agenda))
    if meta and meta.participants:
        st.dataframe(pd.DataFrame([{"Tên": p.name, "Vai trò": p.role or "", "Quyền chốt": p.can_decide}
                                   for p in meta.participants]), hide_index=True, use_container_width=True)
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

    main, side = st.columns([2.35, 1], gap="large")
    with main:
        st.markdown(f'<div class="crumb">Tất cả cuộc họp › <b>{html.escape(title)}</b></div>'
                    f'<div class="title">{html.escape(title)}</div>', unsafe_allow_html=True)
        parts = []
        if meta and (meta.start_time or meta.date):
            parts.append(f"🗓️ {html.escape(' – '.join(x for x in [meta.start_time, meta.end_time] if x))}"
                         f"{', ' + html.escape(meta.date) if meta.date else ''}")
        speakers = {u.speaker for u in result.utterances}
        n_people = len(meta.participants) if meta and meta.participants else len(speakers)
        parts.append(f"👥 {n_people} người tham dự")
        parts.append(f"💬 {len(result.utterances)} câu · {len(result.topics)} chủ đề")
        if meta and meta.project:
            parts.append(f"<span class='chip'>{html.escape(meta.project)}</span>")
        st.markdown(f"<div class='meta-line'>{''.join(f'<span>{p}</span>' for p in parts)}</div>",
                    unsafe_allow_html=True)
        st.write("")
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
        if a4.button("✔ Duyệt nhanh", type="primary", use_container_width=True,
                     help="Chấp nhận mọi mục chưa duyệt không có cờ và độ tin cậy ≥ 70%"):
            for i in result.items:
                if i.review == "pending" and not i.flags and i.confidence >= 0.7:
                    set_review(run_dir, i.item_id, "accepted")
            st.rerun()
        st.write("")
        stat_cards(result.items)
        st.write("")
        tabs = st.tabs(["Tổng quan"] + [g[1] for g in GROUPS])
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
        for tab, (key, label, types) in zip(tabs[1:], GROUPS):
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
