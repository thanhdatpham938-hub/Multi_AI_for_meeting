"""S2: code signals in rules.apply_rules (PLAN_SIGNALS.md sections 4-5, 14-19). Offline, no LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from meeting_extractor.conflicts import sibling_pairs
from meeting_extractor.models import HistoryEntry, Item, MeetingMeta, Participant, Utterance
from meeting_extractor.parsing import load_meta, parse_file
from meeting_extractor.rules import apply_rules
from meeting_extractor.signals import tag_transcript, tags_of

ROOT = Path(__file__).resolve().parent.parent
LONG = ROOT / "test_cases_3_muc_do (1)"
FIXTURES = ROOT / "tests" / "fixtures"


# ------------------------------------------------------------------ helpers


def utts(*lines: tuple[str, str]) -> list[Utterance]:
    return [Utterance(id=f"u{i:03d}", time=f"{i:02d}:00", speaker=s, text=t) for i, (s, t) in enumerate(lines, 1)]


def mk(content: str = "Dùng AWS", evidence: list[str] | None = None, **kw) -> Item:
    base = dict(
        item_id="", type="decision", topic_id="t01", topic="T", content=content, status="confirmed",
        evidence=evidence or ["u001"], confidence=0.9, closing_signal="explicit",
        evidence_directness="direct", in_summary=True,
    )  # fmt: skip
    base.update(kw)
    return Item(**base)


def real_case(name: str) -> tuple[list[Utterance], MeetingMeta]:
    d = next(LONG.glob(f"{name}_*"))
    utterances, _ = parse_file(d / "transcript.txt")
    return utterances, load_meta(d / "meeting_meta.json")


def tc(name: str, with_meta: bool = True) -> tuple[list[Utterance], MeetingMeta | None]:
    utterances, _ = parse_file(FIXTURES / f"{name}.txt")
    meta_path = FIXTURES / f"{name}.meta.json"
    return utterances, (load_meta(meta_path) if with_meta and meta_path.exists() else None)


def by_content(items: list[Item], content: str) -> Item:
    return next(i for i in items if i.content == content)


def notes(item: Item) -> dict[str, dict]:
    return {n["rule"]: n for n in item.signal_check.get("notes", [])}


def state(items: list[Item]) -> list[tuple]:
    return [
        (i.item_id, i.status, tuple(i.flags), i.confidence, i.evidence, i.owner,
         [(h.status, h.content, h.reason, tuple(h.evidence)) for h in i.history], i.signal_check)
        for i in items
    ]  # fmt: skip


def tags_at(u: list[Utterance], uid: str) -> set[str]:
    return tags_of(tag_transcript(u, None)[uid])


# ------------------------------------------------------------------ table rows 1-11


def test_row1_group_b_closing_is_demoted_with_history_step():
    u = utts(("Nam", "Hay bỏ luôn tính năng chat cho nhanh, haha."), ("Lan", "Ừ."))
    assert "DUA" in tags_at(u, "u001")
    items, _ = apply_rules([mk("Bỏ tính năng chat", ["u001", "u002"])], u)
    it = items[0]
    assert it.status.value == "proposed" and "signal_mismatch" in it.flags
    assert it.history[-1].reason.startswith("Code: câu u002 có dấu hiệu") and it.history[-1].evidence == ["u002"]
    assert it.confidence_breakdown["signal_strong_conflict"] == -0.25
    assert it.signal_check["closing_utterance"] == "u002" and "NGU_CANH_DUA" in it.signal_check["tags"]
    assert notes(it)["group_b"]["utterance"] == "u002"


def test_row1_question_with_close_word_is_demoted_but_question_plus_clear_close_is_not():
    q = utts(("Hùng", "Hay là mình chốt dùng AWS nhỉ?"))
    assert {"CHOT_RO", "GIA_DINH"} <= tags_at(q, "u001")
    assert apply_rules([mk()], q)[0][0].status.value == "proposed"

    both = utts(("Hùng", "Chốt vậy nhé. Có ai phản đối không?"))
    assert {"CHOT_RO", "CAU_HOI"} <= tags_at(both, "u001")
    it = apply_rules([mk()], both)[0][0]
    assert it.status.value == "confirmed"  # a sub-sentence is a clean "chốt"
    assert "signal_mismatch" in it.flags and it.confidence_breakdown["signal_weak_conflict"] == -0.15
    assert it.history == []


def test_row2_clear_close_is_left_alone():
    u = utts(("Hùng", "OK, vậy mình chốt dùng AWS nhé."))
    it = apply_rules([mk()], u)[0][0]
    assert it.status.value == "confirmed" and it.flags == [] and it.confidence >= 0.8
    assert it.signal_check["notes"] == [] and "CHOT_RO" in it.signal_check["tags"]


def test_row3_task_like_decision_gets_possible_action_and_cap():
    u, meta = real_case("case2")
    item = mk("Ngọc lên kịch bản series 'một ngày với TeaGo', tuần sau gửi Phương xem", ["u065"])
    it = apply_rules([item], u, meta)[0][0]
    assert it.status.value == "confirmed" and "possible_action" in it.flags and it.confidence <= 0.65
    assert it.confidence_breakdown["cap_possible_action"] < 0 or it.confidence_breakdown["base"] <= 0.65
    assert notes(it)["possible_action"]["utterance"] == "u065"


def test_row3_needs_task_like_content():
    u, meta = real_case("case2")
    it = apply_rules([mk("Làm series TeaGo", ["u065"])], u, meta)[0][0]  # content does not start with a name
    assert "possible_action" not in it.flags


def test_row4_implicit_agreement_with_content_is_left_alone():
    u = utts(("Hùng", "Ok, làm trang đích đơn giản thôi."))
    assert "CHOT_NGAM" in tags_at(u, "u001")
    it = apply_rules([mk("Làm trang đích đơn giản")], u)[0][0]
    assert it.status.value == "confirmed" and it.flags == []


def test_row5_bare_agreement_caps_at_06():
    u = utts(("Minh", "Anh ơi, thứ Năm em xin nghỉ chiều được không ạ?"), ("Hùng", "Được em, không sao."))
    assert "DONG_Y_NGAN" in tags_at(u, "u002")
    it = apply_rules([mk("Duyệt nghỉ phép", ["u001", "u002"])], u)[0][0]
    assert it.status.value == "confirmed" and "signal_mismatch" in it.flags and it.confidence <= 0.6
    assert it.confidence_breakdown["cap_signal_short_ack"] < 0 and notes(it)["short_ack"]["utterance"] == "u002"


def test_row6_weak_frame_costs_015():
    u = utts(("Lan", "Để em hỏi sếp đã rồi báo lại."))
    assert "HOAN" in tags_at(u, "u001")
    it = apply_rules([mk()], u)[0][0]
    assert it.status.value == "confirmed" and "signal_mismatch" in it.flags
    assert it.confidence_breakdown["signal_weak_conflict"] == -0.15 and notes(it)["weak"]["utterance"] == "u001"


def test_row7_no_tag_at_all_caps_at_065():
    u = utts(("Hùng", "AWS cho hạ tầng server."))
    assert tags_at(u, "u001") == set()
    it = apply_rules([mk()], u)[0][0]
    assert it.status.value == "confirmed" and it.confidence <= 0.65 and "low_confidence" not in it.flags or it.confidence < 0.7
    assert it.confidence_breakdown["cap_signal_unverified"] < 0 and notes(it)["unverified"]["utterance"] == "u001"


def test_row8_open_decision_with_clear_close_word_asks_the_reviewer():
    u = utts(("Hùng", "Chốt vậy nhé."))
    it = apply_rules([mk(status="open")], u)[0][0]
    assert it.status.value == "open" and "possible_closing" in it.flags
    assert "signal_strong_conflict" not in it.confidence_breakdown and notes(it)["possible_closing"]["utterance"] == "u001"


def test_row9_deferred_with_deferral_frame_is_left_alone():
    u = utts(("Hùng", "Cái này tuần sau bàn tiếp."))
    it = apply_rules([mk(status="deferred")], u)[0][0]
    assert it.status.value == "deferred" and it.flags == [] and it.signal_check["notes"] == []


def test_row10_action_whose_evidence_is_only_questions():
    u = utts(("Hùng", "Ai làm tài liệu được không?"))
    act = mk("Làm tài liệu", type="action", status=None, owner=None, commitment="assigned")
    it = apply_rules([act], u)[0][0]
    assert "signal_mismatch" in it.flags and it.confidence_breakdown["signal_weak_conflict"] == -0.15
    ok_u = utts(("Hùng", "Minh làm tài liệu API, thứ Sáu gửi anh nhé."), ("Minh", "Dạ vâng."))
    ok = apply_rules([mk("Làm tài liệu API", type="action", status=None, owner="Minh", commitment="assigned")], ok_u)[0][0]
    assert "signal_mismatch" not in ok.flags


def test_row11_everything_else_does_nothing():
    u = utts(("Hùng", "Ai làm tài liệu được không?"))
    it = apply_rules([mk("Tài liệu", type="knowledge", status=None, evidence=["u001"])], u)[0][0]
    assert it.flags == [] and it.signal_check == {}


def test_tam_thoi_confirmed_decision_is_capped():
    u = utts(("Hùng", "Tạm chốt dùng AWS nhé."))
    it = apply_rules([mk()], u)[0][0]
    assert "signal_mismatch" in it.flags and it.confidence <= 0.65


# ------------------------------------------------------------------ P3 reversal (4 real cases)


def test_p3_case5_rollback_u025_then_khoan_u027():
    u, meta = real_case("case5")
    it = apply_rules([mk("Rollback về 3.2 tối nay, Thảo làm", ["u025"])], u, meta)[0][0]
    assert it.status.value == "confirmed" and "possible_superseded" in it.flags and it.confidence <= 0.6
    assert it.confidence_breakdown["signal_reversal_penalty"] == -0.2
    assert it.history[-1].reason.startswith("Code: ngay sau câu chốt có câu u027")
    assert notes(it)["reversal"]["utterance"] == "u027"


def test_p3_case4_u045_without_participants_and_with_them():
    u, meta = real_case("case4")
    item = mk("In 5.000 tờ rơi", ["u045"])
    it = apply_rules([item], u, None)[0][0]  # no list of participants: A1 off, P3 on
    assert it.status.value == "confirmed" and "possible_superseded" in it.flags and notes(it)["reversal"]["utterance"] == "u046"
    # With the list, Mai cannot decide and nobody with authority confirms: A1 demotes instead (P3 only for `confirmed`).
    with_meta = apply_rules([item], u, meta)[0][0]
    assert with_meta.status.value == "proposed" and "authority_unconfirmed" in with_meta.flags


def test_p3_case3_u086_then_hoi_lai_sep_and_u023_then_nhung():
    u, _ = real_case("case3")
    a = apply_rules([mk("Hợp đồng hai năm", ["u086"])], u)[0][0]
    assert "possible_superseded" in a.flags and notes(a)["reversal"]["utterance"] == "u087"
    b = apply_rules([mk("Theo phương án trong email", ["u022", "u023"])], u)[0][0]
    assert "possible_superseded" in b.flags and notes(b)["reversal"]["utterance"] == "u024"


def test_p3_skips_reversal_the_item_already_cites_or_that_is_a_new_close():
    u, meta = real_case("case5")
    own = apply_rules([mk("Rollback về 3.2", ["u025", "u027"])], u, meta)[0][0]
    assert "possible_superseded" not in own.flags
    cited_in_history = mk("Rollback về 3.2", ["u025"], history=[HistoryEntry(status="superseded", evidence=["u027"])])
    assert "possible_superseded" not in apply_rules([cited_in_history], u, meta)[0][0].flags
    sentence = utts(("Hùng", "Chốt dùng AWS nhé."), ("Lan", "Khoan, chốt luôn đi."))
    assert {"DAO_NGUOC", "CHOT_RO"} <= tags_at(sentence, "u002")
    assert "possible_superseded" not in apply_rules([mk()], sentence)[0][0].flags


def test_p3_does_not_use_own_reversal_to_reject_a_real_close():
    u, meta = real_case("case5")  # u031 "Ok, vậy không rollback nữa..." carries DAO_NGUOC itself
    it = apply_rules([mk("Hotfix tăng pool kết nối, Phúc làm", ["u031"])], u, meta)[0][0]
    assert it.status.value == "confirmed" and "possible_superseded" not in it.flags


# ------------------------------------------------------------------ P1 narrow siblings


def test_p1_two_confirmed_answers_to_the_same_issue():
    u = utts(("Hùng", "Chốt ngân sách marketing quý này là 100 triệu."), ("Lan", "Ờ."), ("Hùng", "Chốt ngân sách marketing quý này tăng lên 150 triệu."))
    first, second = mk("Ngân sách marketing quý này là 100 triệu", ["u001"]), mk("Ngân sách marketing quý này tăng lên 150 triệu", ["u003"])
    assert len(sibling_pairs([first, second])) == 1
    items, _ = apply_rules([first, second], u)
    early, late = by_content(items, first.content), by_content(items, second.content)
    assert "possible_superseded" in early.flags and early.confidence <= 0.65
    assert early.confidence_breakdown["cap_superseded_sibling"] < 0
    assert notes(early)["sibling"]["utterance"] == "u003"
    assert "possible_superseded" not in late.flags and early.status.value == "confirmed"


def test_p1_different_issues_in_one_topic_are_not_flagged():
    u, meta = real_case("case2")
    logo, landing = mk("Duyệt logo mới bản màu xanh lá", ["u060"]), mk("Làm trang đích đơn giản thôi", ["u092"])
    assert sibling_pairs([logo, landing]) == []
    items, _ = apply_rules([logo, landing], u, meta)
    assert all("possible_superseded" not in i.flags for i in items)


# ------------------------------------------------------------------ A1 / A2


def test_a1_case2_u022_khoa_cannot_decide_and_phuong_says_khoan():
    u, meta = real_case("case2")
    it = apply_rules([mk("Mời Mai Chi làm KOL", ["u022"])], u, meta)[0][0]
    assert it.status.value == "proposed" and "authority_unconfirmed" in it.flags
    assert it.history[-1].reason == "Code: Khoa không có quyền chốt và không ai có quyền xác nhận trong 3 câu sau"
    assert notes(it)["authority_unconfirmed"]["utterance"] == "u022"


def test_a1_case4_u045_mai_cannot_decide():
    u, meta = real_case("case4")
    it = apply_rules([mk("In 5.000 tờ rơi", ["u045"])], u, meta)[0][0]
    assert it.status.value == "proposed" and "authority_unconfirmed" in it.flags


def test_a1_tc3_nam_then_hung_confirms_and_u020_becomes_the_close():
    u, meta = tc("tc3")
    assert meta is not None
    it = apply_rules([mk("Ra mắt bản beta ngày 15/11", ["u019"])], u, meta)[0][0]
    assert it.status.value == "confirmed" and it.evidence == ["u019", "u020"]
    assert "authority_unclear" not in it.flags and "authority_unconfirmed" not in it.flags
    assert it.signal_check["closing_utterance"] == "u020" and notes(it)["authority_confirmed"]["utterance"] == "u020"
    assert it.confidence_breakdown["closer_can_decide"] == 0.15


def test_a2_no_participants_or_nobody_with_authority_keeps_the_old_behaviour():
    u, _ = real_case("case2")
    item = mk("Mời Mai Chi làm KOL", ["u022"])
    no_meta = apply_rules([item], u, None)[0][0]
    assert no_meta.status.value == "confirmed" and "authority_unconfirmed" not in no_meta.flags
    nobody = MeetingMeta(participants=[Participant(name="Khoa"), Participant(name="Phương")])
    assert apply_rules([item], u, nobody)[0][0].status.value == "confirmed"


def test_a1_anonymous_speakers_are_not_demoted():
    u = utts(("Speaker 1", "Chốt dùng React nhé."))
    meta = MeetingMeta(participants=[Participant(name="Hùng", can_decide=True)])
    it = apply_rules([mk("Dùng React")], u, meta)[0][0]
    assert it.status.value == "confirmed" and "authority_unclear" in it.flags and "authority_unconfirmed" not in it.flags


def _fuse_transcript(n_bad: int, n_good: int) -> tuple[list[Utterance], list[Item], MeetingMeta]:
    lines, items = [], []
    topics = ["ngân sách", "màu logo", "lịch họp", "nhà cung cấp", "tên miền", "gói bảo hành", "hợp đồng"]
    meta = MeetingMeta(participants=[Participant(name="Hùng", can_decide=True), Participant(name="Khoa")])
    for k in range(n_bad + n_good):
        speaker = "Khoa" if k < n_bad else "Hùng"
        lines += [(speaker, f"Chốt phương án {topics[k]} nhé."), ("Lan", "Dạ."), ("Lan", "Vâng."), ("Lan", "Em ghi lại.")]
        items.append(mk(f"Phương án {topics[k]}", [f"u{4 * k + 1:03d}"]))
    return utts(*lines), items, meta


def test_a1_fuse_trips_when_it_would_demote_over_40_percent():
    u, items, meta = _fuse_transcript(n_bad=3, n_good=2)  # 3/5 = 60%
    out, warnings = apply_rules(items, u, meta)
    assert all(i.status.value == "confirmed" for i in out)
    assert any(w.startswith("[Cảnh báo cờ]") and "A1" in w for w in warnings)


def test_a1_runs_below_the_fuse():
    u, items, meta = _fuse_transcript(n_bad=1, n_good=4)  # 1/5 = 20%
    out, warnings = apply_rules(items, u, meta)
    assert sum(i.status.value == "proposed" for i in out) == 1
    assert not any("A1" in w for w in warnings)


# ------------------------------------------------------------------ VO_CHU / XUNG_PHONG


def test_vo_chu_open_call_clears_a_guessed_owner():
    # The owner only "speaks" the open call itself and is never named: nobody actually took the task.
    u = utts(("Hùng", "Ừ."), ("Tuấn", "Cần ai đó viết brief nữa không nhỉ?"))
    act = mk("Viết brief gửi agency", ["u002"], type="action", status=None, owner="Tuấn")
    it, warnings = apply_rules([act], u)
    assert it[0].owner is None and "missing_owner" in it[0].flags
    assert any("Tuấn" in w for w in warnings) and notes(it[0])["no_owner"]["utterance"] == "u002"


def test_vo_chu_does_not_clear_owner_who_answers_the_open_call():
    u = utts(("Hùng", "Có ai nhận phần tài liệu API không?"), ("Minh", "Em làm nhé."))
    act = mk("Làm tài liệu API", ["u001", "u002"], type="action", status=None, owner="Minh",
             field_evidence={"owner": ["u002"]})  # fmt: skip
    it, warnings = apply_rules([act], u)
    assert it[0].owner == "Minh" and "missing_owner" not in it[0].flags and not warnings
    assert "no_owner" not in notes(it[0])
    again, _ = apply_rules(it, u)
    assert again[0].owner == "Minh"


def test_case2_u069_u070_owner_removed_by_volunteer_rule_when_both_cited():
    u, meta = real_case("case2")
    act = mk("Tuấn viết brief gửi agency quay video", ["u069", "u070"], type="action", status=None, owner="Tuấn")
    it, warnings = apply_rules([act], u, meta)
    assert it[0].owner is None and "missing_owner" in it[0].flags
    assert any("Tuấn" in w for w in warnings) and notes(it[0])["volunteer"]["utterance"] == "u070"


def test_vo_chu_keeps_owner_when_a_cited_sentence_names_him():
    u = utts(("Hùng", "Có ai nhận phần test không?"), ("Hùng", "Minh làm nhé."))
    act = mk("Minh làm phần test", ["u001", "u002"], type="action", status=None, owner="Minh")
    it = apply_rules([act], u)[0][0]
    assert it.owner == "Minh" and "missing_owner" not in it.flags


def test_xung_phong_case2_u070_u071_owner_removed():
    u, meta = real_case("case2")
    act = mk("Tuấn hỗ trợ viết brief gửi agency", ["u070", "u071"], type="action", status=None, owner="Tuấn",
             field_evidence={"owner": ["u070"]})  # fmt: skip
    it, warnings = apply_rules([act], u, meta)
    assert it[0].owner is None and "missing_owner" in it[0].flags
    assert any("xung phong" in w for w in warnings) and notes(it[0])["volunteer"]["utterance"] == "u070"


def test_xung_phong_kept_when_someone_with_authority_assigns():
    u = utts(("Tuấn", "Em có thể hỗ trợ nếu cần."), ("Phương", "Ok, Tuấn làm phần brief nhé."))
    meta = MeetingMeta(participants=[Participant(name="Phương", can_decide=True), Participant(name="Tuấn")])
    act = mk("Tuấn làm brief", ["u001", "u002"], type="action", status=None, owner="Tuấn", field_evidence={"owner": ["u001"]})
    assert apply_rules([act], u, meta)[0][0].owner == "Tuấn"


# ------------------------------------------------------------------ N1


def test_n1_number_missing_from_the_cited_sentences():
    u = utts(("Hùng", "Chốt ngân sách 300 triệu nhé."))
    it = apply_rules([mk("Ngân sách 200 triệu")], u)[0][0]
    assert "number_not_in_evidence" in it.flags and it.confidence_breakdown["number_not_in_evidence_penalty"] == -0.2
    assert it.signal_check["missing_numbers"] == ["200"] and "number" in notes(it)


@pytest.mark.parametrize(
    ("content", "text"),
    [
        ("In 5.000 tờ rơi", "Chốt in 5000 tờ rơi nhé."),
        ("Ngân sách 1,5 tỷ", "Chốt ngân sách 1.5 tỷ nhé."),
        ("Ra mắt ngày 15/11", "Chốt ra mắt ngày 15/11 nhé."),
        ("Ra mắt ngày 15 tháng 11", "Chốt ra mắt 15/11 nhé."),
        ("Dùng AWS", "Chốt dùng AWS nhé."),  # no digit in the content: skipped
    ],
)
def test_n1_normalised_numbers_match(content: str, text: str):
    it = apply_rules([mk(content)], utts(("Hùng", text)))[0][0]
    assert "number_not_in_evidence" not in it.flags and "missing_numbers" not in it.signal_check


def test_n1_number_found_only_in_history_evidence_counts():
    u = utts(("Hùng", "Chốt dùng AWS nhé."), ("Lan", "Ngân sách 200 triệu thôi."))
    it = apply_rules([mk("Ngân sách 200 triệu", history=[HistoryEntry(status="proposed", evidence=["u002"])])], u)[0][0]
    assert "number_not_in_evidence" not in it.flags


# ------------------------------------------------------------------ merge duplicates


def test_merge_coopmart_pair():
    u, meta = real_case("case2")
    short = mk("Sampling tại Coopmart", ["u132"], confidence=0.9)
    long_ = mk("Sampling tại Coopmart thay vì Big C do phí cao gấp đôi", ["u131", "u132"], confidence=0.9)
    items, _ = apply_rules([short, long_], u, meta)
    assert len(items) == 1
    merged = items[0]
    assert merged.evidence == ["u131", "u132"] and "merged" in notes(merged)
    assert any((h.reason or "").startswith("Code: gộp với mục trùng") for h in merged.history)


def test_merge_requires_same_type_status_evidence_and_overlap():
    u, meta = real_case("case2")
    base = mk("Sampling tại Coopmart", ["u132"])
    different_status = mk("Sampling tại Coopmart thay vì Big C", ["u131", "u132"], status="proposed")
    different_text = mk("Thuê freelancer dựng video", ["u131", "u132"])
    other_evidence = mk("Sampling tại Coopmart thay vì Big C", ["u120"])
    assert len(apply_rules([base, different_status, different_text, other_evidence], u, meta)[0]) == 4


def test_merge_keeps_the_higher_score():
    u = utts(("Hùng", "Chốt dùng AWS nhé."), ("Lan", "Dạ."))
    weak = mk("Dùng AWS", ["u001"], closing_signal="none", in_summary=None)
    strong = mk("Dùng AWS cho hạ tầng", ["u001", "u002"])
    items, _ = apply_rules([weak, strong], u)
    assert len(items) == 1 and items[0].content == "Dùng AWS cho hạ tầng"


# ------------------------------------------------------------------ run-level warnings


def _closing_ack_run(n: int) -> tuple[list[Utterance], list[Item]]:
    names = ["ngân sách", "màu logo", "lịch họp", "nhà cung cấp", "tên miền", "gói bảo hành"]
    u = utts(*[("Hùng", "Ừ.") for _ in range(n)])
    return u, [mk(f"Phương án {names[k]}", [f"u{k + 1:03d}"]) for k in range(n)]


def test_run_warning_when_over_30_percent_of_decisions_mismatch():
    u, items = _closing_ack_run(5)
    _, warnings = apply_rules(items, u)
    assert any(w.startswith("[Cảnh báo cờ]") and "lệch tín hiệu" in w for w in warnings)


def test_run_warning_needs_at_least_five_decisions_and_enough_flags():
    u, items = _closing_ack_run(3)
    assert not any(w.startswith("[Cảnh báo cờ]") for w in apply_rules(items, u)[1])
    u2 = utts(*[("Hùng", "Chốt dùng AWS nhé.")] * 5)
    clean = [mk(f"Phương án {k}", [f"u{k + 1:03d}"]) for k in range(5)]
    assert not any(w.startswith("[Cảnh báo cờ]") for w in apply_rules(clean, u2)[1])


def test_run_warning_for_possible_superseded():
    lines = []
    for _ in range(5):
        lines += [("Hùng", "Chốt dùng AWS nhé."), ("Lan", "Khoan đã.")]
    items = [mk(f"Phương án số {k}", [f"u{2 * k + 1:03d}"]) for k in range(5)]
    _, warnings = apply_rules(items, utts(*lines))
    assert any("có thể đã bị thay thế" in w for w in warnings)


# ------------------------------------------------------------------ idempotence


def test_apply_rules_is_idempotent_on_a_mixed_bag():
    u, meta = real_case("case2")
    items = [
        mk("Không mời Sơn Tùng vì ngân sách có hạn", ["u029"]),  # row 1
        mk("Mời Mai Chi làm KOL", ["u022"]),  # A1 demotion
        mk("Ngọc lên kịch bản series", ["u065"]),  # row 3
        mk("Ngọc tự quyết bài đăng", ["u068"]),
        mk("Sampling tại Coopmart", ["u132"]),  # merge pair
        mk("Sampling tại Coopmart thay vì Big C do phí cao gấp đôi", ["u131", "u132"]),
        mk("Làm trang đích đơn giản thôi", ["u092"]),
        mk("Ngân sách 999 triệu", ["u092"]),  # N1
        mk("Tuấn hỗ trợ viết brief", ["u070", "u071"], type="action", status=None, owner="Tuấn",
           field_evidence={"owner": ["u070"]}),  # fmt: skip
        mk("Tuấn viết brief", ["u069"], type="action", status=None, owner="Tuấn"),
    ]
    once, w1 = apply_rules(items, u, meta)
    twice, _ = apply_rules(once, u, meta)
    assert state(once) == state(twice)
    # Items demoted by code keep their note and penalty on the second run, without a second history step.
    sun = by_content(twice, "Không mời Sơn Tùng vì ngân sách có hạn")
    assert sun.status.value == "proposed" and "group_b" in notes(sun)
    assert sun.confidence_breakdown["signal_strong_conflict"] == -0.25
    assert sum((h.reason or "").startswith("Code:") for h in sun.history) == 1
    mai = by_content(twice, "Mời Mai Chi làm KOL")
    assert "authority_unconfirmed" in mai.flags and sum((h.reason or "").startswith("Code:") for h in mai.history) == 1
    assert len([i for i in twice if i.content.startswith("Sampling")]) == 1


def test_idempotent_with_authority_confirmation_and_reversal():
    u3, m3 = tc("tc3")
    once, _ = apply_rules([mk("Ra mắt bản beta ngày 15/11", ["u019"])], u3, m3)
    assert state(once) == state(apply_rules(once, u3, m3)[0])
    assert "authority_confirmed" in notes(once[0])
    u5, m5 = real_case("case5")
    once5, _ = apply_rules([mk("Rollback về 3.2", ["u025"])], u5, m5)
    assert state(once5) == state(apply_rules(once5, u5, m5)[0])
    assert len([h for h in once5[0].history if (h.reason or "").startswith("Code:")]) == 1


def test_does_not_mutate_inputs_and_tolerates_malformed_signal_check():
    u = utts(("Hùng", "Chốt dùng AWS nhé."))
    item = mk(signal_check={"notes": "garbage"})
    before = item.model_dump()
    items, _ = apply_rules([item], u)
    assert item.model_dump() == before and items[0].status.value == "confirmed"


# ------------------------------------------------------------------ review fixes: merge never loses data


def _merge_run(a: Item, b: Item, u: list[Utterance]) -> tuple[list[Item], list[str]]:
    return apply_rules([a, b], u)


def test_merge_fills_owner_and_deadline_from_the_loser_and_warns():
    u = utts(("Hùng", "Minh làm tài liệu API, thứ Sáu gửi anh nhé."))
    rich = mk("Làm tài liệu API", ["u001"], type="action", status=None, owner="Minh", deadline="thứ Sáu")
    bare = mk("Làm tài liệu API cho dự án", ["u001"], type="action", status=None, confidence=0.95)
    items, warnings = _merge_run(rich, bare, u)
    assert len(items) == 1
    assert items[0].owner == "Minh" and items[0].deadline == "thứ Sáu" and "missing_owner" not in items[0].flags
    assert any(w.startswith("Gộp hai mục trùng") for w in warnings)


def test_merge_never_combines_different_owners_deadlines_conditions_or_figures():
    u = utts(("Hùng", "Lan và Nam làm tài liệu API, thứ Sáu hoặc thứ Hai."))
    lan = mk("Làm tài liệu API", ["u001"], type="action", status=None, owner="Lan")
    nam = mk("Làm tài liệu API", ["u001"], type="action", status=None, owner="Nam")
    items, warnings = _merge_run(lan, nam, u)
    assert {i.owner for i in items} == {"Lan", "Nam"} and not any("Gộp" in w for w in warnings)

    d1 = mk("Nộp tài liệu", ["u001"], type="action", status=None, owner="Lan", deadline="thứ Sáu")
    d2 = mk("Nộp tài liệu", ["u001"], type="action", status=None, owner="Lan", deadline="thứ Hai")
    assert len(_merge_run(d1, d2, u)[0]) == 2

    cu = utts(("Hùng", "Nếu khách đồng ý giá mới hoặc nếu khách đồng ý giá cũ thì ký gói B."))
    c1 = mk("Ký gói B", ["u001"], status="conditional", condition="khách đồng ý giá mới")
    c2 = mk("Ký gói B", ["u001"], status="conditional", condition="khách đồng ý giá cũ")
    assert len(_merge_run(c1, c2, cu)[0]) == 2

    du = utts(("Hùng", "Ra mắt beta ngày 15/11 hay ngày 1/11 nhỉ."))
    n1 = mk("Ra mắt beta ngày 15/11", ["u001"], status="proposed")
    n2 = mk("Ra mắt beta ngày 1/11", ["u001"], status="proposed")
    assert len(_merge_run(n1, n2, du)[0]) == 2


def test_merge_same_condition_still_merges_and_fills_a_missing_condition():
    cu = utts(("Hùng", "Nếu khách đồng ý giá mới thì ký gói B."))
    c1 = mk("Ký gói B", ["u001"], status="conditional", condition="khách đồng ý giá mới")
    c2 = mk("Ký gói B với khách", ["u001"], status="conditional", condition="khách đồng ý giá mới")
    assert len(_merge_run(c1, c2, cu)[0]) == 1


def test_merge_prefers_the_longer_content_when_scores_are_close():
    u = utts(("Hùng", "Báo bên marketing về lịch ra mắt beta ngày 15/11 nhé."))
    short = mk("Báo bên marketing", ["u001"], type="action", status=None, owner="Hùng", confidence=0.9)
    long_ = mk("Báo bên marketing về lịch ra mắt beta ngày 15/11", ["u001"], type="action", status=None, owner="Hùng")
    items, _ = _merge_run(short, long_, u)
    assert len(items) == 1 and items[0].content == "Báo bên marketing về lịch ra mắt beta ngày 15/11"


# ------------------------------------------------------------------ review fixes: A1 and the closing utterance


def test_trailing_ok_does_not_outrank_an_earlier_close_by_someone_who_can_decide():
    u = utts(("Hùng", "Chốt dùng AWS nhé."), ("Lan", "Ok."))
    meta = MeetingMeta(participants=[Participant(name="Hùng", can_decide=True), Participant(name="Lan")])
    it = apply_rules([mk("Dùng AWS", ["u001", "u002"])], u, meta)[0][0]
    assert it.status.value == "confirmed" and it.flags == []
    assert it.signal_check["closing_utterance"] == "u001" and "short_ack" not in notes(it)
    assert it.confidence_breakdown.get("closer_can_decide") == 0.15


def test_a1_confirmed_by_a_cited_utterance_of_someone_who_can_decide():
    u = utts(("Lan", "Chốt dùng AWS nhé."), ("Hùng", "Ok, vậy cứ dùng cái đó thôi nhé."))
    meta = MeetingMeta(participants=[Participant(name="Hùng", can_decide=True), Participant(name="Lan")])
    it = apply_rules([mk("Dùng AWS", ["u001", "u002"])], u, meta)[0][0]
    assert it.status.value == "confirmed" and "authority_unclear" not in it.flags
    assert it.signal_check["closing_utterance"] == "u002" and "authority_confirmed" in notes(it)


# ------------------------------------------------------------------ review fixes: stable A1 fuse


def _blocks(kinds: list[str]) -> tuple[list[Utterance], list[Item], MeetingMeta]:
    """One 4-line block per decision. kinds: 'khoa' (cannot decide), 'hung' (can), 'joke' (Hùng, but not a real close)."""
    topics = ["ngân sách", "màu logo", "lịch họp", "nhà cung cấp", "tên miền", "gói bảo hành", "hợp đồng",
              "địa điểm", "tuyển dụng", "đào tạo", "bảo mật", "báo cáo"]  # fmt: skip
    meta = MeetingMeta(participants=[Participant(name="Hùng", can_decide=True), Participant(name="Khoa")])
    lines, items = [], []
    for k, kind in enumerate(kinds):
        text = f"Hay là chốt phương án {topics[k]} haha." if kind == "joke" else f"Chốt phương án {topics[k]} nhé."
        lines += [("Khoa" if kind == "khoa" else "Hùng", text), ("Lan", "Dạ."), ("Lan", "Vâng."), ("Lan", "Em ghi lại.")]
        items.append(mk(f"Phương án {topics[k]}", [f"u{4 * k + 1:03d}"]))
    return utts(*lines), items, meta


def test_a1_fuse_is_stable_across_passes_with_group_b_demotions():
    u, items, meta = _blocks(["joke"] * 3 + ["khoa"] * 4 + ["hung"] * 3)  # A1 would demote 4 of 10 = 40%: allowed
    once, warnings = apply_rules(items, u, meta)
    assert not any("A1" in w for w in warnings)
    assert sum(i.status.value == "proposed" for i in once) == 7 and sum("authority_unconfirmed" in i.flags for i in once) == 4
    twice, warnings2 = apply_rules(once, u, meta)
    assert state(once) == state(twice) and not any("A1" in w for w in warnings2)


def test_a1_fuse_trip_undoes_earlier_a1_demotions():
    u, items, meta = _blocks(["khoa"] + ["hung"] * 4 + ["khoa"] * 2)
    first, _ = apply_rules(items[:5], u, meta)  # 1 of 5: A1 applies
    assert sum("authority_unconfirmed" in i.flags for i in first) == 1
    second, warnings = apply_rules([*first, *items[5:]], u, meta)  # now 3 of 7 = 43%: the fuse trips
    assert any("A1" in w and w.startswith("[Cảnh báo cờ]") for w in warnings)
    assert all(i.status.value == "confirmed" and "authority_unconfirmed" not in i.flags for i in second)
    assert not any((h.reason or "").startswith("Code: Khoa") for i in second for h in i.history)
    assert state(second) == state(apply_rules(second, u, meta)[0])


def test_unstable_rules_add_a_warning(monkeypatch):
    from meeting_extractor import rules

    monkeypatch.setattr(rules, "MAX_PASSES", 1)
    u = utts(("Hùng", "Chốt dùng AWS nhé."))
    _, warnings = apply_rules([mk()], u)
    assert any(w.startswith("[Cảnh báo cờ]") and "chưa ổn định" in w for w in warnings)
