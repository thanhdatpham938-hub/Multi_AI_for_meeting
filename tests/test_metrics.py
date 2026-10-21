"""Offline checks of the evaluation metrics (no API)."""

import json
from pathlib import Path

import pytest

from eval.metrics import aggregate, evaluate_case, match_items, meets, stability
from meeting_extractor.models import HistoryEntry, Item, MeetingMeta, RunResult, Status, Topic
from meeting_extractor.parsing import load_meta, parse_file
from meeting_extractor.rules import apply_rules

FIXTURES = Path(__file__).parent / "fixtures"


def load_case(n: int):
    utts, _ = parse_file(FIXTURES / f"tc{n}.txt")
    answer = json.loads((FIXTURES / f"tc{n}.expected.json").read_text(encoding="utf-8"))
    meta_path = FIXTURES / f"tc{n}.meta.json"
    return utts, answer, load_meta(meta_path) if meta_path.exists() else None


def oracle_result(n: int) -> RunResult:
    """A RunResult built from the answer key itself, passed through the real rules."""
    utts, answer, meta = load_case(n)
    items = []
    for exp in answer["items"]:
        history = [HistoryEntry(status="superseded", content=s["content"], evidence=s["evidence"])
                   for s in exp.get("history_superseded", [])]
        # Labels a good Agent 3 + Agent 4 would produce; confidence is then computed by the formula.
        confirmed = exp.get("status") == "confirmed"
        labels = dict(
            closing_signal=("explicit" if confirmed else "none") if exp["type"] == "decision" else None,
            evidence_directness="direct", contradicted_later=False, in_summary=confirmed,
            verify_passed=True if exp["type"] in ("decision", "action") else None,
        )
        items.append(Item(item_id="", type=exp["type"], topic_id="t01", topic="T", content=exp["content"],
                          status=exp.get("status"), condition=exp.get("condition"), owner=exp.get("owner"),
                          deadline=exp.get("deadline"), evidence=exp["evidence"], history=history,
                          confidence=0.5, **labels))
    items, _ = apply_rules(items, utts, meta)
    topic = Topic(topic_id="t01", title="T", utterance_ids=[u.id for u in utts])
    return RunResult(run_id="x", source_file=f"tc{n}", model_light="l", model_strong="s", prompt_versions={},
                     utterances=utts, topics=[topic], items=items, meta=meta or MeetingMeta())


@pytest.mark.parametrize("n", range(1, 8))
def test_oracle_passes_every_case(n):
    _, answer, _ = load_case(n)
    rep = evaluate_case(oracle_result(n), answer)
    assert rep.errors == []


def test_oracle_meets_all_thresholds():
    reports = [evaluate_case(oracle_result(n), load_case(n)[1]) for n in range(1, 8)]
    metrics = aggregate(reports)
    assert all(meets(k, v) for k, v in metrics.items()), metrics


def test_false_confirmation_is_caught():
    result = oracle_result(4)
    result.items[0].status = Status.confirmed  # gói B wrongly confirmed
    rep = evaluate_case(result, load_case(4)[1])
    assert rep.counts["confirmed_wrong"] == 1
    assert any("Chốt nhầm" in e for e in rep.errors)
    assert aggregate([rep])["false_confirm_rate"] == 1.0


def test_fabricated_owner_and_extra_action_counted():
    result = oracle_result(2)
    for it in result.items:
        if it.owner is None:
            it.owner = "Nam"
    result.items.append(Item(item_id="a09", type="action", topic_id="t01", topic="T", content="Đi cà phê",
                             evidence=["u016"], confidence=0.8))
    rep = evaluate_case(result, load_case(2)[1])
    m = aggregate([rep])
    assert m["fabricated_fields"] == 1
    assert m["action_precision"] == pytest.approx(2 / 3)


def test_content_judge_used_when_evidence_differs():
    result = oracle_result(6)
    result.items[0].evidence = ["u009"]
    answer = load_case(6)[1]
    assert evaluate_case(result, answer).matches[0].how == ""
    rep = evaluate_case(result, answer, judge=lambda a, b: True)
    assert rep.matches[0].how == "llm"
    assert any("Trích dẫn lệch" in e for e in rep.errors)


def test_stability_detects_status_change():
    answer = load_case(1)[1]
    r1 = oracle_result(1)
    r2 = oracle_result(1)
    r2.items[0].status = Status.open
    runs = {"TC1": [match_items(answer["items"], r1.items), match_items(answer["items"], r2.items)]}
    rate, details = stability(runs)
    assert rate == 1.0 and details
