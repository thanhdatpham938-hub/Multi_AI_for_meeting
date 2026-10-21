"""4C – counter-evidence: later utterances that may contradict a decision."""

from meeting_extractor.agents.verifier import apply_contradiction, verify
from meeting_extractor.counter_evidence import find_counter_candidates
from meeting_extractor.llm import FakeLLM
from meeting_extractor.models import Item, MeetingMeta, Topic, Utterance
from meeting_extractor.pipeline import process_topic

# Condensed from case 5 (CTO decides rollback, then flips to hotfix).
LINES = [
    ("Thảo", "Em đề xuất rollback về bản 3.2 ngay tối nay."),                              # u001
    ("Phúc", "Em thì muốn hotfix, không phải rollback cả bản."),                           # u002
    ("Quân", "Anh đồng ý với Thảo. Chốt rollback về 3.2 tối nay, Thảo làm."),              # u003 (evidence)
    ("Thảo", "Dạ em chuẩn bị luôn."),                                                      # u004
    ("Duy", "Khoan anh, rollback về 3.2 là mất tính năng voucher."),                       # u005
    ("Quân", "Ok, vậy không rollback nữa. Hotfix tăng pool kết nối, Phúc làm."),           # u006
    ("Linh", "Chuyện bồi thường cho khách thì sao ạ?"),                                    # u007
]
UTTS = [Utterance(id=f"u{i:03d}", time=f"0{i}:00", speaker=s, text=t) for i, (s, t) in enumerate(LINES, 1)]


def make_item(**kw) -> Item:
    base = dict(item_id="", type="decision", topic_id="t01", topic="Sự cố", content="Rollback về bản 3.2",
                status="confirmed", evidence=["u003"], confidence=0.9)
    base.update(kw)
    return Item(**base)


def ids(us: list[Utterance]) -> list[str]:
    return [u.id for u in us]


# ---------------------------------------------------------------- find_counter_candidates


def test_candidates_only_after_latest_evidence_and_sharing_keywords():
    got = find_counter_candidates(make_item(), UTTS)
    assert ids(got) == ["u005", "u006"]  # u001/u002 are before the evidence; u004/u007 share nothing


def test_candidates_use_latest_evidence_of_several():
    got = find_counter_candidates(make_item(evidence=["u001", "u005"]), UTTS)
    assert ids(got) == ["u006"]


def test_candidates_share_number_without_shared_word():
    utts = [
        Utterance(id="u001", time="01:00", speaker="Hùng", text="Thống nhất ra mắt 15/11."),
        Utterance(id="u002", time="02:00", speaker="Nam", text="Lùi sang 30/11 nhé."),
        Utterance(id="u003", time="03:00", speaker="Lan", text="Ra mắt 15/11 vẫn được mà."),
        Utterance(id="u004", time="04:00", speaker="Lan", text="Đi ăn trưa thôi."),
    ]
    item = make_item(content="Ra mắt ngày 15/11", evidence=["u001"])
    # u003 shares "15/11" (+ word "ra mắt"); u002 shares nothing; u004 shares nothing
    assert ids(find_counter_candidates(item, utts)) == ["u003"]


def test_candidates_limit_and_ordering():
    utts = [Utterance(id="u001", time="00:01", speaker="A", text="Chốt dùng AWS cho hạ tầng.")]
    utts += [Utterance(id=f"u{i:03d}", time=f"00:{i:02d}", speaker="B", text="AWS vẫn ổn") for i in range(2, 10)]
    utts.append(Utterance(id="u010", time="00:10", speaker="B", text="AWS hạ tầng đắt, bỏ AWS"))  # 2 shared words
    item = make_item(content="Dùng AWS cho hạ tầng", evidence=["u001"])
    got = ids(find_counter_candidates(item, utts))
    assert len(got) == 5
    assert got[0] == "u010"  # higher score first
    assert got[1:] == ["u002", "u003", "u004", "u005"]  # ties by transcript order
    assert len(find_counter_candidates(item, utts, limit=2)) == 2


def test_candidates_empty_for_non_decision_or_bad_evidence():
    assert find_counter_candidates(make_item(type="action"), UTTS) == []
    assert find_counter_candidates(make_item(evidence=["u999"]), UTTS) == []
    assert find_counter_candidates(make_item(evidence=["u007"]), UTTS) == []  # nothing after the last one


# ---------------------------------------------------------------- verifier


def ok(**extra):
    return {"passed": True, "reason": "ok", **extra}


def test_verify_sends_later_block_and_sets_contradiction():
    llm = FakeLLM({"verify": ok(contradicted_by=["u006"])})
    item = make_item()
    out = verify(llm, "strong", item, UTTS)
    sent = llm.calls[0][2]
    assert "<later_utterances>" in sent and "u006" in sent and "vậy không rollback nữa" in sent
    assert "u002" not in sent and "bồi thường" not in sent
    assert out.passed and out.contradicted_by == ["u006"] and out.warnings == []
    marked = apply_contradiction(item, out)
    assert marked.contradicted_later is True
    assert marked.field_evidence["contradicted_by"] == ["u006"]
    assert item.contradicted_later is None  # original untouched


def test_verify_drops_unknown_ids_with_warning():
    llm = FakeLLM({"verify": ok(contradicted_by=["u006", "u007", "u999", "u006"])})
    out = verify(llm, "strong", make_item(), UTTS)  # u007 exists but was not sent as a candidate
    assert out.contradicted_by == ["u006"]
    assert len(out.warnings) == 2 and "u999" in out.warnings[1]


def test_only_unknown_ids_keeps_old_ai_label():
    llm = FakeLLM({"verify": ok(contradicted_by=["u999"])})
    item = make_item(contradicted_later=True, field_evidence={"owner": ["u003"]})
    out = verify(llm, "strong", item, UTTS)
    assert out.contradicted_by == []
    same = apply_contradiction(item, out)
    assert same.contradicted_later is True and "contradicted_by" not in same.field_evidence


def test_apply_preserves_other_field_evidence():
    item = make_item(field_evidence={"owner": ["u003"]})
    llm = FakeLLM({"verify": ok(contradicted_by=["u005"])})
    marked = apply_contradiction(item, verify(llm, "strong", item, UTTS))
    assert marked.field_evidence == {"owner": ["u003"], "contradicted_by": ["u005"]}


def test_no_block_without_candidates_and_for_actions():
    llm = FakeLLM({"verify": ok()})
    verify(llm, "strong", make_item(evidence=["u007"]), UTTS)
    verify(llm, "strong", make_item(type="action", status=None), UTTS)
    assert all("later_utterances" not in c[2] and "{{" not in c[2] for c in llm.calls)
    assert len(llm.calls) == 2


def test_verify_without_contradicted_field_defaults_empty():
    llm = FakeLLM({"verify": {"passed": True, "reason": "ok"}})
    assert verify(llm, "strong", make_item(), UTTS).contradicted_by == []


# ---------------------------------------------------------------- pipeline


TRACKED = {
    "type": "decision", "content": "Rollback về bản 3.2", "status": "confirmed", "evidence": ["u003"],
    "history": [], "confidence": 0.9, "flags": [],
}
CANDS = {"candidates": [
    {"type": "decision", "topic_id": "t01", "content": "Rollback về bản 3.2", "speaker": "Quân", "evidence": ["u003"]},
]}
TOPIC = Topic(topic_id="t01", title="Sự cố", utterance_ids=[u.id for u in UTTS])


def test_process_topic_writes_contradiction_and_warnings():
    llm = FakeLLM({
        "extract": CANDS, "track": {"items": [TRACKED]},
        "verify": ok(contradicted_by=["u006", "u404"]),
    })
    res = process_topic(llm, "light", "strong", TOPIC, UTTS, MeetingMeta())
    item = res.items[0]
    assert item.contradicted_later is True and item.field_evidence["contradicted_by"] == ["u006"]
    assert any("u404" in w for w in res.warnings)
    assert item.verify_passed is True


def test_process_topic_retry_items_get_latest_contradiction():
    fail = {"passed": False, "reason": "sai"}
    llm = FakeLLM({
        "extract": [CANDS, CANDS], "track": [{"items": [TRACKED]}, {"items": [{**TRACKED, "content": "Hotfix pool"}]}],
        "verify": [fail, ok(contradicted_by=["u005"])],
    })
    res = process_topic(llm, "light", "strong", TOPIC, UTTS, MeetingMeta())
    retried = next(i for i in res.items if i.content == "Hotfix pool")
    assert retried.field_evidence.get("contradicted_by") == ["u005"]


# ---------------------------------------------------------------- malformed contradicted_by never raises


def test_contradicted_by_null_missing_and_single_string():
    for payload, expected in [
        (ok(contradicted_by=None), []),
        ({"passed": True, "reason": "ok"}, []),
        (ok(contradicted_by="u006"), ["u006"]),
    ]:
        out = verify(FakeLLM({"verify": payload}), "strong", make_item(), UTTS)
        assert out.passed and out.contradicted_by == expected and out.warnings == []


def test_contradicted_by_null_for_action_without_block():
    out = verify(FakeLLM({"verify": ok(contradicted_by=None)}), "strong", make_item(type="action", status=None), UTTS)
    assert out.passed and out.contradicted_by == []


def test_contradicted_by_non_list_gives_warning():
    for bad in (5, {"id": "u006"}, True):
        out = verify(FakeLLM({"verify": ok(contradicted_by=bad)}), "strong", make_item(), UTTS)
        assert out.contradicted_by == [] and len(out.warnings) == 1


def test_contradicted_by_non_string_elements_dropped_with_warning():
    out = verify(FakeLLM({"verify": ok(contradicted_by=["u006", 3, None, {"a": 1}])}), "strong", make_item(), UTTS)
    assert out.contradicted_by == ["u006"] and len(out.warnings) == 1
