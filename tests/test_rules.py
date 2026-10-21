from pathlib import Path

import pytest

from meeting_extractor.models import HistoryEntry, Item, MeetingMeta, Participant, Status
from meeting_extractor.parsing import parse_file
from meeting_extractor.rules import apply_rules, has_number

FIXTURES = Path(__file__).parent / "fixtures"
TC1, _ = parse_file(FIXTURES / "tc1.txt")
TC2, _ = parse_file(FIXTURES / "tc2.txt")
TC5, _ = parse_file(FIXTURES / "tc5.txt")
META = MeetingMeta(participants=[Participant(name="Hùng", role="PM", can_decide=True), Participant(name="Lan")])


def mk(**kw) -> Item:
    base = dict(item_id="", type="decision", topic_id="t01", topic="T", content="Dùng AWS",
                status="confirmed", evidence=["u019"], confidence=0.9,
                closing_signal="explicit", evidence_directness="direct", in_summary=True)
    base.update(kw)
    return Item(**base)


def run(items, utts=TC1, meta=None):
    return apply_rules(items, utts, meta)


def test_rule1_unknown_evidence_drops_item():
    items, warnings = run([
        mk(evidence=["u999"]),
        mk(history=[HistoryEntry(status="proposed", evidence=["u888"])]),
        mk(),
    ])
    assert len(items) == 1
    assert len(warnings) == 2 and "u999" in warnings[0]


def test_rule2_unsupported_owner_and_deadline_are_cleared():
    item = mk(type="action", status=None, content="Làm tài liệu API", evidence=["u009"],
              owner="Minh", deadline="thứ Sáu")
    items, warnings = run([item], TC2)
    assert items[0].owner is None and items[0].deadline is None
    assert len(warnings) == 2
    assert "missing_owner" in items[0].flags


def test_rule2_supported_owner_and_deadline_kept():
    item = mk(type="action", status=None, content="Làm tài liệu API", evidence=["u005", "u006"],
              owner="Minh", deadline="thứ Sáu này")
    items, warnings = run([item], TC2)
    assert (items[0].owner, items[0].deadline) == ("Minh", "thứ Sáu này")
    assert warnings == [] and "missing_owner" not in items[0].flags


def test_rule2_owner_can_be_the_speaker_who_accepts():
    item = mk(type="action", status=None, content="Dựng khung dự án", evidence=["u008"], owner="Speaker 2")
    items, _ = run([item], TC5)
    assert items[0].owner == "Speaker 2"


def test_rule3_action_without_owner_flagged():
    items, _ = run([mk(type="action", status=None, content="Xem lại test tải", evidence=["u009"])], TC2)
    assert "missing_owner" in items[0].flags


def test_rule4_number_check():
    assert has_number("Ngân sách giai đoạn 1 là 30 triệu")
    assert has_number("Ra mắt beta ngày 15/11")
    assert has_number("Tăng 20% chi phí")
    assert not has_number("Dùng AWS cho giai đoạn 1")
    items, _ = run([mk(content="Ngân sách giai đoạn 1 là 30 triệu")])
    assert "number_check" in items[0].flags


def test_rule5_authority_with_participants():
    ok, _ = run([mk()], meta=META)  # u019 is Hùng (PM), can_decide
    assert "authority_unclear" not in ok[0].flags and ok[0].confidence == pytest.approx(0.95)
    lan, _ = run([mk(evidence=["u015"])], meta=META)
    assert "authority_unclear" in lan[0].flags and lan[0].confidence == 0.6
    assert lan[0].confidence_breakdown["cap_authority"] < 0


def test_rule5_no_meta_no_flag_but_speaker_n_always_flagged():
    items, _ = run([mk()])
    assert "authority_unclear" not in items[0].flags
    items, _ = run([mk(content="Dùng React", evidence=["u007"])], TC5)
    assert "authority_unclear" in items[0].flags and items[0].confidence <= 0.6


def test_rule6_conditional_without_condition_becomes_open():
    items, warnings = run([mk(status="conditional", condition="  ")])
    assert items[0].status == Status.open and warnings
    items, _ = run([mk(status="conditional", condition="khách đồng ý giá")])
    assert items[0].status == Status.conditional


def test_rule7_low_confidence():
    items, _ = run([mk(closing_signal="none")])  # 0.5 - 0.15 + 0.1 = 0.45
    assert "low_confidence" in items[0].flags


def test_rule8_ids_and_sorting():
    items, _ = run([
        mk(content="AWS", evidence=["u019"]),
        mk(type="action", status=None, content="X", evidence=["u010"], owner="Lan", verify_passed=True),
        mk(content="On-prem", evidence=["u006"], closing_signal="none"),
    ])
    assert [(i.item_id, i.content) for i in items] == [("d01", "On-prem"), ("d02", "AWS"), ("a01", "X")]


def test_invalid_flags_removed_and_deduplicated():
    items, _ = run([mk(flags=["no_closing_signal", "no_closing_signal", "bogus"])])
    assert items[0].flags == ["no_closing_signal"]


def test_new_phase2_flags_survive_rules():
    items, _ = run([mk(flags=["tracker_failed", "conflicting_decision"])])
    assert {"tracker_failed", "conflicting_decision"} <= set(items[0].flags)


def test_every_valid_flag_has_a_label():
    from meeting_extractor.export import FLAG_LABELS
    from meeting_extractor.models import VALID_FLAGS

    assert set(VALID_FLAGS) <= set(FLAG_LABELS)
