"""Provenance checks: verbatim quotes and per-field source utterances (Mission 3, M4B)."""

from __future__ import annotations

import re
import string
import unicodedata

from .confidence import closer_status
from .models import Item, MeetingMeta, Utterance
from .parsing import base_speaker_name

# ASCII punctuation plus common typographic marks; Vietnamese diacritics are never touched.
_EDGE_PUNCT = string.punctuation + "…“”‘’«»–—"


def normalize_text(text: str) -> str:
    """Lowercase, collapse whitespace, strip edge punctuation. Keeps Vietnamese diacritics."""
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(_EDGE_PUNCT + " ")


def quote_matches(quote: str, utterance_text: str) -> bool:
    q = normalize_text(quote)
    return bool(q) and q in normalize_text(utterance_text)


def check_quotes(
    item: Item, by_id: dict[str, Utterance]
) -> tuple[dict[str, str], list[str], list[str]]:
    """Return (kept quotes, ids whose quote does not match, ids not cited in `evidence`).

    Mismatching quotes are kept so the reviewer can see them; orphan pairs are dropped.
    """
    kept: dict[str, str] = {}
    mismatched: list[str] = []
    orphans: list[str] = []
    cited = set(item.evidence)
    for uid, quote in item.evidence_quotes.items():
        if uid not in cited:
            orphans.append(uid)
            continue
        kept[uid] = quote
        if uid not in by_id or not quote_matches(quote, by_id[uid].text):
            mismatched.append(uid)
    return kept, mismatched, orphans


def sanitize_field_evidence(
    field_evidence: dict[str, list[str]], by_id: dict[str, Utterance]
) -> tuple[dict[str, list[str]], list[str]]:
    """Drop source ids that do not exist. Returns (cleaned mapping, dropped ids)."""
    cleaned: dict[str, list[str]] = {}
    dropped: list[str] = []
    for key, ids in field_evidence.items():
        good = [i for i in dict.fromkeys(ids) if i in by_id]
        dropped.extend(i for i in dict.fromkeys(ids) if i not in by_id)
        if good:
            cleaned[key] = good
    return cleaned, dropped


def _same_person(a: str, b: str) -> bool:
    na, nb = normalize_text(base_speaker_name(a)), normalize_text(base_speaker_name(b))
    return bool(na) and na == nb


def _may_assign(speaker: str, meta: MeetingMeta | None) -> bool:
    """Whether `speaker` may hand out work. Without participants in meta, any named speaker may."""
    if meta and meta.participants:
        return closer_status(speaker, meta) == "can"
    return closer_status(speaker, meta) != "cannot"


def owner_from_sources(
    owner: str, sources: list[Utterance], utterances: list[Utterance], meta: MeetingMeta | None
) -> bool:
    """Owner is valid if named in a source, is a source's speaker, or was delegated to
    ("A asks, B: I decide it myself": source spoken by an authority, the previous line by owner)."""
    name = normalize_text(base_speaker_name(owner))
    if not name:
        return False
    position = {u.id: i for i, u in enumerate(utterances)}
    for src in sources:
        if name in normalize_text(src.text) or _same_person(owner, src.speaker):
            return True
        idx = position.get(src.id, 0)
        if idx > 0 and _may_assign(src.speaker, meta) and _same_person(owner, utterances[idx - 1].speaker):
            return True
    return False


def deadline_from_sources(deadline: str, sources: list[Utterance]) -> bool:
    d = normalize_text(deadline)
    return bool(d) and any(d in normalize_text(u.text) for u in sources)
