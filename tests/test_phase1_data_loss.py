"""Phase 1 (L1, L2): no silent data loss when an agent returns bad output."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from meeting_extractor.agents.tracker import TrackerFailed, track_detailed
from meeting_extractor.config import Settings
from meeting_extractor.llm import FakeLLM, LLMError
from meeting_extractor.models import Candidate, Status
from meeting_extractor.parsing import parse_file
from meeting_extractor.pipeline import process_topic, run
from tests.test_pipeline_offline import FIXTURES, _track, tc1_llm
from tests.test_tracking import AWS_ITEM, CANDS, TOPIC1

TC1, _ = parse_file(FIXTURES / "tc1.txt")
APP = str(Path(__file__).resolve().parents[1] / "app" / "review_app.py")
GOOD_VERIFY = {"passed": True, "reason": "ok"}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(anthropic_api_key=None, model_light="light", model_strong="strong",
                    temperature=None, runs_dir=tmp_path / "runs")


def _cands() -> list[Candidate]:
    return [Candidate.model_validate(c) for c in CANDS["candidates"]]


# ---------------------------------------------------------------- L1: tracker validation


def test_null_history_status_drops_only_that_entry():
    item = {**AWS_ITEM, "history": [
        {"status": None, "content": "x", "evidence": ["u006"]},
        {"status": "superseded", "content": "On-premise", "evidence": ["u014"]},
        {"content": "thiếu status"},
    ]}
    llm = FakeLLM({"track": {"items": [item]}})
    res = track_detailed(llm, "strong", TOPIC1, _cands(), TC1)
    assert len(res.items) == 1
    assert [h.status for h in res.items[0].history] == [Status.superseded]
    assert len(llm.calls) == 1  # no retry needed any more
    assert any("2 mục lịch sử" in w for w in res.warnings)


def test_unsalvageable_item_dropped_others_kept():
    bad = {"type": "decision", "content": "Không evidence", "evidence": []}
    llm = FakeLLM({"track": {"items": [bad, "rác", AWS_ITEM]}})
    res = track_detailed(llm, "strong", TOPIC1, _cands(), TC1)
    assert [i.content for i in res.items] == ["Dùng AWS"]
    assert len(res.warnings) == 2


def test_non_list_history_becomes_empty_with_warning():
    llm = FakeLLM({"track": {"items": [{**AWS_ITEM, "history": "oops"}]}})
    res = track_detailed(llm, "strong", TOPIC1, _cands(), TC1)
    assert res.items[0].history == [] and res.warnings


def test_all_items_invalid_raises_tracker_failed():
    llm = FakeLLM({"track": {"items": [{"type": "nope"}]}})
    with pytest.raises(TrackerFailed):
        track_detailed(llm, "strong", TOPIC1, _cands(), TC1)


def test_empty_items_ok_when_no_candidates():
    res = track_detailed(FakeLLM({"track": {"items": []}}), "strong", TOPIC1, [], TC1)
    assert res.items == [] and res.warnings == []


def test_empty_items_with_candidates_is_tracker_failure():
    with pytest.raises(TrackerFailed):
        track_detailed(FakeLLM({"track": {"items": []}}), "strong", TOPIC1, _cands(), TC1)
    llm = FakeLLM({"extract": CANDS, "track": {"items": []}})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.failed and len(res.items) == 2
    assert all(i.flags == ["tracker_failed"] for i in res.items)


def test_dropped_item_marks_topic_failed_but_dropped_history_does_not():
    bad = {"type": "decision", "content": "Không evidence", "evidence": []}
    llm = FakeLLM({"extract": CANDS, "track": {"items": [bad, AWS_ITEM]}, "verify": GOOD_VERIFY})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.failed and len(res.items) == 1
    only_history = {**AWS_ITEM, "history": [{"status": None}]}
    llm = FakeLLM({"extract": CANDS, "track": {"items": [only_history]}, "verify": GOOD_VERIFY})
    assert not process_topic(llm, "light", "strong", TOPIC1, TC1).failed


def test_process_topic_with_null_history_keeps_item_and_warns():
    item = {**AWS_ITEM, "history": [{"status": None, "evidence": ["u006"]}]}
    llm = FakeLLM({"extract": CANDS, "track": {"items": [item]}, "verify": GOOD_VERIFY})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert len(res.items) == 1 and not res.failed
    assert any("lịch sử" in w for w in res.warnings)


# ---------------------------------------------------------------- L1: agent failures


def test_tracker_total_failure_keeps_candidates():
    llm = FakeLLM({"extract": CANDS, "track": "không phải json"})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.failed
    assert len(res.items) == 2
    for it in res.items:
        assert it.flags == ["tracker_failed"] and it.confidence == 0.3 and it.status is None
        assert it.item_id == "" and (it.topic_id, it.topic) == ("t01", "Hạ tầng server")
        assert it.verify_passed is None
    assert [c[0] for c in llm.calls].count("verify") == 0
    assert any("Agent 3" in w for w in res.warnings)


def test_pipeline_tracker_failure_flag_survives_rules(settings):
    llm = tc1_llm()
    llm.handlers["track"] = "hỏng"
    result = run(FIXTURES / "tc1.txt", llm=llm, settings=settings)
    assert set(result.failed_topics) == {"t01", "t02"}
    assert len(result.items) == 3  # 2 + 1 raw candidates
    assert all("tracker_failed" in i.flags for i in result.items)
    assert all(i.item_id for i in result.items)
    saved = (settings.runs_dir / result.run_id / "result.json").read_text(encoding="utf-8")
    assert '"failed_topics"' in saved and '"t01"' in saved


def test_extract_failure_marks_topic_and_other_topics_run(settings):
    llm = tc1_llm()
    llm.handlers["extract"] = lambda s, u: "hỏng" if "t02" in u else {"candidates": [
        {"type": "decision", "topic_id": "t01", "content": "AWS", "speaker": "Lan", "evidence": ["u015"]}]}
    result = run(FIXTURES / "tc1.txt", llm=llm, settings=settings)
    assert result.failed_topics == ["t02"]
    assert any("t02" in w and "Agent 2" in w for w in result.warnings)
    assert result.items and all(i.topic_id == "t01" for i in result.items)


def test_verify_llm_error_keeps_items_and_marks_topic():
    llm = FakeLLM({"extract": CANDS, "track": {"items": [AWS_ITEM]}, "verify": "hỏng"})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.failed and len(res.items) == 1
    assert res.items[0].verify_passed is None and "verify_failed" not in res.items[0].flags
    assert any("Agent 4" in w for w in res.warnings)


def test_retry_failure_keeps_first_pass_items_flagged():
    llm = FakeLLM({"extract": [CANDS, "hỏng", "hỏng", "hỏng"], "track": {"items": [AWS_ITEM]},
                   "verify": {"passed": False, "reason": "sai"}})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.failed and len(res.items) == 1
    it = res.items[0]
    assert "verify_failed" in it.flags and it.confidence == 0.5 and it.verify_passed is False


# ---------------------------------------------------------------- retry never shrinks the result

ACTION = {"type": "action", "content": "Minh gửi tài liệu API", "evidence": ["u014"], "confidence": 0.8}
PASS = {"passed": True, "reason": "ok"}
FAIL = {"passed": False, "reason": "sai"}


def _retry_llm(retry_extract, retry_track, verify) -> FakeLLM:
    return FakeLLM({"extract": [CANDS, retry_extract], "track": [{"items": [AWS_ITEM, ACTION]}, retry_track],
                    "verify": verify})


def test_retry_with_empty_candidates_keeps_first_pass():
    llm = _retry_llm({"candidates": []}, {"items": []}, [PASS, FAIL])
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.failed and len(res.items) == 2
    aws = next(i for i in res.items if i.type.value == "decision")
    act = next(i for i in res.items if i.type.value == "action")
    assert aws.verify_passed is True and "verify_failed" not in aws.flags
    assert "verify_failed" in act.flags and act.confidence <= 0.5 and act.verify_passed is False
    assert any("làm lại" in w for w in res.warnings)


def test_retry_with_empty_tracker_items_keeps_first_pass():
    llm = _retry_llm(CANDS, {"items": []}, [PASS, FAIL])
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.failed and len(res.items) == 2
    assert next(i for i in res.items if i.type.value == "decision").verify_passed is True
    assert res.warnings


def test_first_pass_passed_items_survive_retry_and_failed_are_replaced():
    fixed = {**ACTION, "content": "Minh gửi tài liệu API thứ Sáu"}
    llm = _retry_llm(CANDS, {"items": [fixed]}, [PASS, FAIL, PASS])
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert not res.failed
    assert sorted(i.content for i in res.items) == ["Dùng AWS", "Minh gửi tài liệu API thứ Sáu"]
    assert all(i.verify_passed is True for i in res.items)


def test_unmatched_failed_item_is_kept_flagged_when_retry_replaces_only_one():
    a = {**AWS_ITEM, "content": "Dùng AWS", "evidence": ["u019"]}
    b = {**ACTION, "evidence": ["u014"]}
    a2 = {**a, "content": "Dùng AWS hạ tầng"}
    llm = FakeLLM({"extract": [CANDS, CANDS], "track": [{"items": [a, b]}, {"items": [a2]}],
                   "verify": [FAIL, FAIL, PASS]})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    by_content = {i.content: i for i in res.items}
    assert set(by_content) == {"Dùng AWS hạ tầng", "Minh gửi tài liệu API"}  # a replaced, b kept
    kept = by_content["Minh gửi tài liệu API"]
    assert "verify_failed" in kept.flags and kept.confidence <= 0.5 and kept.verify_passed is False
    assert by_content["Dùng AWS hạ tầng"].verify_passed is True
    assert any("chưa được sửa" in w for w in res.warnings)


def test_different_issue_sharing_evidence_is_not_a_duplicate():
    other = {"type": "decision", "content": "Lùi beta sang 15/11", "status": "confirmed",
             "evidence": ["u019"], "confidence": 0.9}
    llm = FakeLLM({"extract": [CANDS, CANDS], "track": [{"items": [AWS_ITEM, ACTION]}, {"items": [other]}],
                   "verify": [PASS, FAIL, PASS]})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    contents = {i.content for i in res.items}
    assert {"Dùng AWS", "Lùi beta sang 15/11"} <= contents
    assert not any("trùng" in w for w in res.warnings)


def test_retry_duplicate_of_passed_item_warns_with_both_contents():
    dup = {**AWS_ITEM, "content": "Dùng AWS hạ tầng"}
    llm = _retry_llm(CANDS, {"items": [dup]}, [PASS, FAIL])
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert "Dùng AWS hạ tầng" not in {i.content for i in res.items}
    assert any("Dùng AWS hạ tầng" in w and "Dùng AWS\"" in w for w in res.warnings)


def test_retry_duplicate_of_passed_item_is_not_added_twice():
    llm = _retry_llm(CANDS, {"items": [AWS_ITEM]}, [PASS, FAIL])
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert len(res.items) == 2 and not res.failed
    assert [i.content for i in res.items].count("Dùng AWS") == 1


# ---------------------------------------------------------------- verify_passed


def test_verify_passed_values():
    knowledge = {"type": "knowledge", "content": "Chat chậm", "evidence": ["u006"], "confidence": 0.9}
    llm = FakeLLM({"extract": CANDS, "track": {"items": [AWS_ITEM, knowledge]}, "verify": GOOD_VERIFY})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert [i.verify_passed for i in res.items] == [True, None]


def test_verify_passed_false_after_retry():
    bad = {**AWS_ITEM, "content": "Dùng on-premise", "evidence": ["u006"]}
    llm = FakeLLM({"extract": [CANDS, CANDS], "track": [{"items": [bad]}, {"items": [bad]}],
                   "verify": [{"passed": False, "reason": "a"}, {"passed": False, "reason": "b"}]})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.items[0].verify_passed is False and "verify_failed" in res.items[0].flags


def test_verify_passed_true_when_retry_fixes():
    bad = {**AWS_ITEM, "content": "Dùng on-premise", "evidence": ["u006"]}
    llm = FakeLLM({"extract": [CANDS, CANDS], "track": [{"items": [bad]}, {"items": [AWS_ITEM]}],
                   "verify": [{"passed": False, "reason": "a"}, GOOD_VERIFY]})
    res = process_topic(llm, "light", "strong", TOPIC1, TC1)
    assert res.items[0].verify_passed is True


def test_tracker_failed_is_llm_error():
    assert issubclass(TrackerFailed, LLMError)


# ---------------------------------------------------------------- L2: review app


def _app_with_run(monkeypatch, settings, break_tracker: bool) -> AppTest:
    monkeypatch.setenv("RUNS_DIR", str(settings.runs_dir))
    llm = tc1_llm()
    if break_tracker:
        llm.handlers["track"] = lambda s, u: "hỏng" if "t02" in u else _track(s, u)
    result = run(FIXTURES / "tc1.txt", llm=llm, settings=settings)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["page"] = "run"
    at.session_state["run_dir"] = str(settings.runs_dir / result.run_id)
    return at.run()


def _quick(at: AppTest):
    return next(b for b in at.button if b.label == "✔ Duyệt nhanh")


def test_app_failed_topics_show_error_and_disable_quick_approve(monkeypatch, settings):
    at = _app_with_run(monkeypatch, settings, break_tracker=True)
    assert not at.exception
    assert len(at.error) == 1 and "Hạ tầng server" in at.error[0].value
    assert _quick(at).disabled
    at.checkbox[0].check().run()
    assert not _quick(at).disabled


def test_app_no_failed_topics_no_error(monkeypatch, settings):
    at = _app_with_run(monkeypatch, settings, break_tracker=False)
    assert not at.exception and len(at.error) == 0
    assert not _quick(at).disabled


def _make_run(monkeypatch, settings, break_tracker: bool) -> str:
    monkeypatch.setenv("RUNS_DIR", str(settings.runs_dir))
    llm = tc1_llm()
    if break_tracker:
        llm.handlers["track"] = lambda s, u: "hỏng" if "t02" in u else _track(s, u)
    return str(settings.runs_dir / run(FIXTURES / "tc1.txt", llm=llm, settings=settings).run_id)


def test_app_switching_runs_does_not_leak_ack_or_banner(monkeypatch, settings):
    bad1 = _make_run(monkeypatch, settings, True)
    clean = _make_run(monkeypatch, settings, False)
    bad2 = _make_run(monkeypatch, settings, True)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["page"] = "run"
    at.session_state["run_dir"] = bad1
    at.run()
    assert len(at.error) == 1 and _quick(at).disabled
    at.checkbox[0].check().run()
    assert not _quick(at).disabled

    at.session_state["run_dir"] = clean
    at.run()
    assert len(at.error) == 0 and len(at.checkbox) == 0 and not _quick(at).disabled

    at.session_state["run_dir"] = bad2
    at.run()
    assert len(at.error) == 1 and _quick(at).disabled and not at.checkbox[0].value

    at.session_state["run_dir"] = bad1
    at.run()
    assert len(at.error) == 1 and _quick(at).disabled and not at.checkbox[0].value
