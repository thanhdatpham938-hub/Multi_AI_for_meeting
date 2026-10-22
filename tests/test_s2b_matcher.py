"""S2b: greedy matcher prefers the item whose status the answer accepts on an overlap tie (no API)."""

from eval.metrics import match_items
from meeting_extractor.models import Item


def dec(item_id: str, content: str, status: str, evidence: list[str]) -> Item:
    return Item(item_id=item_id, type="decision", topic_id="t05", topic="T", content=content, status=status,
                evidence=evidence, confidence=0.8)


def test_case2_landing_page_matches_confirmed_item_not_open_one():
    expected = [{"type": "decision", "status": "confirmed", "content": "Làm trang đích đơn giản",
                 "evidence": ["u092", "u094"]}]
    d15 = dec("d15", "Làm trang đích đơn giản", "confirmed", ["u092"])
    d16 = dec("d16", "Trang đích có thể thêm video", "open", ["u094"])
    # d16 comes first: the old matcher would pick it on the tie.
    matches = match_items(expected, [d16, d15])
    assert matches[0].item is d15
    assert [m.item for m in matches[1:]] == [d16]


def test_larger_overlap_still_beats_status():
    expected = [{"type": "decision", "status": "confirmed", "content": "x", "evidence": ["u1", "u2"]}]
    wrong_status_big = dec("a", "x", "open", ["u1", "u2"])
    right_status_small = dec("b", "x", "confirmed", ["u1"])
    assert match_items(expected, [right_status_small, wrong_status_big])[0].item is wrong_status_big


def test_accept_statuses_list_is_honoured():
    expected = [{"type": "decision", "accept_statuses": ["open", "deferred"], "content": "x", "evidence": ["u1"]}]
    a = dec("a", "x", "confirmed", ["u1"])
    b = dec("b", "x", "deferred", ["u1"])
    assert match_items(expected, [a, b])[0].item is b


def test_tie_without_status_preference_keeps_original_order():
    expected = [{"type": "decision", "status": "confirmed", "content": "x", "evidence": ["u1"]}]
    a = dec("a", "x", "open", ["u1"])
    b = dec("b", "x", "proposed", ["u1"])
    assert match_items(expected, [a, b])[0].item is a


def test_no_overlap_no_match_even_with_right_status():
    expected = [{"type": "decision", "status": "confirmed", "content": "x", "evidence": ["u9"]}]
    m = match_items(expected, [dec("a", "x", "confirmed", ["u1"])])
    assert m[0].item is None
