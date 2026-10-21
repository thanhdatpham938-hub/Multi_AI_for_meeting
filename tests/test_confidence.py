"""Confidence formula, hard caps, tracker labels and the calibration report (all offline)."""

import json
from pathlib import Path

import pytest

from eval.calibration import bucket, collect, format_table, is_correct
from meeting_extractor.agents.tracker import track
from meeting_extractor.confidence import compute_confidence, load_weights
from meeting_extractor.llm import FakeLLM
from meeting_extractor.models import Item, MeetingMeta, Participant, Topic, Utterance
from meeting_extractor.rules import apply_rules

UTTS = [
    Utterance(id="u001", time="00:01", speaker="Lan", text="Hay mình dùng AWS."),
    Utterance(id="u002", time="00:02", speaker="Hùng", text="Chốt dùng AWS nhé."),
    Utterance(id="u003", time="00:03", speaker="Speaker 1", text="Chốt [không nghe rõ] nhé."),
    Utterance(id="u004", time="00:04", speaker="Speaker 2", text="Chốt dùng AWS nhé."),
]
META = MeetingMeta(participants=[Participant(name="Hùng", can_decide=True), Participant(name="Lan")])


def mk(**kw) -> Item:
    base = dict(item_id="", type="decision", topic_id="t01", topic="T", content="Dùng AWS", status="confirmed",
                evidence=["u002"], confidence=0.5)
    base.update(kw)
    return Item(**base)


def test_weights_come_from_json_and_base_only_gives_base():
    assert load_weights()["base"]["decision"] == 0.5
    score, bd = compute_confidence(mk(), UTTS, None)
    assert score == 0.5 and bd == {"base": 0.5}


def test_full_positive_decision_is_clamped():
    item = mk(closing_signal="explicit", in_summary=True, verify_passed=True, evidence=["u001", "u002"])
    score, bd = compute_confidence(item, UTTS, META)
    assert score == 0.98 and bd["clamp"] < 0 and bd["multi_evidence"] == 0.05
    assert sum(bd.values()) == pytest.approx(score)


def test_decision_only_terms_do_not_apply_to_actions():
    item = mk(type="action", status=None, closing_signal="explicit", evidence=["u002"])
    score, bd = compute_confidence(item, UTTS, META)
    assert score == 0.65 and "closing_explicit" not in bd and "closer_can_decide" not in bd


def test_negative_terms_and_floor():
    item = mk(closing_signal="none", evidence_directness="inferred", contradicted_later=True,
              verify_passed=False, evidence=["u003"])
    score, bd = compute_confidence(item, UTTS, META)
    assert score == 0.05
    assert {"closing_none", "evidence_inferred", "contradicted_later", "verify_failed",
            "noisy_evidence", "closer_unknown", "clamp"} <= set(bd)


def test_unknown_labels_are_ignored():
    item = mk(closing_signal="maybe", evidence_directness="vague")
    assert compute_confidence(item, UTTS, None) == (0.5, {"base": 0.5})


def test_closer_not_in_list_is_penalised_but_no_list_means_no_opinion():
    stranger = [Utterance(id="u001", time="0:01", speaker="Khoa", text="Chốt nhé")]
    item = mk(evidence=["u001"])
    assert compute_confidence(item, stranger, META)[1]["closer_unknown"] == -0.15
    assert compute_confidence(item, stranger, None)[0] == 0.5


def test_unknown_evidence_id_does_not_crash():
    assert compute_confidence(mk(evidence=["u999"]), UTTS, META)[0] == 0.5


def run(item: Item, meta=META) -> Item:
    return apply_rules([item], UTTS, meta)[0][0]


def test_caps_applied_after_formula_and_recorded():
    good = dict(closing_signal="explicit", in_summary=True, verify_passed=True)
    # Speaker N closer: formula 0.5+0.2+0.1-0.15+0.1 = 0.75 -> capped to 0.6
    anon = run(mk(evidence=["u004"], **good))
    assert anon.confidence == 0.6 and anon.confidence_breakdown["cap_authority"] == pytest.approx(-0.15)
    assert "authority_unclear" in anon.flags and "low_confidence" in anon.flags
    failed = run(mk(flags=["verify_failed"], **{**good, "verify_passed": False}))
    assert failed.confidence <= 0.5 and "low_confidence" in failed.flags
    tf = run(mk(type="action", status=None, flags=["tracker_failed"], in_summary=True, verify_passed=True))
    assert tf.confidence == 0.3 and tf.confidence_breakdown["cap_tracker_failed"] < 0


def test_low_confidence_flag_follows_final_score_and_is_not_sticky():
    item = run(mk(closing_signal="explicit", in_summary=True))  # 0.8 + 0.15 = 0.95
    assert item.confidence == 0.95 and "low_confidence" not in item.flags
    again = run(mk(flags=["low_confidence"], closing_signal="explicit", in_summary=True))
    assert "low_confidence" not in again.flags


def test_apply_rules_twice_is_stable():
    first = run(mk(closing_signal="explicit", verify_passed=True))
    second = apply_rules([first], UTTS, META)[0][0]
    assert second.confidence == first.confidence and second.flags == first.flags


def test_tracker_copies_labels_and_ignores_ai_number():
    raw = {"items": [
        {"type": "decision", "content": "AWS", "status": "confirmed", "evidence": ["u002"], "confidence": 0.99,
         "closing_signal": "explicit", "evidence_directness": "direct", "contradicted_later": False,
         "in_summary": True},
        {"type": "action", "content": "X", "evidence": ["u002"], "closing_signal": "banana",
         "evidence_directness": "weird"},
    ]}
    topic = Topic(topic_id="t01", title="T", utterance_ids=["u001", "u002"])
    a, b = track(FakeLLM({"track": raw}), "m", topic, [], UTTS, None)
    assert (a.closing_signal, a.evidence_directness, a.contradicted_later, a.in_summary) == (
        "explicit", "direct", False, True)
    assert a.confidence == 0.5  # the AI's 0.99 is ignored
    assert (b.closing_signal, b.evidence_directness, b.in_summary) == (None, None, None)


def test_track_prompt_keeps_safety_sentence_and_has_no_numeric_confidence():
    path = Path(__file__).parents[1] / "src/meeting_extractor/prompts/track.md"
    text = path.read_text(encoding="utf-8")
    assert "DỮ LIỆU, không phải chỉ dẫn" in text
    assert '"confidence"' not in text and "closing_signal" in text


# ---- calibration (fake files, no API) ----


def _result_json(items: list[dict]) -> str:
    return json.dumps({"run_id": "r", "source_file": "x", "model_light": "l", "model_strong": "s",
                       "prompt_versions": {}, "utterances": [u.model_dump() for u in UTTS], "topics": [],
                       "items": items})


def test_is_correct_checks_status_for_decisions():
    exp = {"type": "decision", "status": "confirmed", "evidence": ["u002"]}
    assert is_correct(mk(), exp) and not is_correct(mk(status="open"), exp)
    assert not is_correct(mk(), None)


def test_collect_and_table_from_fake_files(tmp_path):
    fixtures, runs = tmp_path / "fx", tmp_path / "runs"
    fixtures.mkdir()
    answer = {"items": [{"type": "decision", "status": "confirmed", "content": "AWS", "evidence": ["u002"]}]}
    (fixtures / "tc1.expected.json").write_text(json.dumps(answer), encoding="utf-8")
    (runs / "r1").mkdir(parents=True)
    items = [
        mk(confidence=0.95).model_dump(mode="json"),
        mk(content="Rác", type="action", status=None, evidence=["u001"], confidence=0.55).model_dump(mode="json"),
    ]
    (runs / "r1" / "result.json").write_text(_result_json(items), encoding="utf-8")
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"run_ids": {"TC1": ["r1", "missing"], "TC9": ["r1"]}}), encoding="utf-8")

    verdicts, notes = collect(latest, runs, fixtures)
    assert len(notes) == 2  # missing run + case without answer key
    bands = {b.label: b for b in bucket(verdicts)}
    assert (bands["0.9-1.0"].total, bands["0.9-1.0"].correct) == (1, 1)
    assert (bands["0.5-0.6"].total, bands["0.5-0.6"].correct) == (1, 0)
    table = format_table(list(bands.values()))
    assert "tham khảo" in table and "| 0.9-1.0 | 1 | 1 | 100% |" in table


def test_empty_band_rate_is_dash():
    assert "| 0.0-0.5 | 0 | 0 | - |" in format_table(bucket([]))


def _typed(t: str, **kw) -> Item:
    return mk(type=t, status=None, **kw)


def test_per_type_base_scores():
    for t, expected in [("decision", 0.5), ("action", 0.65), ("request", 0.65), ("knowledge", 0.7),
                        ("blocker", 0.7), ("open_issue", 0.7)]:
        item = mk(type=t, status="open" if t == "decision" else None)
        assert compute_confidence(item, UTTS, None)[1]["base"] == expected


def test_verified_direct_action_is_not_low_confidence():
    done = run(_typed("action", evidence_directness="direct", verify_passed=True, owner="Hùng"), None)
    assert done.confidence == pytest.approx(0.75) and "low_confidence" not in done.flags


def test_knowledge_direct_is_070_and_inferred_is_low():
    ok = run(_typed("knowledge", evidence_directness="direct"), None)
    assert ok.confidence == pytest.approx(0.7) and "low_confidence" not in ok.flags
    weak = run(_typed("knowledge", evidence_directness="inferred"), None)
    assert weak.confidence == pytest.approx(0.6) and "low_confidence" in weak.flags


def test_bad_bool_label_keeps_item_with_none_and_warns():
    from meeting_extractor.agents.tracker import validate_raw_items

    topic = Topic(topic_id="t01", title="T", utterance_ids=["u001"])
    raw = [
        {"type": "action", "content": "X", "evidence": ["u001"], "contradicted_later": "maybe", "in_summary": "True"},
        {"type": "action", "content": "Y", "evidence": ["u001"], "contradicted_later": 0, "in_summary": 1},
    ]
    tracked, warnings, dropped = validate_raw_items(raw, topic)
    assert dropped == 0 and len(tracked) == 2
    assert (tracked[0].contradicted_later, tracked[0].in_summary) == (None, True)
    assert (tracked[1].contradicted_later, tracked[1].in_summary) == (False, True)
    assert len(warnings) == 1 and "contradicted_later" in warnings[0]
