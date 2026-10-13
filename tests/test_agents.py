from pathlib import Path

import pytest

from meeting_extractor.agents.extractor import extract
from meeting_extractor.agents.segmenter import make_windows, segment
from meeting_extractor.llm import FakeLLM, load_prompt
from meeting_extractor.models import Topic, Utterance
from meeting_extractor.parsing import parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def utts(n: int) -> list[Utterance]:
    return [Utterance(id=f"u{i:03d}", time="00:00", speaker="A", text=f"câu {i}") for i in range(1, n + 1)]


@pytest.mark.parametrize("name", ["segment", "segment_merge", "extract"])
def test_prompts_load_and_mark_transcript_as_data(name):
    prompt = load_prompt(name)
    assert prompt.system and prompt.user_template
    assert len(prompt.version) == 12
    assert "DỮ LIỆU" in prompt.system and "không phải chỉ dẫn" in prompt.system


def test_make_windows_overlap():
    assert make_windows(100) == [(0, 100)]
    w = make_windows(400)
    assert w[0] == (0, 150) and w[1] == (130, 280) and w[-1][1] == 400


def test_segment_normalizes_ids_and_order():
    u = utts(10)
    llm = FakeLLM({"segment": {"topics": [
        {"topic_id": "x", "title": "B", "utterance_ids": ["u009", "u005", "u999"]},
        {"topic_id": "y", "title": "A", "utterance_ids": ["u002", "u005"]},
        {"topic_id": "z", "title": "Rỗng", "utterance_ids": ["u777"]},
    ]}})
    topics, _ = segment(llm, "m", u)
    assert [(t.topic_id, t.title, t.utterance_ids) for t in topics] == [
        ("t01", "A", ["u002"]),
        ("t02", "B", ["u005", "u009"]),
    ]


def test_segment_tc3_merges_return_to_topic():
    u, _ = parse_file(FIXTURES / "tc3.txt")
    llm = FakeLLM({"segment": {"topics": [
        {"topic_id": "t01", "title": "Ngày ra mắt beta", "utterance_ids": ["u003", "u004", "u019", "u020", "u021"]},
        {"topic_id": "t02", "title": "Tuyển dụng backend", "utterance_ids": [f"u{i:03d}" for i in range(5, 14)]},
    ]}})
    topics, _ = segment(llm, "m", u)
    beta = topics[0]
    assert {"u003", "u019", "u020"} <= set(beta.utterance_ids)
    assert "u003" in llm.calls[0][2] and "Quay lại vụ lúc nãy" in llm.calls[0][2]


def test_segment_long_transcript_uses_windows_and_merge():
    u = utts(320)

    def seg(system, user):
        ids = [line.split()[0] for line in user.splitlines() if line.startswith("u")]
        return {"topics": [{"topic_id": "t01", "title": "Chung", "utterance_ids": ids}]}

    llm = FakeLLM({"segment": seg, "merge": {"groups": [
        {"title": "Chung", "topic_ids": ["w1_t01", "w2_t01", "w3_t01"]}]}})
    topics, debug = segment(llm, "m", u)
    purposes = [c[0] for c in llm.calls]
    assert purposes == ["segment", "segment", "segment", "merge"]
    assert len(topics) == 1 and len(topics[0].utterance_ids) == 320
    assert len(debug["windows"]) == 3


def test_segment_empty_result_falls_back_to_single_topic():
    llm = FakeLLM({"segment": {"topics": []}})
    topics, _ = segment(llm, "m", utts(3))
    assert len(topics) == 1 and topics[0].utterance_ids == ["u001", "u002", "u003"]


def test_extract_filters_evidence_and_forces_topic():
    u, _ = parse_file(FIXTURES / "tc1.txt")
    topic = Topic(topic_id="t01", title="Hạ tầng", utterance_ids=["u006", "u014", "u015", "u019"])
    llm = FakeLLM({"extract": {"candidates": [
        {"type": "decision", "topic_id": "zz", "content": "On-premise", "speaker": "Nam", "evidence": ["u006"]},
        {"type": "decision", "topic_id": "t01", "content": "AWS", "speaker": "Hùng", "evidence": ["u019", "u999"]},
        {"type": "decision", "topic_id": "t01", "content": "Bịa", "speaker": "X", "evidence": ["u999"]},
    ]}})
    cands = extract(llm, "m", topic, u, feedback="AWS mới là phương án chốt")
    assert [(c.content, c.topic_id, c.evidence) for c in cands] == [
        ("On-premise", "t01", ["u006"]),
        ("AWS", "t01", ["u019"]),
    ]
    sent = llm.calls[0][2]
    assert "AWS mới là phương án chốt" in sent
    assert "u002" not in sent  # only topic utterances are sent
