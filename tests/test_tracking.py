from pathlib import Path

from meeting_extractor.agents.tracker import track
from meeting_extractor.agents.verifier import verify
from meeting_extractor.llm import FakeLLM
from meeting_extractor.models import Candidate, Item, Status, Topic
from meeting_extractor.parsing import parse_file
from meeting_extractor.pipeline import process_topic

FIXTURES = Path(__file__).parent / "fixtures"
TC1, _ = parse_file(FIXTURES / "tc1.txt")
TC4, _ = parse_file(FIXTURES / "tc4.txt")
TOPIC1 = Topic(topic_id="t01", title="Hạ tầng server", utterance_ids=["u006", "u014", "u015", "u019"])

AWS_ITEM = {
    "type": "decision", "content": "Dùng AWS", "status": "confirmed", "condition": None,
    "history": [
        {"status": "proposed", "content": "On-premise", "evidence": ["u006"]},
        {"status": "superseded", "content": "On-premise", "reason": "vượt ngân sách", "evidence": ["u014"]},
        {"status": "confirmed", "content": "AWS", "evidence": ["u019"]},
    ],
    "owner": None, "deadline": None, "evidence": ["u019"], "confidence": 0.9,
    "flags": ["no_closing_signal", "made_up_flag"],
}
CANDS = {"candidates": [
    {"type": "decision", "topic_id": "t01", "content": "On-premise", "speaker": "Nam", "evidence": ["u006"]},
    {"type": "decision", "topic_id": "t01", "content": "AWS", "speaker": "Lan", "evidence": ["u015"]},
]}


def test_track_builds_items_with_topic_and_filters_flags():
    llm = FakeLLM({"track": {"items": [AWS_ITEM]}})
    cands = [Candidate.model_validate(c) for c in CANDS["candidates"]]
    items = track(llm, "strong", TOPIC1, cands, TC1)
    assert len(items) == 1
    it = items[0]
    assert (it.topic_id, it.topic, it.status) == ("t01", "Hạ tầng server", Status.confirmed)
    assert it.history[1].status == Status.superseded
    assert it.flags == ["no_closing_signal"]
    assert "On-premise" in llm.calls[0][2]  # candidates are passed to the tracker


def test_verify_sends_only_evidence_text():
    llm = FakeLLM({"verify": {"passed": True, "reason": "ok"}})
    item = Item(item_id="", topic_id="t01", topic="x", **{k: v for k, v in AWS_ITEM.items() if k != "flags"})
    out = verify(llm, "strong", item, TC1)
    assert out.passed
    sent = llm.calls[0][2]
    assert "chốt dùng AWS" in sent and "on-premise cho dự án" not in sent


def test_verify_without_evidence_fails_without_llm_call():
    llm = FakeLLM({})
    item = Item(item_id="", type="action", topic_id="t01", topic="x", content="c", evidence=["u999"], confidence=0.9)
    assert verify(llm, "strong", item, TC1).passed is False
    assert llm.calls == []


def test_process_topic_no_retry_when_verified():
    llm = FakeLLM({"extract": CANDS, "track": {"items": [AWS_ITEM]}, "verify": {"passed": True, "reason": "ok"}})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert [c[0] for c in llm.calls] == ["extract", "track", "verify"]
    assert res.items[0].status == Status.confirmed
    assert "verify_failed" not in res.items[0].flags


def test_process_topic_retries_once_then_flags():
    bad = {**AWS_ITEM, "content": "Dùng on-premise", "evidence": ["u006"]}
    llm = FakeLLM({
        "extract": [CANDS, CANDS],
        "track": [{"items": [bad]}, {"items": [bad]}],
        "verify": [{"passed": False, "reason": "u006 chỉ là đề xuất"}, {"passed": False, "reason": "vẫn sai"}],
    })
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert [c[0] for c in llm.calls] == ["extract", "track", "verify", "extract", "track", "verify"]
    assert "u006 chỉ là đề xuất" in llm.calls[3][2] and "u006 chỉ là đề xuất" in llm.calls[4][2]
    item = res.items[0]
    assert "verify_failed" in item.flags and item.confidence == 0.5


def test_process_topic_retry_fixes_item():
    bad = {**AWS_ITEM, "content": "Dùng on-premise", "evidence": ["u006"]}
    llm = FakeLLM({
        "extract": [CANDS, CANDS],
        "track": [{"items": [bad]}, {"items": [AWS_ITEM]}],
        "verify": [{"passed": False, "reason": "sai"}, {"passed": True, "reason": "ok"}],
    })
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.items[0].content == "Dùng AWS" and "verify_failed" not in res.items[0].flags


def test_process_topic_tc4_statuses_and_no_verify_for_knowledge():
    topic = Topic(topic_id="t01", title="TC4", utterance_ids=[u.id for u in TC4])
    items = {"items": [
        {"type": "decision", "content": "Ký hợp đồng gói B", "status": "conditional",
         "condition": "khách đồng ý giá mới", "evidence": ["u012"], "confidence": 0.85},
        {"type": "decision", "content": "Ngân sách marketing", "status": "deferred",
         "evidence": ["u015"], "confidence": 0.8},
        {"type": "knowledge", "content": "Chat chậm 2 tuần", "evidence": ["u003"], "confidence": 0.9},
    ]}
    llm = FakeLLM({"extract": {"candidates": []}, "track": items, "verify": {"passed": True, "reason": "ok"}})
    res = process_topic(llm, "light", "strong", topic, TC4)
    assert [c[0] for c in llm.calls].count("verify") == 2
    assert [i.status for i in res.items][:2] == [Status.conditional, Status.deferred]
    assert not any(i.status == Status.confirmed for i in res.items)
