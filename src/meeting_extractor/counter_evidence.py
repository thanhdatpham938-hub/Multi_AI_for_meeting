"""Deterministic search for utterances that may contradict, change or retract a decision.

For a `decision`, candidates are utterances located AFTER the item's latest evidence utterance (whole transcript,
not limited to the topic) that share at least one distinctive content word or one number/date with the item.
Agent 4 then judges whether any of them really contradicts the item; this module only narrows the search.
"""

from __future__ import annotations

import re

from .conflicts import content_tokens
from .models import Item, ItemType, Utterance

DEFAULT_LIMIT = 5
NUMBER_WEIGHT = 2  # a shared number/date is stronger evidence than a shared word

# 30, 15/11, 3.2, 1,5 ... ("x triệu/nghìn/%" is covered by the number itself). One-digit integers are too noisy.
_NUMBER = re.compile(r"\d+(?:[./,]\d+)*")


def number_tokens(text: str) -> set[str]:
    return {n for n in _NUMBER.findall(text) if len(n) >= 2}


def _latest_evidence_index(item: Item, utterances: list[Utterance]) -> int | None:
    """Position (in transcript order) of the item's latest evidence utterance, or None if none is valid."""
    wanted = set(item.evidence)
    positions = [idx for idx, u in enumerate(utterances) if u.id in wanted]
    return max(positions) if positions else None


def _score(u: Utterance, words: set[str], numbers: set[str]) -> int:
    return len(content_tokens(u.text) & words) + NUMBER_WEIGHT * len(number_tokens(u.text) & numbers)


def find_counter_candidates(
    item: Item, utterances: list[Utterance], limit: int = DEFAULT_LIMIT
) -> list[Utterance]:
    """Up to `limit` later utterances sharing words/numbers with a decision, best score first, then earliest."""
    if item.type != ItemType.decision or limit <= 0:
        return []
    last = _latest_evidence_index(item, utterances)
    if last is None:
        return []
    evidence_text = " ".join(u.text for u in utterances if u.id in set(item.evidence))
    words = content_tokens(item.content)
    numbers = number_tokens(item.content) | number_tokens(evidence_text)
    scored = [(_score(u, words, numbers), pos, u) for pos, u in enumerate(utterances[last + 1:], start=last + 1)]
    hits = sorted((s for s in scored if s[0] > 0), key=lambda s: (-s[0], s[1]))
    return [u for _, _, u in hits[:limit]]
