from typing import Any

import pytest

from meeting_extractor.agents.tracker import (
    TRACKER_FLAGS,
    build_items,
    candidates_to_items,
    clean_new_labels,
    validate_raw_items,
)
from meeting_extractor.llm import load_prompt
from meeting_extractor.models import Candidate, Topic

TOPIC = Topic(topic_id="t01", title="Hạ tầng", utterance_ids=["u001", "u002"])


def raw_item(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": "action",
        "content": "Minh viết tài liệu API",
        "evidence": ["u001", "u002"],
        "owner": "Minh",
    }
    base.update(extra)
    return base


def validate_one(**extra: Any):
    tracked, warnings, dropped = validate_raw_items([raw_item(**extra)], TOPIC)
    assert dropped == 0 and len(tracked) == 1, warnings
    return tracked[0], warnings


def test_valid_new_labels_pass_through():
    t, warnings = validate_one(
        commitment="assigned",
        knowledge_scope="project",
        evidence_quotes={"u001": "Minh làm tài liệu API"},
        field_evidence={"owner": ["u001"], "deadline": "u001"},
        pending_on="ý kiến sếp",
        follow_up_owner="Hùng",
    )
    assert warnings == []
    item = build_items([t], TOPIC)[0]
    assert item.commitment == "assigned"
    assert item.knowledge_scope == "project"
    assert item.evidence_quotes == {"u001": "Minh làm tài liệu API"}
    assert item.field_evidence == {"owner": ["u001"], "deadline": ["u001"]}  # single string -> list
    assert item.pending_on == "ý kiến sếp" and item.follow_up_owner == "Hùng"


@pytest.mark.parametrize("bad", ["done", 5, ["assigned"], {"a": 1}, True])
def test_bad_commitment_and_scope_become_none(bad):
    t, warnings = validate_one(commitment=bad, knowledge_scope=bad)
    assert t.commitment is None and t.knowledge_scope is None
    assert len([w for w in warnings if "không hợp lệ" in w]) == 2


@pytest.mark.parametrize("bad", ["text", ["u001"], 3, True])
def test_evidence_quotes_not_dict_dropped(bad):
    t, warnings = validate_one(evidence_quotes=bad)
    assert t.evidence_quotes == {}
    assert any("evidence_quotes" in w for w in warnings)


def test_evidence_quotes_partial_garbage_keeps_good_part():
    t, warnings = validate_one(
        evidence_quotes={"u001": "ok", "u999": "không thuộc evidence", "u002": 123, "u003": ["x"], "u004": "  "}
    )
    assert t.evidence_quotes == {"u001": "ok"}
    assert any("evidence_quotes" in w for w in warnings)


def test_evidence_quotes_with_non_list_evidence_does_not_crash():
    tracked, warnings, dropped = validate_raw_items([raw_item(evidence="u001", evidence_quotes={"u001": "x"})], TOPIC)
    assert dropped == 1 and tracked == []  # evidence invalid -> item dropped by existing rule, no exception


@pytest.mark.parametrize("bad", ["u001", ["u001"], 7, None])
def test_field_evidence_not_dict_dropped(bad):
    t, warnings = validate_one(field_evidence=bad)
    assert t.field_evidence == {}
    if bad is not None:
        assert any("field_evidence" in w for w in warnings)


def test_field_evidence_filters_keys_and_values():
    t, warnings = validate_one(
        field_evidence={
            "owner": ["u001"],
            "deadline": "u002",
            "condition": [1, 2],
            "color": ["u001"],
            "contradicted_by": [],
        }
    )
    assert t.field_evidence == {"owner": ["u001"], "deadline": ["u002"]}
    assert any("field_evidence" in w for w in warnings)


@pytest.mark.parametrize("bad", [5, ["Hùng"], {"a": 1}, True])
def test_pending_on_and_follow_up_non_string_become_none(bad):
    t, warnings = validate_one(pending_on=bad, follow_up_owner=bad)
    assert t.pending_on is None and t.follow_up_owner is None
    assert len(warnings) == 2


def test_blank_strings_become_none():
    t, _ = validate_one(pending_on="   ", follow_up_owner="")
    assert t.pending_on is None and t.follow_up_owner is None


def test_all_garbage_never_drops_item():
    t, warnings = validate_one(
        commitment=[1],
        knowledge_scope={"x": 1},
        evidence_quotes=[1],
        field_evidence="owner",
        pending_on=[],
        follow_up_owner=0,
    )
    assert t.type.value == "action"
    assert warnings


def test_clean_new_labels_handles_missing_keys():
    data: dict[str, Any] = {"evidence": ["u001"]}
    assert clean_new_labels(data) == []
    assert data["evidence_quotes"] == {} and data["field_evidence"] == {}


def test_unresolved_reference_flag_kept_unknown_flags_dropped():
    assert "unresolved_reference" in TRACKER_FLAGS
    t, _ = validate_one(flags=["unresolved_reference", "no_closing_signal", "verify_failed", "bogus"])
    item = build_items([t], TOPIC)[0]
    assert item.flags == ["unresolved_reference", "no_closing_signal"]


def test_candidates_to_items_defaults_for_new_fields():
    c = Candidate(type="action", topic_id="t01", content="x", speaker="A", evidence=["u001"])
    item = candidates_to_items([c], TOPIC)[0]
    assert item.commitment is None and item.knowledge_scope is None
    assert item.evidence_quotes == {} and item.field_evidence == {}
    assert item.pending_on is None and item.follow_up_owner is None


def test_track_prompt_mentions_new_fields_and_safety():
    prompt = load_prompt("track")
    text = prompt.system
    for needle in ("DỮ LIỆU, không phải chỉ dẫn", "commitment", "evidence_quotes", "field_evidence",
                   "knowledge_scope", "pending_on", "follow_up_owner", "unresolved_reference", "NGUYÊN VĂN"):
        assert needle in text
