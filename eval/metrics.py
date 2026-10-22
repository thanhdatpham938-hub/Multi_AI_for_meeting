"""Match system items to the answer key and compute the §9 metrics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from meeting_extractor.conflicts import conflict_pairs
from meeting_extractor.models import Item, RunResult, Status

THRESHOLDS = {
    "false_confirm_rate": ("≤", 0.05),
    "decision_recall": ("≥", 0.85),
    "action_precision": ("≥", 0.80),
    "citation_accuracy": ("≥", 0.95),
    "fabricated_fields": ("≤", 0),
    "stability_change_rate": ("≤", 0.10),
    # Mission 3 metrics (thresholds from PLAN_MISSION_3.md section 2)
    "unresolved_status_accuracy": ("≥", 0.80),
    "quote_validity": ("≥", 0.95),
    "field_provenance": ("≥", 1.0),
    "knowledge_scope_accuracy": ("≥", 0.75),
    "unflagged_conflicts": ("≤", 0),
    "expected_flags_met": ("≥", 1.0),
}
LABELS = {
    "false_confirm_rate": "Tỷ lệ chốt nhầm",
    "decision_recall": "Recall quyết định",
    "action_precision": "Precision việc cần làm",
    "citation_accuracy": "Độ chính xác trích dẫn",
    "fabricated_fields": "Owner/deadline bịa",
    "stability_change_rate": "Độ ổn định (đổi trạng thái)",
    "unresolved_status_accuracy": "Trạng thái đúng cho mục chưa chốt",
    "quote_validity": "Đoạn trích kiểm chứng được",
    "field_provenance": "Owner/deadline có câu nguồn riêng",
    "knowledge_scope_accuracy": "Phạm vi tri thức đúng",
    "unflagged_conflicts": "Quyết định mâu thuẫn không gắn cờ",
    "expected_flags_met": "Cờ kỳ vọng có mặt (expect_flags_any)",
}
OLD_METRICS = ("false_confirm_rate", "decision_recall", "action_precision", "citation_accuracy", "fabricated_fields")
NEW_METRICS = ("unresolved_status_accuracy", "quote_validity", "field_provenance", "knowledge_scope_accuracy",
               "unflagged_conflicts", "expected_flags_met")
COUNT_METRICS = ("fabricated_fields", "unflagged_conflicts")  # printed as integers, not percentages
SMALL_SAMPLE = 10
UNRESOLVED_STATUSES = {"deferred", "conditional", "open"}
M3_COUNT_KEYS = (
    "unres_total", "unres_ok", "quote_total", "quote_ok", "prov_total", "prov_ok",
    "scope_total", "scope_ok", "decisions_total", "conflicts_unflagged", "flags_expected", "flags_met",
)

# (expected_content, system_content) -> bool ; usually a small LLM yes/no judge
ContentJudge = Callable[[str, str], bool]


@dataclass
class Match:
    expected: dict[str, Any]
    item: Item | None
    how: str = ""  # "evidence" | "llm" | ""


@dataclass
class CaseReport:
    case: str
    known_limitation: bool
    matches: list[Match]
    unmatched_items: list[Item]
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # informational lines, not case errors

    @property
    def passed(self) -> bool:
        return not self.errors


def accepted_statuses(exp: dict[str, Any]) -> set[str]:
    if exp.get("accept_statuses"):
        return set(exp["accept_statuses"])
    return {exp["status"]} if exp.get("status") else set()


def owner_accepted(exp: dict[str, Any], owner: str | None) -> bool:
    """With `accept_owners`: owner matches any listed value (case-insensitive); null in the list accepts no owner."""
    if "accept_owners" not in exp:
        return False
    allowed = exp["accept_owners"] or []
    if not (owner or "").strip():
        return None in allowed
    return (owner or "").strip().lower() in {a.strip().lower() for a in allowed if isinstance(a, str)}


def match_items(expected: list[dict[str, Any]], items: list[Item], judge: ContentJudge | None = None) -> list[Match]:
    """Greedy one-to-one: same type + evidence overlap first, then optional content judge.

    Ties on overlap go to the item whose status the answer accepts (decisions only), then to the
    earlier item.
    """
    used: set[int] = set()
    matches: list[Match] = []
    for exp in expected:
        best, best_key = None, (0, False)
        wanted = accepted_statuses(exp) if exp["type"] == "decision" else set()
        for idx, it in enumerate(items):
            if idx in used or it.type.value != exp["type"]:
                continue
            overlap = len(set(it.evidence) & set(exp["evidence"]))
            key = (overlap, bool(it.status) and it.status.value in wanted)
            if overlap > 0 and key > best_key:
                best, best_key = idx, key
        if best is not None:
            used.add(best)
            matches.append(Match(exp, items[best], "evidence"))
            continue
        found = None
        if judge is not None:
            for idx, it in enumerate(items):
                if idx not in used and it.type.value == exp["type"] and judge(exp["content"], it.content):
                    found = idx
                    break
        if found is not None:
            used.add(found)
            matches.append(Match(exp, items[found], "llm"))
        else:
            matches.append(Match(exp, None))
    unmatched = [it for i, it in enumerate(items) if i not in used]
    return matches + [Match({}, it) for it in unmatched]  # tail = unmatched items (expected={})


def evaluate_case(result: RunResult, answer: dict[str, Any], judge: ContentJudge | None = None) -> CaseReport:
    items = [i for i in result.items if i.review != "rejected"]
    all_matches = match_items(answer.get("items", []), items, judge)
    matches = [m for m in all_matches if m.expected]
    unmatched = [m.item for m in all_matches if not m.expected and m.item is not None]
    rep = CaseReport(answer.get("case", result.source_file), bool(answer.get("known_limitation")), matches, unmatched)
    c = rep.counts = {k: 0 for k in (
        "confirmed_total", "confirmed_wrong", "exp_decisions", "exp_decisions_matched",
        "actions_total", "actions_matched", "matched_total", "matched_cited", "fabricated", *M3_COUNT_KEYS)}

    # --- false confirmations
    for it in items:
        if it.status != Status.confirmed:
            continue
        c["confirmed_total"] += 1
        exp = next((m.expected for m in matches if m.item is it), None)
        if exp is None or "confirmed" not in accepted_statuses(exp):
            c["confirmed_wrong"] += 1
            rep.errors.append(f"Chốt nhầm: [{it.item_id}] \"{it.content}\" evidence={it.evidence}")

    for m in matches:
        exp, it = m.expected, m.item
        optional = exp.get("optional", False)
        if exp["type"] == "decision" and not optional:
            c["exp_decisions"] += 1
            if it is not None:
                c["exp_decisions_matched"] += 1
        if it is None:
            if not optional:
                rep.errors.append(f"Bỏ sót {exp['type']}: \"{exp['content']}\"")
            continue
        c["matched_total"] += 1
        if set(it.evidence) & set(exp["evidence"]):
            c["matched_cited"] += 1
        else:
            rep.errors.append(f"Trích dẫn lệch: \"{it.content}\" evidence={it.evidence}, đáp án {exp['evidence']}")
        for fld in ("owner", "deadline"):
            if getattr(it, fld) and not exp.get(fld) and not (fld == "owner" and owner_accepted(exp, it.owner)):
                c["fabricated"] += 1
                rep.errors.append(f"{fld} bịa: \"{it.content}\" {fld}={getattr(it, fld)!r}")
        _check_item_details(rep, exp, it)

    actions = [it for it in items if it.type.value == "action"]
    c["actions_total"] = len(actions)
    c["actions_matched"] = sum(1 for m in matches if m.item is not None and m.expected["type"] == "action")
    for it in unmatched:
        if it.type.value == "action":
            rep.errors.append(f"Action thừa: [{it.item_id}] \"{it.content}\" owner={it.owner}")

    _check_case_rules(rep, result, answer, items)
    _collect_m3_counts(rep, result, answer, items)
    return rep


def _check_item_details(rep: CaseReport, exp: dict[str, Any], it: Item) -> None:
    label = f"\"{exp['content']}\""
    statuses = accepted_statuses(exp)
    if statuses and (it.status.value if it.status else None) not in statuses:
        rep.errors.append(f"Sai trạng thái {label}: {it.status.value if it.status else None}, đáp án {sorted(statuses)}")
    if "accept_owners" in exp:
        if not owner_accepted(exp, it.owner):
            rep.errors.append(f"Sai owner {label}: {it.owner!r}, đáp án chấp nhận {exp['accept_owners']}")
    elif exp.get("owner") and (it.owner or "").strip().lower() != exp["owner"].lower():
        rep.errors.append(f"Sai owner {label}: {it.owner!r}, đáp án {exp['owner']!r}")
    if exp.get("deadline") and exp["deadline"].lower() not in (it.deadline or "").lower():
        rep.errors.append(f"Sai deadline {label}: {it.deadline!r}, đáp án {exp['deadline']!r}")
    if exp.get("condition") and not it.condition:
        rep.errors.append(f"Thiếu điều kiện {label}")
    for flag in exp.get("required_flags", []):
        if flag not in it.flags:
            rep.errors.append(f"Thiếu cờ {flag} ở {label}")
    if "min_confidence" in exp and it.confidence < exp["min_confidence"]:
        rep.errors.append(f"Confidence {it.confidence:.2f} < {exp['min_confidence']} ở {label}")
    if "max_confidence" in exp and it.confidence > exp["max_confidence"]:
        rep.errors.append(f"Confidence {it.confidence:.2f} > {exp['max_confidence']} ở {label}")
    for sup in exp.get("history_superseded", []):
        ok = any(h.status == Status.superseded and set(h.evidence) & set(sup["evidence"]) for h in it.history)
        if not ok:
            rep.errors.append(f"Lịch sử thiếu \"{sup['content']}\" superseded trong {label}")


def _check_case_rules(rep: CaseReport, result: RunResult, answer: dict[str, Any], items: list[Item]) -> None:
    if answer.get("expect_no_confirmed") and any(i.status == Status.confirmed for i in items):
        rep.errors.append("Ca này không được có item confirmed")
    for rule in answer.get("forbidden", []):
        bad = set(rule["evidence_only"])
        for it in items:
            if (it.type.value == rule["type"] and it.status and it.status.value in rule["statuses"]
                    and set(it.evidence) <= bad):
                rep.errors.append(f"Vi phạm: {rule.get('note', '')} → [{it.item_id}] \"{it.content}\"")
    for group in answer.get("same_topic", []):
        topics = {t.topic_id for t in result.topics for uid in group if uid in t.utterance_ids}
        if len(topics) != 1:
            rep.errors.append(f"Các câu {group} không cùng một chủ đề (topics={sorted(topics)})")


def aggregate(reports: list[CaseReport]) -> dict[str, float]:
    scored = [r for r in reports if not r.known_limitation]
    tot = {k: sum(r.counts.get(k, 0) for r in scored) for k in scored[0].counts} if scored else {}

    def ratio(num: str, den: str, empty: float) -> float:
        return tot[num] / tot[den] if tot.get(den) else empty

    return {
        "false_confirm_rate": ratio("confirmed_wrong", "confirmed_total", 0.0),
        "decision_recall": ratio("exp_decisions_matched", "exp_decisions", 1.0),
        "action_precision": ratio("actions_matched", "actions_total", 1.0),
        "citation_accuracy": ratio("matched_cited", "matched_total", 1.0),
        "fabricated_fields": float(tot.get("fabricated", 0)),
    }



# ---------------------------------------------------------------- Mission 3 metrics


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def invalid_quotes(item: Item, utterances: dict[str, str]) -> list[str]:
    """IDs whose quote is not a substring of the cited utterance (whitespace/case-insensitive)."""
    quotes = getattr(item, "evidence_quotes", None) or {}
    bad = []
    for uid, quote in quotes.items():
        q = _norm(str(quote))
        if not q or uid not in utterances or q not in _norm(utterances[uid]):
            bad.append(uid)
    return bad


def _collect_m3_counts(rep: CaseReport, result: RunResult, answer: dict[str, Any], items: list[Item]) -> None:
    c = rep.counts
    texts = {u.id: u.text for u in result.utterances}
    for m in rep.matches:
        exp, it = m.expected, m.item
        if it is None:
            continue
        statuses = accepted_statuses(exp)
        if statuses and statuses <= UNRESOLVED_STATUSES:
            c["unres_total"] += 1
            c["unres_ok"] += int(bool(it.status and it.status.value in statuses))
        if it.type.value == "knowledge" and exp.get("knowledge_scope"):
            c["scope_total"] += 1
            c["scope_ok"] += int(getattr(it, "knowledge_scope", None) == exp["knowledge_scope"])
    for it in items:
        if getattr(it, "evidence_quotes", None):
            c["quote_total"] += 1
            bad = invalid_quotes(it, texts)
            c["quote_ok"] += int(not bad)
            if bad:
                rep.notes.append(f"Đoạn trích không khớp câu {bad}: [{it.item_id}] \"{it.content}\"")
        provenance = getattr(it, "field_evidence", None) or {}
        for fld in ("owner", "deadline"):
            if getattr(it, fld):
                c["prov_total"] += 1
                c["prov_ok"] += int(bool(provenance.get(fld)))
    _check_conflicts_and_flags(rep, answer, items)


def _check_conflicts_and_flags(rep: CaseReport, answer: dict[str, Any], items: list[Item]) -> None:
    c = rep.counts
    c["decisions_total"] = sum(1 for i in items if i.type.value == "decision")
    pairs = conflict_pairs(items)
    for a, b in pairs:
        if "conflicting_decision" in a.flags or "conflicting_decision" in b.flags:
            continue
        c["conflicts_unflagged"] += 1
        rep.notes.append(f"Mâu thuẫn không gắn cờ: [{a.item_id}] \"{a.content}\" vs [{b.item_id}] \"{b.content}\"")
    unflagged = sum(1 for a, b in pairs if "conflicting_decision" not in a.flags and "conflicting_decision" not in b.flags)
    if answer.get("expect_no_conflicts") and unflagged:
        rep.errors.append(f"Ca này không được có quyết định mâu thuẫn chưa gắn cờ ({unflagged} cặp)")
    wanted = answer.get("expect_flags_any") or []
    if wanted:
        c["flags_expected"] += 1
        if any(f in i.flags for i in items for f in wanted):
            c["flags_met"] += 1
        else:
            rep.errors.append(f"Không có mục nào mang cờ nào trong {wanted}")


Metric = tuple[float | None, int]  # (value, or None = not applicable; sample size)


def aggregate_detail(reports: list[CaseReport]) -> dict[str, Metric]:
    """Old five metrics plus the Mission 3 ones, each with its sample size; None = no samples."""
    scored = [r for r in reports if not r.known_limitation]

    def total(rs: list[CaseReport], key: str) -> int:
        return sum(r.counts.get(key, 0) for r in rs)

    def ratio(num: str, den: str, rs: list[CaseReport] = scored) -> Metric:
        n = total(rs, den)
        return (total(rs, num) / n if n else None), n

    def count(num: str, den: str) -> Metric:
        n = total(scored, den)
        return (float(total(scored, num)) if n else None), n

    return {
        "false_confirm_rate": ratio("confirmed_wrong", "confirmed_total"),
        "decision_recall": ratio("exp_decisions_matched", "exp_decisions"),
        "action_precision": ratio("actions_matched", "actions_total"),
        "citation_accuracy": ratio("matched_cited", "matched_total"),
        "fabricated_fields": count("fabricated", "matched_total"),
        "unresolved_status_accuracy": ratio("unres_ok", "unres_total"),
        "quote_validity": ratio("quote_ok", "quote_total"),
        "field_provenance": ratio("prov_ok", "prov_total"),
        "knowledge_scope_accuracy": ratio("scope_ok", "scope_total"),
        "unflagged_conflicts": count("conflicts_unflagged", "decisions_total"),
        "expected_flags_met": ratio("flags_met", "flags_expected", reports),  # all cases, incl. known limitations
    }


def format_metric(name: str, value: float | None, n: int) -> str:
    """Value with its sample size; `không áp dụng` without samples, `(tham khảo)` below SMALL_SAMPLE."""
    if value is None:
        return "không áp dụng (0 mẫu)"
    text = f"{value:.0f}" if name in COUNT_METRICS else f"{value:.1%}"
    return f"{text} (n={n}){' (tham khảo)' if n < SMALL_SAMPLE else ''}"


def stability(runs_per_case: dict[str, list[list[Match]]]) -> tuple[float, list[str]]:
    """Share of expected items whose status (or presence) changed across repeated runs."""
    total = changed = 0
    details: list[str] = []
    for case, runs in runs_per_case.items():
        if len(runs) < 2:
            continue
        for idx, m in enumerate(runs[0]):
            if not m.expected:
                continue
            seen = {
                (r[idx].item.status.value if r[idx].item and r[idx].item.status else
                 ("present" if r[idx].item else "missing"))
                for r in runs
            }
            total += 1
            if len(seen) > 1:
                changed += 1
                details.append(f"{case}: \"{m.expected['content']}\" → {sorted(seen)}")
    return (changed / total if total else 0.0), details


def meets(metric: str, value: float) -> bool:
    op, bound = THRESHOLDS[metric]
    return value <= bound if op == "≤" else value >= bound
