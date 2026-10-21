"""Mission 3 / M4B rules: commitment, decision deadline, quotes, field evidence, knowledge recheck."""

from meeting_extractor.models import Item, MeetingMeta, Participant, Utterance
from meeting_extractor.provenance import normalize_text, quote_matches
from meeting_extractor.rules import apply_rules, has_quantity

UTTS = [
    Utterance(id="u001", time="01:00", speaker="Ngọc", text="Em muốn chuyển sang gói mới, anh quyết giúp em."),
    Utterance(id="u002", time="01:10", speaker="Hùng (PM)", text="Phương tự quyết nhé, thứ Sáu này báo lại."),
    Utterance(id="u003", time="01:20", speaker="Phương", text="Dạ, em tự quyết luôn."),
    Utterance(id="u004", time="01:30", speaker="Minh", text="Em đã khởi động lại server rồi ạ."),
    Utterance(id="u005", time="01:40", speaker="Lan", text="Mỗi ngày hệ thống xử lý khoảng 5.000 đơn."),
    Utterance(id="u006", time="01:50", speaker="Nam", text="Giả sử mình thuê thêm 2 người, được không?"),
    Utterance(id="u007", time="02:00", speaker="Lan", text="Em có thể hỗ trợ nếu cần."),
    Utterance(id="u008", time="02:10", speaker="Hùng (PM)", text="Chốt dùng AWS, hạn 15/11."),
]
META = MeetingMeta(participants=[Participant(name="Hùng", can_decide=True), Participant(name="Ngọc")])


def mk(**kw) -> Item:
    base = dict(item_id="", type="action", topic_id="t01", topic="T", content="Việc X",
                evidence=["u002"], confidence=0.9)
    base.update(kw)
    return Item(**base)


def run(*items: Item, meta=None):
    return apply_rules(list(items), UTTS, meta)


# --- commitment -------------------------------------------------------------------------


def test_already_done_becomes_knowledge_and_keeps_owner():
    out, warns = run(mk(content="Khởi động lại server", evidence=["u004"], owner="Minh", commitment="already_done"))
    assert out[0].type.value == "knowledge" and out[0].owner == "Minh"
    assert "missing_owner" not in out[0].flags
    assert any("Khởi động lại server" in w and "Minh" in w for w in warns)


def test_hypothetical_becomes_open_issue_not_dropped():
    out, warns = run(mk(content="Thuê thêm 2 người", evidence=["u006"], commitment="hypothetical"))
    assert len(out) == 1 and out[0].type.value == "open_issue"
    assert any("giả định" in w and "Thuê thêm 2 người" in w for w in warns)


def test_volunteered_conditional_becomes_open_issue_keeping_name():
    out, warns = run(mk(content="Hỗ trợ", evidence=["u007"], owner="Lan", commitment="volunteered_conditional"))
    assert len(out) == 1 and out[0].type.value == "open_issue" and out[0].owner is None
    assert "missing_owner" not in out[0].flags
    assert "Lan" in out[0].content and "chưa được giao" in out[0].content
    assert any("Lan" in w and "chưa được giao" in w for w in warns)


def test_volunteered_conditional_without_owner_still_converted():
    out, _ = run(mk(content="Hỗ trợ", evidence=["u007"], commitment="volunteered_conditional"))
    assert out[0].type.value == "open_issue" and out[0].content == "Hỗ trợ"


def test_unknown_or_missing_commitment_is_ignored():
    for label in (None, "weird", "assigned", "accepted"):
        out, warns = run(mk(evidence=["u003"], owner="Phương", commitment=label))
        assert out[0].type.value == "action" and out[0].owner == "Phương" and warns == []


def test_commitment_only_applies_to_actions():
    out, _ = run(mk(type="request", evidence=["u004"], commitment="already_done"))
    assert out[0].type.value == "request"


def test_commitment_rules_are_idempotent():
    first, _ = run(mk(evidence=["u006"], commitment="hypothetical"))
    again, warns = apply_rules(first, UTTS)
    assert again[0].type.value == "open_issue" and warns == []


# --- decision deadline ------------------------------------------------------------------


def test_decision_deadline_dropped_with_warning():
    out, warns = run(mk(type="decision", status="confirmed", content="Dùng AWS", evidence=["u008"],
                        deadline="15/11"))
    assert out[0].deadline is None
    assert any("'15/11'" in w and "quyết định" in w for w in warns)


def test_action_deadline_untouched_and_number_checked():
    out, _ = run(mk(evidence=["u008"], owner="Hùng", deadline="15/11"))
    assert out[0].deadline == "15/11" and "number_check" in out[0].flags


def test_action_deadline_without_number_not_flagged():
    out, _ = run(mk(evidence=["u002"], owner="Phương", deadline="thứ Sáu"))
    assert "number_check" not in out[0].flags


# --- quotes -----------------------------------------------------------------------------


def test_normalize_keeps_diacritics_and_strips_edges():
    assert normalize_text("  “Chốt   vậy nhé!”  ") == "chốt vậy nhé"
    assert normalize_text("ma") != normalize_text("mà")
    assert quote_matches("chốt dùng AWS", "Chốt dùng AWS, hạn 15/11.")
    assert not quote_matches("chot dung AWS", "Chốt dùng AWS, hạn 15/11.")
    assert not quote_matches("   ", "abc")


def test_matching_quote_no_flag():
    out, warns = run(mk(evidence=["u003"], evidence_quotes={"u003": "Em tự quyết luôn"}))
    assert "quote_mismatch" not in out[0].flags and warns == []
    assert "quote_mismatch" not in out[0].confidence_breakdown


def test_mismatching_quote_flagged_kept_and_penalised():
    clean, _ = run(mk(evidence=["u003"]))
    out, warns = run(mk(evidence=["u003"], evidence_quotes={"u003": "em bịa ra"}))
    assert "quote_mismatch" in out[0].flags
    assert out[0].evidence_quotes == {"u003": "em bịa ra"}
    assert out[0].confidence_breakdown["quote_mismatch"] == -0.15
    assert out[0].confidence < clean[0].confidence
    assert any("không khớp" in w for w in warns)


def test_quote_for_uncited_id_dropped_with_warning():
    out, warns = run(mk(evidence=["u003"], evidence_quotes={"u003": "tự quyết", "u001": "chuyển sang"}))
    assert out[0].evidence_quotes == {"u003": "tự quyết"}
    assert "quote_mismatch" not in out[0].flags
    assert any("u001" in w for w in warns)


def test_stale_quote_mismatch_flag_cleared_on_rerun():
    out, _ = run(mk(evidence=["u003"], flags=["quote_mismatch"]))
    assert "quote_mismatch" not in out[0].flags


# --- field evidence ---------------------------------------------------------------------


def test_owner_from_field_evidence_name_in_source():
    # owner is only named in u002, which is not in `evidence`
    out, warns = run(mk(evidence=["u003"], owner="Phương", field_evidence={"owner": ["u002"]}))
    assert out[0].owner == "Phương" and warns == []


def test_owner_delegated_by_authority_to_previous_speaker():
    # source u002 (Hùng, can_decide) comes right after u001 by Ngọc -> Ngọc may own it
    out, _ = run(mk(evidence=["u003"], owner="Ngọc", field_evidence={"owner": ["u002"]}), meta=META)
    assert out[0].owner == "Ngọc"


def test_delegation_rejected_when_source_speaker_cannot_decide():
    meta = MeetingMeta(participants=[Participant(name="Hùng"), Participant(name="Ngọc")])
    out, warns = run(mk(evidence=["u003"], owner="Ngọc", field_evidence={"owner": ["u002"]}), meta=meta)
    assert out[0].owner is None and any("owner" in w for w in warns)


def test_delegation_without_meta_allows_any_named_speaker():
    out, _ = run(mk(evidence=["u003"], owner="Ngọc", field_evidence={"owner": ["u002"]}))
    assert out[0].owner == "Ngọc"


def test_owner_not_in_any_source_cleared():
    out, warns = run(mk(evidence=["u003"], owner="Hải", field_evidence={"owner": ["u002"]}))
    assert out[0].owner is None and "missing_owner" in out[0].flags and warns


def test_deadline_from_field_evidence():
    out, warns = run(mk(evidence=["u003"], owner="Phương", deadline="thứ Sáu này",
                        field_evidence={"deadline": ["u002"]}))
    assert out[0].deadline == "thứ Sáu này" and warns == []


def test_unknown_field_evidence_id_dropped_and_falls_back():
    out, warns = run(mk(evidence=["u003"], owner="Phương", field_evidence={"owner": ["u999"]}))
    assert out[0].field_evidence == {}
    assert out[0].owner == "Phương"  # speaker of the cited evidence u003 (old rule)
    assert any("u999" in w for w in warns)


def test_unknown_id_among_valid_ones_keeps_valid():
    out, _ = run(mk(evidence=["u003"], owner="Phương", field_evidence={"owner": ["u002", "u999"]}))
    assert out[0].field_evidence == {"owner": ["u002"]}


def test_no_field_evidence_falls_back_to_old_rule():
    out, warns = run(mk(evidence=["u003"], owner="Hải", deadline="mai"))
    assert out[0].owner is None and out[0].deadline is None and len(warns) == 2


# --- knowledge recheck ------------------------------------------------------------------


def test_has_quantity_forms():
    assert has_quantity("khoảng 5.000 đơn") and has_quantity("trong 24 giờ") and has_quantity("3.200 đơn")
    assert has_quantity("ngân sách 30 triệu")
    assert not has_quantity("server chạy ổn định")


def test_project_knowledge_with_quantity_needs_recheck():
    out, _ = run(mk(type="knowledge", content="Hệ thống xử lý 5.000 đơn mỗi ngày", evidence=["u005"],
                    knowledge_scope="project"))
    assert "needs_recheck" in out[0].flags


def test_knowledge_other_scope_or_no_number_no_recheck():
    a, _ = run(mk(type="knowledge", content="Hệ thống xử lý 5.000 đơn", evidence=["u005"],
                  knowledge_scope="reusable"))
    b, _ = run(mk(type="knowledge", content="Hệ thống ổn định", evidence=["u005"], knowledge_scope="project"))
    c, _ = run(mk(type="knowledge", content="Hệ thống xử lý 5.000 đơn", evidence=["u005"],
                  knowledge_scope="lạ"))
    assert all("needs_recheck" not in o[0].flags for o in (a, b, c))
