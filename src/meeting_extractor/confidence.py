"""Confidence = fixed formula over discrete labels (AI labels, pipeline result, meta, evidence text).

The AI never reports a number. Weights live in `confidence_weights.json`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import CLOSING_SIGNALS, EVIDENCE_DIRECTNESS, Item, ItemType, MeetingMeta, Utterance
from .parsing import base_speaker_name, is_anonymous_speaker

WEIGHTS_PATH = Path(__file__).with_name("confidence_weights.json")
NOISE_MARKERS = ("[không nghe rõ]", "[nói chồng]")


@lru_cache(maxsize=1)
def load_weights() -> dict:
    return json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def closer_status(closer: str, meta: MeetingMeta | None) -> str | None:
    """'can' | 'cannot' | None (no opinion). 'cannot' = anonymous speaker or not allowed to decide."""
    if is_anonymous_speaker(closer):
        return "cannot"
    if not (meta and meta.participants):
        return None
    name = _norm(base_speaker_name(closer))
    for p in meta.participants:
        if _norm(p.name) in (name, _norm(closer)):
            return "can" if p.can_decide else "cannot"
    return "cannot"


def _cited(item: Item, utterances: list[Utterance]) -> list[Utterance]:
    by_id = {u.id: u for u in utterances}
    order = {u.id: i for i, u in enumerate(utterances)}
    found = [by_id[e] for e in dict.fromkeys(item.evidence) if e in by_id]
    return sorted(found, key=lambda u: order[u.id])


def _label_terms(item: Item, w: dict) -> dict[str, float]:
    """Terms from AI labels; unknown or missing labels contribute nothing."""
    out: dict[str, float] = {}
    signal = item.closing_signal if item.closing_signal in CLOSING_SIGNALS else None
    if item.type == ItemType.decision and signal:
        out[f"closing_{signal}"] = w[f"closing_{signal}"]
    if item.evidence_directness in EVIDENCE_DIRECTNESS and item.evidence_directness == "inferred":
        out["evidence_inferred"] = w["evidence_inferred"]
    if item.contradicted_later is True:
        out["contradicted_later"] = w["contradicted_later"]
    if item.in_summary is True:
        out["in_summary"] = w["in_summary"]
    return out


def _code_terms(item: Item, cited: list[Utterance], meta: MeetingMeta | None, w: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    if item.type == ItemType.decision and cited:
        status = closer_status(cited[-1].speaker, meta)
        if status == "can":
            out["closer_can_decide"] = w["closer_can_decide"]
        elif status == "cannot":
            out["closer_unknown"] = w["closer_unknown"]
    if item.verify_passed is True:
        out["verify_passed"] = w["verify_passed"]
    elif item.verify_passed is False:
        out["verify_failed"] = w["verify_failed"]
    if len(cited) >= 2:
        out["multi_evidence"] = w["multi_evidence"]
    if any(m in u.text.lower() for u in cited for m in NOISE_MARKERS):
        out["noisy_evidence"] = w["noisy_evidence"]
    return out


def base_score(item: Item, w: dict) -> float:
    """Per-type base score; unknown types fall back to `default`."""
    table = w["base"]
    return float(table.get(item.type.value, table["default"]))


def compute_confidence(
    item: Item, utterances: list[Utterance], meta: MeetingMeta | None = None
) -> tuple[float, dict[str, float]]:
    """Return (score clamped to [min_score, max_score], breakdown of each applied term)."""
    w = load_weights()
    cited = _cited(item, utterances)
    breakdown: dict[str, float] = {"base": base_score(item, w)}
    breakdown.update(_label_terms(item, w))
    breakdown.update(_code_terms(item, cited, meta, w))
    raw = sum(breakdown.values())
    score = min(max(raw, w["min_score"]), w["max_score"])
    if score != raw:
        breakdown["clamp"] = score - raw
    return round(score, 4), {k: round(v, 4) for k, v in breakdown.items()}


def apply_cap(score: float, breakdown: dict[str, float], name: str, cap: float) -> float:
    """Lower `score` to `cap` if above it; record the (negative) delta under `name`."""
    if score <= cap:
        return score
    breakdown[name] = round(cap - score, 4)
    return cap
