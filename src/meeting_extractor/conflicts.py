"""Deterministic detection of conflicting decisions (shared by the pipeline and the evaluation).

Two decisions conflict when one is `confirmed`, the other is still live (proposed / open / deferred / conditional,
never superseded) and both are about the same issue, regardless of topic assignment.

"Same issue" = they share an utterance id (evidence or history), or they share >= 2 content *words* with an overlap
coefficient >= 0.2. Vietnamese words are often two syllables ("khai trương", "quảng cáo"), so shared syllables that
are adjacent in a text count as one word. Generic time words ("ngày", "tuần"…) and tokens that appear in COMMON_DF
or more decisions of the same meeting carry no signal about *which* issue is meant and are ignored. A flagged pair
only asks a human to look; nothing is deleted.
"""

from __future__ import annotations

import re

from collections import Counter

from .models import Item

LIVE_STATUSES = {"proposed", "open", "deferred", "conditional"}
MIN_SHARED_TOKENS = 2
MIN_OVERLAP = 0.2
MIN_TOKEN_LEN = 3  # tokens of <= 2 characters are dropped
COMMON_DF = 4  # a token present in this many decisions of one meeting is too common to identify an issue
CONFLICT_FLAG = "conflicting_decision"

# Small Vietnamese stop-word list (function words and generic decision verbs).
STOP_WORDS = frozenset("""
và của cho các những một này đó khi thì là có không được đã sẽ đang cần phải nên với từ trong ngoài trên dưới
tại theo vào ra lên xuống như nhưng nếu hoặc hay vậy nhé nhỉ thôi rồi cũng còn lại thay vì do bởi để mà
mình chúng tôi anh chị em bạn ban cái việc vụ phần bên về sang qua hơn rất quá lắm
chưa quyết định chốt thống nhất làm dùng sẽ
""".split())
# Time words say *when*, not *what*: "khai trương ngày 8/12" vs "khuyến mãi ba ngày đầu" are different issues.
TIME_WORDS = frozenset("ngày tuần tháng năm giờ phút sáng chiều tối nay mai đầu cuối".split())

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _is_content(token: str) -> bool:
    return len(token) >= MIN_TOKEN_LEN and token not in STOP_WORDS and token not in TIME_WORDS


def content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if _is_content(t)}


def shared_words(text: str, shared: set[str]) -> set[str]:
    """Shared syllables of `text`, with runs of adjacent shared syllables merged into one word."""
    words: set[str] = set()
    run: list[str] = []
    for tok in [*_TOKEN.findall(text.lower()), ""]:
        if tok and _is_content(tok) and tok in shared:
            run.append(tok)
        elif run:
            words.add(" ".join(run))
            run = []
    return words


def all_evidence(item: Item) -> set[str]:
    ids = set(item.evidence)
    for h in item.history:
        ids.update(h.evidence)
    return ids


def common_tokens(items: list[Item]) -> frozenset[str]:
    """Tokens found in COMMON_DF or more decisions of the same meeting."""
    df = Counter(t for i in items if i.type.value == "decision" for t in content_tokens(i.content))
    return frozenset(t for t, n in df.items() if n >= COMMON_DF)


def same_issue(a: Item, b: Item, ignore: frozenset[str] = frozenset()) -> bool:
    if all_evidence(a) & all_evidence(b):
        return True
    ta, tb = content_tokens(a.content) - ignore, content_tokens(b.content) - ignore
    shared = ta & tb
    if not shared:
        return False
    n_words = min(len(shared_words(a.content, shared)), len(shared_words(b.content, shared)))
    if n_words < MIN_SHARED_TOKENS:
        return False
    return len(shared) / min(len(ta), len(tb)) >= MIN_OVERLAP


def is_conflict_pair(a: Item, b: Item, ignore: frozenset[str] = frozenset()) -> bool:
    if a.type.value != "decision" or b.type.value != "decision":
        return False
    sa, sb = (a.status.value if a.status else None), (b.status.value if b.status else None)
    mixed = (sa == "confirmed" and sb in LIVE_STATUSES) or (sb == "confirmed" and sa in LIVE_STATUSES)
    return mixed and same_issue(a, b, ignore)


def conflict_pairs(items: list[Item]) -> list[tuple[Item, Item]]:
    ignore = common_tokens(items)
    decisions = [i for i in items if i.type.value == "decision"]
    return [(a, b) for idx, a in enumerate(decisions) for b in decisions[idx + 1:] if is_conflict_pair(a, b, ignore)]


def flag_conflicts(items: list[Item]) -> int:
    """Add CONFLICT_FLAG to both items of every conflict pair (in place). Returns the number of pairs."""
    pairs = conflict_pairs(items)
    for a, b in pairs:
        for it in (a, b):
            if CONFLICT_FLAG not in it.flags:
                it.flags.append(CONFLICT_FLAG)
    return len(pairs)


def sibling_pairs(items: list[Item]) -> list[tuple[Item, Item]]:
    """Pairs of `confirmed` decisions about the same issue (two "final" answers to one question).

    Same ignore set and `same_issue` as `conflict_pairs`; does not flag anything itself.
    """
    ignore = common_tokens(items)
    decisions = [i for i in items if i.type.value == "decision"]
    confirmed = [i for i in decisions if i.status is not None and i.status.value == "confirmed"]
    return [(a, b) for idx, a in enumerate(confirmed) for b in confirmed[idx + 1:] if same_issue(a, b, ignore)]
