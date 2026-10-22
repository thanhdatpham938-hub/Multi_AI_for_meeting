"""S2b: _merge_retry must not keep duplicates, and must not leave a failed decision confirmed (no API)."""

from meeting_extractor.agents.tracker import TrackResult
from meeting_extractor.llm import FakeLLM
from meeting_extractor.models import Item, Status, Topic
from meeting_extractor.parsing import parse_file
from meeting_extractor.pipeline import _merge_retry, _same_issue
from tests.test_pipeline_offline import FIXTURES

TC1, _ = parse_file(FIXTURES / "tc1.txt")
TOPIC = Topic(topic_id="t05", title="Chủ đề", utterance_ids=["u006", "u014", "u015", "u019"])
PASS = {"passed": True, "reason": "ok"}


def mk(content: str, evidence: list[str], status: str | None = "confirmed", type_: str = "decision") -> Item:
    return Item(item_id="", type=type_, topic_id="t05", topic="Chủ đề", content=content, status=status,
                evidence=evidence, confidence=0.9)


def merge(first: list[tuple[Item, bool | None, str]], retry_items: list[Item], verify=PASS):
    return _merge_retry(FakeLLM({"verify": verify}), "strong", TOPIC, TC1, first, TrackResult(items=retry_items), {})


# ---------------------------------------------------------------- _same_issue


def test_same_issue_identical_evidence_still_needs_similar_content():
    # u126 states both the channel mix and the budget split: two decisions, one utterance.
    channel = mk("Chạy quảng cáo cả hai kênh, TikTok là chính", ["u014"])
    split = mk("Tỷ lệ ngân sách 70/30", ["u014"])
    assert not _same_issue(channel, split)
    assert _same_issue(mk("Ngọc tự quyết bài đăng giới thiệu ba vị", ["u014"]),
                       mk("Ngọc tự quyết bài đăng giới thiệu ba vị, chạy trước ra mắt một tuần", ["u014"]))


def test_same_issue_requires_same_type():
    assert not _same_issue(mk("Dùng AWS", ["u014"]), mk("Dùng AWS", ["u014"], None, "action"))


def test_same_issue_no_shared_evidence():
    assert not _same_issue(mk("Dùng AWS", ["u014"]), mk("Dùng AWS", ["u015"]))


def test_same_issue_overlap_against_shorter_content():
    long = mk("Sampling tại Coopmart thay vì Big C do phí cao gấp đôi", ["u014", "u015"])
    short = mk("Sampling tại Coopmart", ["u014"])
    assert _same_issue(long, short) and _same_issue(short, long)


def test_same_issue_partial_evidence_different_content():
    a = mk("Chạy quảng cáo cả hai kênh, TikTok là chính", ["u019"])
    b = mk("Phân bổ ngân sách TikTok 70%, Facebook 30%", ["u019", "u015"])
    assert not _same_issue(a, b)


# ---------------------------------------------------------------- the three real cases


def test_coopmart_retry_replaces_first_pass_instead_of_duplicating():
    first = mk("Sampling tại Coopmart thay vì Big C do phí cao gấp đôi", ["u014"])
    retry = mk("Sampling tại Coopmart", ["u014"])
    items, _, failed = merge([(first, False, "sai")], [retry])
    assert [i.content for i in items] == ["Sampling tại Coopmart"] and not failed


def test_ngoc_tu_quyet_retry_replaces_first_pass():
    first = mk("Ngọc tự quyết bài đăng giới thiệu ba vị, chạy trước ngày ra mắt một tuần để tạo tò mò", ["u015"])
    retry = mk("Ngọc tự quyết bài đăng giới thiệu ba vị", ["u015"])
    items, _, _ = merge([(first, False, "sai")], [retry])
    assert [i.content for i in items] == ["Ngọc tự quyết bài đăng giới thiệu ba vị"]


def test_son_tung_dropped_by_retry_is_kept_but_demoted():
    joke = mk("Không mời Sơn Tùng vì ngân sách có hạn", ["u006"])
    other = mk("Dùng AWS", ["u019"])
    items, warnings, _ = merge([(joke, False, "câu đùa")], [other])
    kept = next(i for i in items if "Sơn Tùng" in i.content)
    assert kept.status == Status.proposed
    assert "verify_failed" in kept.flags and kept.confidence <= 0.5 and kept.verify_passed is False
    last = kept.history[-1]
    assert last.status == Status.proposed and last.evidence == ["u006"]
    assert last.reason == "Kiểm chứng không đạt và lần làm lại không còn giữ kết luận này"
    assert any("Sơn Tùng" in w and "proposed" in w for w in warnings)
    assert any(i.content == "Dùng AWS" for i in items)  # data from the retry is still there


def test_son_tung_demoted_even_when_retry_returns_nothing():
    joke = mk("Không mời Sơn Tùng", ["u006"])
    items, _, failed = merge([(joke, False, "x")], [])
    assert failed and items[0].status == Status.proposed


def test_non_decision_unmatched_is_not_demoted():
    act = mk("Minh gửi tài liệu", ["u014"], None, "action")
    items, warnings, _ = merge([(act, False, "x")], [])
    assert items[0].status is None and items[0].history == []
    assert "verify_failed" in items[0].flags
    assert not any("proposed" in w for w in warnings)


def test_unmatched_non_confirmed_decision_keeps_status():
    d = mk("Hoãn ngân sách", ["u006"], "deferred")
    items, _, _ = merge([(d, False, "x")], [])
    assert items[0].status == Status.deferred and items[0].history == []


# ---------------------------------------------------------------- different decisions, same sentence


def test_two_different_decisions_citing_same_sentence_are_both_kept():
    channel = mk("Chạy quảng cáo cả hai kênh, TikTok là chính", ["u019"])
    ratio = mk("Phân bổ ngân sách TikTok 70%, Facebook 30%", ["u019", "u015"])
    items, warnings, _ = merge([(channel, True, "ok"), (mk("Dùng AWS", ["u006"]), False, "x")], [ratio])
    contents = {i.content for i in items}
    assert {channel.content, ratio.content} <= contents
    assert not any("trùng" in w for w in warnings)
