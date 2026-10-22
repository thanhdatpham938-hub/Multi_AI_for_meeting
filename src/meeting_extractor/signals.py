"""Code-only lexical signal tagger for utterances (no LLM, no cost).

Tags each utterance with closing signals (group A), "not a closing" frames
(group B), weak frames (group C) and neighbour-sensitive tags. All phrases live
in ``signal_lexicon.json``. ``tag_utterance`` returns EVERY matching tag; the
precedence between groups (B beats A) is decided by the caller.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, NamedTuple

from .models import MeetingMeta, Utterance
from .parsing import base_speaker_name, is_anonymous_speaker

LEXICON_PATH = Path(__file__).with_name("signal_lexicon.json")

GROUP_A = frozenset({"CHOT_RO", "CHOT_NGAM", "DONG_Y_NGAN"})
GROUP_B = frozenset({"DUA", "NGU_CANH_DUA", "GIA_DINH", "PHONG_DOAN", "CAU_HOI", "THUAT_LAI"})
GROUP_C = frozenset({"DE_XUAT", "HOAN", "DIEU_KIEN", "GIAO_VIEC", "MIA_MAI", "CHUYEN_Y", "TAM_THOI"})
NEIGHBOR_TAGS = frozenset({"DAO_NGUOC", "BO_SUNG_NGUOC", "VO_CHU", "XUNG_PHONG"})

TAG_ORDER: tuple[str, ...] = (
    "CHOT_RO", "CHOT_NGAM", "DONG_Y_NGAN",
    "DUA", "NGU_CANH_DUA", "GIA_DINH", "PHONG_DOAN", "CAU_HOI", "THUAT_LAI",
    "DE_XUAT", "HOAN", "DIEU_KIEN", "GIAO_VIEC", "MIA_MAI", "CHUYEN_Y", "TAM_THOI",
    "DAO_NGUOC", "BO_SUNG_NGUOC", "VO_CHU", "XUNG_PHONG",
)  # fmt: skip

_WORD_RE = re.compile(r"\w+")


@dataclass(frozen=True)
class Signal:
    tag: str  # e.g. "DUA"
    phrase: str  # matched phrase, lowercase, for display


# --------------------------------------------------------------------------- lexicon


@lru_cache(maxsize=1)
def load_lexicon() -> dict[str, Any]:
    return json.loads(LEXICON_PATH.read_text(encoding="utf-8"))


def windows() -> dict[str, int]:
    return {k: int(v) for k, v in load_lexicon()["windows"].items()}


def _build_labels() -> dict[str, str]:
    return dict(load_lexicon()["labels"])


TAG_LABELS: dict[str, str] = _build_labels()


def normalize(text: str) -> str:
    """NFC, lowercase, collapse whitespace. Vietnamese diacritics are kept."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).lower()).strip()


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


# --------------------------------------------------------------------------- matching


class _Entry(NamedTuple):
    pattern: re.Pattern[str]
    display: str | None
    not_after: frozenset[str]


class _Hit(NamedTuple):
    start: int
    end: int
    phrase: str


def _phrase_regex(phrase: str) -> str:
    body = re.escape(phrase).replace(r"\ ", r"\s+")
    prefix = r"(?<!\w)" if re.match(r"\w", phrase[0]) else ""
    suffix = r"(?!\w)" if re.match(r"\w", phrase[-1]) else ""
    return f"{prefix}{body}{suffix}"


def _compile_entry(raw: str | dict[str, Any]) -> _Entry:
    if isinstance(raw, str):
        return _Entry(re.compile(_phrase_regex(raw)), None, frozenset())
    return _Entry(re.compile(raw["re"]), raw.get("display"), frozenset(raw.get("not_after", [])))


@lru_cache(maxsize=None)
def _entries(tag: str, key: str = "phrases") -> tuple[_Entry, ...]:
    raws = load_lexicon()["tags"].get(tag, {}).get(key, [])
    return tuple(_compile_entry(r) for r in raws)


def _previous_word(norm: str, start: int) -> str | None:
    words = _words(norm[:start])
    return words[-1] if words else None


def _all_hits(norm: str, entries: Iterable[_Entry]) -> list[_Hit]:
    hits: list[_Hit] = []
    for entry in entries:
        for m in entry.pattern.finditer(norm):
            if entry.not_after and _previous_word(norm, m.start()) in entry.not_after:
                continue
            hits.append(_Hit(m.start(), m.end(), entry.display or m.group(0)))
    return sorted(hits, key=lambda h: (h.start, -(h.end - h.start)))


def _overlaps(hit: _Hit, others: Iterable[_Hit]) -> bool:
    return any(hit.start < o.end and o.start < hit.end for o in others)


def _first_hit(norm: str, tag: str) -> _Hit | None:
    """Leftmost, longest phrase of ``tag`` not covered by one of its exceptions."""
    exceptions = _all_hits(norm, _entries(tag, "exceptions"))
    for hit in _all_hits(norm, _entries(tag)):
        if not _overlaps(hit, exceptions):
            return hit
    return None


# --------------------------------------------------------------------------- clause helpers


def _clause_punct() -> str:
    return load_lexicon()["clause_punctuation"]


def _clause_before(norm: str, start: int) -> str:
    seg = norm[:start]
    cut = max((seg.rfind(c) for c in _clause_punct()), default=-1)
    return seg[cut + 1 :]


def _clause_after(norm: str, end: int) -> str:
    seg = norm[end:]
    cuts = [i for i in (seg.find(c) for c in _clause_punct()) if i >= 0]
    return seg[: min(cuts)] if cuts else seg


def _is_question(text: str, norm: str) -> bool:
    if "?" in text:  # any sentence of the utterance asks something
        return True
    stripped = norm.rstrip(" " + _clause_punct() + "…").strip()
    for ending in load_lexicon()["tags"]["CAU_HOI"]["endings"]:
        if re.search(_phrase_regex(ending) + r"$", stripped):
            return True
    return False


# --------------------------------------------------------------------------- CHOT_RO


def _condition_spans(norm: str, cfg: dict[str, Any]) -> list[tuple[int, int]]:
    openers = "|".join(re.escape(o) for o in cfg["condition_openers"])
    pattern = rf"(?<!\w)(?:{openers})(?!\w)(.*?)(?:(?<!\w)thì(?!\w)|[,.;!?]|$)"
    return [m.span(1) for m in re.finditer(pattern, norm)]


def _is_negated(norm: str, hit: _Hit, cfg: dict[str, Any]) -> bool:
    before = _clause_before(norm, hit.start)
    for neutral in cfg["negation_neutralizers"]:
        before = re.sub(_phrase_regex(neutral), " ", before)
    window = _words(before)[-cfg["negation_window_before"] :]
    if any(w in cfg["negators_before"] for w in window):
        return True
    after = _words(_clause_after(norm, hit.end))[: cfg["negation_window_after"]]
    return any(w in cfg["negators_after"] for w in after)


def _sentence_negated(norm: str, hit: _Hit, cfg: dict[str, Any]) -> bool:
    start = max(norm.rfind(c, 0, hit.start) for c in ".!?;") + 1
    ends = [i for i in (norm.find(c, hit.end) for c in ".!?;") if i >= 0]
    sentence = norm[start : min(ends) if ends else len(norm)]
    return any(re.search(_phrase_regex(p), sentence) for p in cfg["sentence_negation_phrases"])


def _chot_ro(norm: str) -> _Hit | None:
    cfg = load_lexicon()["tags"]["CHOT_RO"]
    suppress = _all_hits(norm, [_compile_entry(p) for p in cfg["suppress_phrases"]])
    words = "|".join(re.escape(w) for w in cfg["rebuttal_words"])
    rebuttals = [
        _Hit(m.start(), m.end(), m.group(0)) for m in re.finditer(rf"(?<!\w)({words}) gì mà \1(?!\w)", norm)
    ]
    conditions = _condition_spans(norm, cfg)
    for hit in _all_hits(norm, _entries("CHOT_RO")):
        if _overlaps(hit, suppress) or _overlaps(hit, rebuttals):
            continue
        if any(s <= hit.start < e for s, e in conditions):
            continue
        if _is_negated(norm, hit, cfg) or _sentence_negated(norm, hit, cfg):
            continue
        return hit
    return None


# --------------------------------------------------------------------------- CHOT_NGAM / DONG_Y_NGAN


def _chot_ngam(norm: str, is_question: bool) -> str | None:
    cfg = load_lexicon()["tags"]["CHOT_NGAM"]
    if is_question:
        return None
    body = norm.lstrip(" " + _clause_punct())
    for opener in sorted(cfg["openers"], key=len, reverse=True):
        m = re.match(_phrase_regex(opener), body)
        if not m:
            continue
        content = [w for w in _words(body[m.end() :]) if w not in cfg["filler_words"]]
        if len(content) >= cfg["min_content_words"]:
            return opener
    tail = norm.rstrip(" " + _clause_punct())
    for ending in cfg["endings"]:
        if re.search(_phrase_regex(ending) + r"$", tail):
            return ending
    return None


def _dong_y_ngan(norm: str, is_question: bool) -> str | None:
    cfg = load_lexicon()["tags"]["DONG_Y_NGAN"]
    tokens = _words(norm)
    if is_question or not tokens or len(tokens) > cfg["max_words"]:
        return None
    agree = sorted((a.split() for a in cfg["agree"]), key=len, reverse=True)
    i, found = 0, False
    while i < len(tokens):
        match = next((a for a in agree if tokens[i : i + len(a)] == a), None)
        if match:
            found, i = True, i + len(match)
        elif tokens[i] in cfg["fillers"]:
            i += 1
        else:
            return None
    return " ".join(tokens) if found else None


# --------------------------------------------------------------------------- GIA_DINH / GIAO_VIEC


def _hay_opener(norm: str) -> _Hit | None:
    cfg = load_lexicon()["tags"]["GIA_DINH"]
    particles = "|".join(re.escape(p) for p in cfg["hay_lead_particles"])
    blocked = "|".join(re.escape(p) for p in cfg["hay_not_followed_by"])
    pattern = (
        rf"(?:^|[,;.!?:]\s*)(?:(?:{particles})\s+)?(hay)(?!\w)\s+(?!(?:{blocked})(?!\w))\w+"
    )
    m = re.search(pattern, norm)
    return _Hit(m.start(1), m.end(1), "hay") if m else None


def _gia_dinh(norm: str) -> _Hit | None:
    hits = [h for h in (_first_hit(norm, "GIA_DINH"), _hay_opener(norm)) if h]
    return min(hits, key=lambda h: h.start) if hits else None


def _name_verb_hit(text: str, name: str, verbs: list[list[str]], window: int) -> str | None:
    """Return "<name> <verb>" if a task verb follows ``name`` within ``window`` words."""
    for form in {name, name[:1].upper() + name[1:]}:
        for m in re.finditer(rf"(?<!\w){re.escape(form)}(?!\w)", text):
            tokens = _words(normalize(text[m.end() :]))
            for k in range(window):
                for verb in verbs:
                    if tokens[k : k + len(verb)] == verb:
                        return f"{normalize(name)} {' '.join(verb)}"
    return None


def _giao_viec(u: Utterance, norm: str, names: Iterable[str]) -> str | None:
    cfg = load_lexicon()["tags"]["GIAO_VIEC"]
    hit = _first_hit(norm, "GIAO_VIEC")
    own = normalize(base_speaker_name(u.speaker))
    verbs = [v.split() for v in cfg["verbs"]]
    text = unicodedata.normalize("NFC", u.text)
    for name in names:
        if len(name) < 2 or normalize(name) == own:
            continue
        found = _name_verb_hit(text, name, verbs, cfg["name_window"])
        if found:
            return found
    return hit.phrase if hit else None


def _thuat_lai(norm: str, names: Iterable[str]) -> _Hit | None:
    cfg = load_lexicon()["tags"]["THUAT_LAI"]
    hits = [h for h in [_first_hit(norm, "THUAT_LAI")] if h]
    for name in names:
        for suffix in cfg["name_suffixes"]:
            m = re.search(_phrase_regex(f"{normalize(name)} {suffix}"), norm)
            if m:
                hits.append(_Hit(m.start(), m.end(), m.group(0)))
    return min(hits, key=lambda h: h.start) if hits else None


# --------------------------------------------------------------------------- per-utterance tagging


def _core_tags(u: Utterance, norm: str, names: list[str]) -> dict[str, str]:
    """Tags that depend only on the utterance itself: tag -> matched phrase."""
    found: dict[str, str] = {}
    question = _is_question(u.text, norm)

    def put(tag: str, phrase: str | None) -> None:
        if phrase is not None:
            found[tag] = phrase

    chot = _chot_ro(norm)
    put("CHOT_RO", chot.phrase if chot else None)
    put("CHOT_NGAM", _chot_ngam(norm, question))
    put("DONG_Y_NGAN", _dong_y_ngan(norm, question))
    for tag in ("DUA", "PHONG_DOAN", "DE_XUAT", "HOAN", "DIEU_KIEN", "CHUYEN_Y", "TAM_THOI",
                "DAO_NGUOC", "VO_CHU", "XUNG_PHONG"):  # fmt: skip
        hit = _first_hit(norm, tag)
        put(tag, hit.phrase if hit else None)
    gia_dinh = _gia_dinh(norm)
    put("GIA_DINH", gia_dinh.phrase if gia_dinh else None)
    put("CAU_HOI", "?" if question else None)
    thuat_lai = _thuat_lai(norm, names)
    put("THUAT_LAI", thuat_lai.phrase if thuat_lai else None)
    put("GIAO_VIEC", _giao_viec(u, norm, names))
    if "CHOT_RO" not in found:
        mia_mai = _first_hit(norm, "MIA_MAI")
        put("MIA_MAI", mia_mai.phrase if mia_mai else None)
    return found


def _opens_with(norm: str, openers: list[str]) -> str | None:
    body = norm.lstrip(" " + _clause_punct())
    for opener in sorted(openers, key=len, reverse=True):
        if re.match(_phrase_regex(opener), body):
            return opener
    return None


def tag_utterance(u: Utterance, prev: Utterance | None, names: Iterable[str]) -> list[Signal]:
    """All signals matching ``u``. ``prev`` is the utterance right before it in the transcript."""
    name_list = [n for n in names if n]
    norm = normalize(u.text)
    found = _core_tags(u, norm, name_list)
    if prev is not None:
        prev_norm = normalize(prev.text)
        prev_found = _core_tags(prev, prev_norm, name_list)
        enders = load_lexicon()["tags"]["NGU_CANH_DUA"]["joke_enders"]
        stops_joke = any(re.search(_phrase_regex(e), prev_norm) for e in enders)
        if "DUA" in prev_found and "CHOT_RO" not in found and not stops_joke:
            found["NGU_CANH_DUA"] = prev_found["DUA"]
        if GROUP_A & prev_found.keys():
            opener = _opens_with(norm, load_lexicon()["tags"]["BO_SUNG_NGUOC"]["openers"])
            if opener:
                found["BO_SUNG_NGUOC"] = opener
    return [Signal(tag, found[tag]) for tag in TAG_ORDER if tag in found]


def _transcript_names(utterances: list[Utterance], meta: MeetingMeta | None) -> list[str]:
    names: list[str] = []
    if meta:
        names += [base_speaker_name(p.name) for p in meta.participants]
    names += [base_speaker_name(u.speaker) for u in utterances if not is_anonymous_speaker(u.speaker)]
    return list(dict.fromkeys(n for n in names if n))


def tag_transcript(utterances: list[Utterance], meta: MeetingMeta | None) -> dict[str, list[Signal]]:
    """Signals for every utterance id (empty list when nothing matched)."""
    names = _transcript_names(utterances, meta)
    tagged: dict[str, list[Signal]] = {}
    prev: Utterance | None = None
    for u in utterances:
        tagged[u.id] = tag_utterance(u, prev, names)
        prev = u
    return tagged


# --------------------------------------------------------------------------- helpers for callers


def tags_of(signals: list[Signal]) -> set[str]:
    return {s.tag for s in signals}


def closing_utterance_id(
    evidence: list[str], tagged: dict[str, list[Signal]], position: dict[str, int]
) -> str | None:
    """The utterance that closes an item.

    Preference: latest CHOT_RO without a group B tag, then latest CHOT_NGAM, then latest DONG_Y_NGAN, then the latest
    evidence utterance. A trailing "Ok." therefore never outranks an earlier explicit "chốt".
    """
    valid = [e for e in evidence if e in position]
    if not valid:
        return None
    tag_sets = {e: tags_of(tagged.get(e, [])) for e in valid}
    tiers = (
        lambda t: "CHOT_RO" in t and not t & GROUP_B,
        lambda t: "CHOT_NGAM" in t,
        lambda t: "DONG_Y_NGAN" in t,
        lambda t: True,
    )
    for accepts in tiers:
        pool = [e for e in valid if accepts(tag_sets[e])]
        if pool:
            return max(pool, key=lambda e: position[e])
    return None


def _clean_phrase(phrase: str) -> str:
    return phrase.replace("<", "").replace(">", "")


def _format_signal(signal: Signal) -> str:
    lex = load_lexicon()
    label = lex["block_labels"].get(signal.tag, signal.tag)
    phrase = _clean_phrase(signal.phrase)
    template = lex["block_templates"].get(signal.tag)
    detail = template.format(phrase=phrase) if template else f'"{phrase}"'
    return f"{label} ({detail})"


def format_signals_block(utterance_ids: list[str], tagged: dict[str, list[Signal]]) -> str:
    """Prompt block listing only utterances that carry at least one signal."""
    lines = [
        f"{uid}: " + "; ".join(_format_signal(s) for s in tagged[uid])
        for uid in utterance_ids
        if tagged.get(uid)
    ]
    if not lines:
        return ""
    return "<code_signals>\n" + "\n".join(lines) + "\n</code_signals>"
