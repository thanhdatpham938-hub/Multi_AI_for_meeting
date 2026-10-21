"""Offline tests for the shared conflicting-decision detector."""

from meeting_extractor.conflicts import conflict_pairs, content_tokens, is_conflict_pair
from meeting_extractor.models import HistoryEntry, Item


def d(item_id: str, content: str, status: str, topic: str = "t01", evidence: list[str] | None = None, **kw) -> Item:
    return Item(item_id=item_id, type="decision", topic_id=topic, topic=topic, content=content, status=status,
                evidence=evidence or [f"u9{item_id[-2:]}"], confidence=0.8, **kw)


def test_same_issue_across_topics_by_tokens():
    d02 = d("d02", "Chưa quyết định làm sampling ở siêu thị, chờ Hà hỏi giá phí", "deferred", "t02", ["u010"])
    d19 = d("d19", "Sampling tại Coopmart thay vì Big C do phí Big C cao gấp đôi", "confirmed", "t08", ["u070"])
    assert is_conflict_pair(d02, d19) and is_conflict_pair(d19, d02)
    assert conflict_pairs([d02, d19]) == [(d02, d19)]


def test_same_topic_different_things_not_caught():
    logo = d("d05", "Logo mới duyệt bản màu xanh lá", "confirmed", "t03", ["u020"])
    script = d("d06", "Kịch bản video series chờ bộ phận sáng tạo gửi bản nháp", "open", "t03", ["u030"])
    assert not is_conflict_pair(logo, script)


def test_superseded_never_conflicts():
    a = d("d01", "Dùng AWS làm hạ tầng", "confirmed", evidence=["u001"])
    b = d("d02", "Dùng AWS làm hạ tầng", "superseded", evidence=["u001"])
    assert conflict_pairs([a, b]) == []


def test_two_confirmed_or_two_live_are_not_pairs():
    a = d("d01", "Dùng AWS cho hạ tầng", "confirmed", evidence=["u001"])
    b = d("d02", "Dùng AWS cho hạ tầng", "confirmed", evidence=["u001"])
    c = d("d03", "Dùng AWS cho hạ tầng", "open", evidence=["u001"])
    assert conflict_pairs([a, b]) == [] and conflict_pairs([c, c.model_copy(update={"item_id": "d04"})]) == []


def test_shared_evidence_id_is_enough_even_with_no_shared_words():
    a = d("d01", "Chọn phương án alpha", "confirmed", evidence=["u001"])
    b = d("d02", "Lùi lịch sang tháng sau", "proposed", "t09", evidence=["u001", "u002"])
    assert is_conflict_pair(a, b)


def test_shared_history_evidence_counts():
    a = d("d01", "Chọn phương án alpha", "confirmed", evidence=["u001"])
    b = d("d02", "Lùi lịch sang tháng sau", "open", "t09", evidence=["u005"],
          history=[HistoryEntry(status="proposed", evidence=["u001"])])
    assert is_conflict_pair(a, b)


def test_non_decisions_ignored_and_stop_words_filtered():
    act = Item(item_id="a01", type="action", topic_id="t01", topic="T", content="Dùng AWS", evidence=["u001"],
               confidence=0.8, status="open")
    assert not is_conflict_pair(act, d("d01", "Dùng AWS", "confirmed", evidence=["u001"]))
    assert "và" not in content_tokens("Chốt và triển khai sampling") and "sampling" in content_tokens("sampling")


def test_meeting_wide_common_tokens_are_ignored():
    from meeting_extractor.conflicts import COMMON_DF, conflict_pairs

    def d(content, status, ev):
        return Item(item_id="", type="decision", topic_id="t", topic="T", content=content,
                    status=status, evidence=[ev], confidence=0.9)

    # "khai trương" appears in COMMON_DF decisions -> it no longer links unrelated decisions.
    items = [d("Khai trương ngày 8/12 nếu có biên bản PCCC", "conditional", "u031"),
             d("Khuyến mãi khai trương mua 1 tặng 1 size M", "confirmed", "u043"),
             d("Mời KOL đến khai trương", "deferred", "u096"),
             d("Ngân sách marketing khai trương", "open", "u099")]
    assert COMMON_DF <= 4
    assert conflict_pairs(items) == []


def test_flag_conflicts_marks_both_items():
    from meeting_extractor.conflicts import CONFLICT_FLAG, flag_conflicts

    a = Item(item_id="", type="decision", topic_id="t1", topic="T", content="Sampling tại Coopmart",
             status="confirmed", evidence=["u132"], confidence=0.9)
    b = Item(item_id="", type="decision", topic_id="t2", topic="T", content="Chưa quyết sampling",
             status="deferred", evidence=["u132"], confidence=0.9)
    assert flag_conflicts([a, b]) == 1
    assert CONFLICT_FLAG in a.flags and CONFLICT_FLAG in b.flags


def _dec(content, status, ev):
    return Item(item_id="", type="decision", topic_id="t", topic="T", content=content,
                status=status, evidence=[ev], confidence=0.9)


def test_two_syllable_word_counts_once():
    # Only "khai trương" (one word, two syllables) and the time word "ngày" are shared -> not the same issue.
    items = [_dec("Khai trương ngày 8/12", "conditional", "u031"),
             _dec("Khuyến mãi khai trương: mua 1 tặng 1 size M trong ba ngày đầu", "confirmed", "u043")]
    assert conflict_pairs(items) == []


def test_two_distinct_shared_words_still_conflict():
    # "sampling" and "phí" are two separate shared words (not adjacent) -> same issue.
    items = [_dec("Chưa quyết định làm sampling ở siêu thị, chờ Hà hỏi giá phí", "deferred", "u034"),
             _dec("Sampling tại Coopmart thay vì Big C do phí Big C cao gấp đôi", "confirmed", "u132")]
    assert len(conflict_pairs(items)) == 1


def test_shared_words_merges_adjacent_syllables():
    from meeting_extractor.conflicts import shared_words

    assert shared_words("Khuyến mãi khai trương ngày đầu", {"khai", "trương"}) == {"khai trương"}
