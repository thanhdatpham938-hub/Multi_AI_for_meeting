"""M5A: topic merge, timeline digest, reconcile and code conflict flags (offline, FakeLLM)."""

from __future__ import annotations

import pytest

from meeting_extractor.agents.digest import build_digest
from meeting_extractor.agents.reconciler import ReconcileOutput, apply_reconcile
from meeting_extractor.agents.segmenter import merge_topics
from meeting_extractor.config import Settings
from meeting_extractor.conflicts import flag_conflicts
from meeting_extractor.llm import FakeLLM
from meeting_extractor.models import Item, Topic, Utterance
from meeting_extractor.pipeline import load_result, run_utterances

TEXTS = [
    ("Hùng", "Chốt chạy quảng cáo 3 kênh nhé."),
    ("Lan", "Hôm nay trời đẹp quá."),
    ("Hùng", "Chạy quảng cáo chỉ 2 kênh thôi, để tính sau."),
    ("Minh", "Minh làm kế hoạch quảng cáo, thứ Sáu gửi anh."),
]
UTTS = [Utterance(id=f"u{i:03d}", time=f"0{i}:00", speaker=s, text=t) for i, (s, t) in enumerate(TEXTS, start=1)]

SEGMENT = {"topics": [
    {"topic_id": "t01", "title": "Quảng cáo kênh", "utterance_ids": ["u001"]},
    {"topic_id": "t02", "title": "Xã giao", "utterance_ids": ["u002"]},
    {"topic_id": "t03", "title": "Quảng cáo (quay lại)", "utterance_ids": ["u003", "u004"]},
]}
MERGE = {"groups": [{"title": "Quảng cáo", "topic_ids": ["t01", "t03"]}, {"title": "Xã giao", "topic_ids": ["t02"]}]}
DIGEST = {"events": [
    {"kind": "chốt", "summary": "Chốt 3 kênh quảng cáo", "utterance_ids": ["u001"]},
    {"kind": "hoãn", "summary": "Hoãn còn 2 kênh", "utterance_ids": ["u003", "u999"]},
    {"kind": "lạ", "summary": "Loại vì kind lạ", "utterance_ids": ["u002"]},
    {"kind": "chốt", "summary": "Loại vì id lạ", "utterance_ids": ["u999"]},
]}
RECONCILE = {"related": [{"a": "d01", "b": "a01", "relation": "thực hiện"}, {"a": "d01", "b": "zz9"}],
             "conflicts": [{"a": "d01", "b": "d02", "reason": "khác số kênh"}]}


def _extract(system: str, user: str) -> dict:
    if "u001" not in user:
        return {"candidates": []}
    return {"candidates": [{"type": "decision", "topic_id": "t01", "content": "3 kênh", "speaker": "Hùng",
                            "evidence": ["u001"]}]}


def _track(system: str, user: str) -> dict:
    if "u001" not in user:
        return {"items": []}
    return {"items": [
        {"type": "decision", "content": "Chạy quảng cáo 3 kênh", "status": "confirmed", "evidence": ["u001"],
         "closing_signal": "explicit", "evidence_directness": "direct"},
        {"type": "decision", "content": "Chạy quảng cáo 2 kênh", "status": "deferred", "evidence": ["u003"],
         "closing_signal": "none", "evidence_directness": "direct"},
        {"type": "action", "content": "Lập kế hoạch quảng cáo", "status": None, "owner": "Minh",
         "evidence": ["u004"], "commitment": "assigned", "evidence_directness": "direct"},
    ]}


def make_llm(**override) -> FakeLLM:
    handlers = {"segment": SEGMENT, "merge": MERGE, "digest": DIGEST, "extract": _extract, "track": _track,
                "verify": {"passed": True, "reason": "ok"}, "reconcile": RECONCILE}
    handlers.update(override)
    return FakeLLM(handlers)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(anthropic_api_key=None, model_light="light", model_strong="strong",
                    temperature=None, runs_dir=tmp_path / "runs")


def go(llm: FakeLLM, settings: Settings, save: bool = False):
    return run_utterances(UTTS, "m.txt", llm=llm, settings=settings, save=save)


def purposes(llm: FakeLLM) -> list[str]:
    return [c[0] for c in llm.calls]


def mk(item_id: str, type_: str = "decision", status: str | None = "confirmed", content: str = "x",
       evidence: list[str] | None = None, topic_id: str = "t01") -> Item:
    return Item(item_id=item_id, type=type_, topic_id=topic_id, topic=topic_id, content=content, status=status,
                evidence=evidence or ["u001"], confidence=0.8)


# ---------------------------------------------------------------- merge


def test_merge_always_runs_and_merges_small_meeting(settings):
    llm = make_llm()
    result = go(llm, settings)
    assert "merge" in purposes(llm)
    assert [t.title for t in result.topics] == ["Quảng cáo", "Xã giao"]
    assert result.topics[0].utterance_ids == ["u001", "u003", "u004"]


def test_merge_skipped_for_single_topic():
    llm = FakeLLM({})
    topics = [Topic(topic_id="t01", title="A", utterance_ids=["u001"])]
    assert merge_topics(llm, "m", topics, UTTS)[0] == topics
    assert llm.calls == []


def test_merge_failure_keeps_unmerged_topics_with_warning(settings):
    llm = make_llm(merge="không phải JSON")
    result = go(llm, settings)
    assert len(result.topics) == 3
    assert any("Gộp chủ đề lỗi" in w for w in result.warnings)
    assert result.items  # run still produced items


# ---------------------------------------------------------------- digest


def test_digest_cleaned_and_passed_to_tracker(settings):
    llm = make_llm()
    go(llm, settings)
    track_users = [u for p, _, u in llm.calls if p == "track"]
    assert track_users and all("Dàn ý toàn cuộc họp" in u for u in track_users)
    assert all("Chốt 3 kênh quảng cáo" in u and "Loại vì" not in u for u in track_users)


def test_build_digest_drops_bad_events_and_ids():
    text, debug = build_digest(make_llm(), "m", UTTS)
    assert text.count("\n") == 1  # two valid events
    assert "u999" not in text and debug["dropped"] == 2


def test_digest_failure_runs_without_outline(settings):
    llm = make_llm(digest="rác")
    result = go(llm, settings)
    assert any("Lập dàn ý lỗi" in w for w in result.warnings)
    assert all("Dàn ý toàn cuộc họp" not in u for p, _, u in llm.calls if p == "track")
    assert result.items


# ---------------------------------------------------------------- reconcile


def test_reconcile_links_both_ways_and_ignores_unknown_ids(settings):
    result = go(make_llm(), settings)
    by_id = {i.item_id: i for i in result.items}
    assert "a01" in by_id["d01"].related_items and "d01" in by_id["a01"].related_items
    assert not any("zz9" in r for i in result.items for r in i.related_items)
    assert len(result.items) == 3  # nothing deleted
    assert {i.status.value for i in result.items if i.type.value == "decision"} == {"confirmed", "deferred"}


def test_reconcile_failure_is_skipped_with_warning(settings):
    result = go(make_llm(reconcile="rác"), settings)
    assert any("Đối soát lỗi" in w for w in result.warnings)
    assert len(result.items) == 3


def test_apply_reconcile_flags_only_decision_pairs_and_links_two_way():
    items = [mk("d03", content="Chọn AWS"), mk("d04", status="open", content="Ký gói B"),
             mk("a05", "action", None, "Dựng khung")]
    out = ReconcileOutput.model_validate({
        "related": [{"a": "d03", "b": "a05"}, {"a": "d03", "b": "nope"}, {"a": "d03", "b": "d03"}],
        "conflicts": [{"a": "d03", "b": "d04", "reason": "r"}, {"a": "d03", "b": "a05"}, {"a": "x", "b": "d04"}],
    })
    warnings = apply_reconcile(items, out)
    d3, d4, a5 = items
    assert d3.related_items == ["a05"] and a5.related_items == ["d03"] and d4.related_items == []
    assert "conflicting_decision" in d3.flags and "conflicting_decision" in d4.flags
    assert "conflicting_decision" not in a5.flags
    assert len(warnings) == 1 and "d03" in warnings[0] and "d04" in warnings[0]


# ---------------------------------------------------------------- code conflicts


def test_flag_conflicts_catches_cross_topic_pair():
    a = mk("d02", status="confirmed", content="Chạy quảng cáo Facebook trong tháng 11", topic_id="t01")
    b = mk("d19", status="proposed", content="Chạy quảng cáo Facebook sang tháng 12", evidence=["u009"],
           topic_id="t07")
    assert flag_conflicts([a, b]) == 1
    assert "conflicting_decision" in a.flags and "conflicting_decision" in b.flags


def test_code_flags_conflict_in_pipeline_without_ai(settings):
    result = go(make_llm(reconcile={"related": [], "conflicts": []}), settings)
    ds = [i for i in result.items if i.type.value == "decision"]
    assert len(ds) == 2 and all("conflicting_decision" in i.flags for i in ds)
    assert not any(w.startswith("Nghi mâu thuẫn") for w in result.warnings)


# ---------------------------------------------------------------- order / persistence


def test_call_order(settings):
    llm = make_llm()
    go(llm, settings)
    p = purposes(llm)
    assert p[:3] == ["segment", "merge", "digest"]
    assert p[-1] == "reconcile"
    assert p.index("digest") < p.index("extract") < p.index("track") < p.index("verify") < p.index("reconcile")
    models = {c[0]: c[1] for c in llm.calls}
    assert models["digest"] == "light" and models["merge"] == "light" and models["reconcile"] == "strong"


def test_intermediate_files_saved_and_ids_stable(settings):
    result = go(make_llm(), settings, save=True)
    run_dir = settings.runs_dir / result.run_id
    for name in ["segment.json", "digest.json", "reconcile.json", "result.json"]:
        assert (run_dir / name).exists(), name
    assert load_result(run_dir).items == result.items
    ids = [i.item_id for i in result.items]
    assert len(ids) == len(set(ids))
    assert {r for i in result.items for r in i.related_items} <= set(ids)
