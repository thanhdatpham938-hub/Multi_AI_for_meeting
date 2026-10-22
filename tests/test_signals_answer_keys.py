"""Signal tagger vs the 12 answer keys (7 short + 5 long). Offline, no LLM.

Main guarantee: no real closing sentence of a confirmed decision carries a group B tag.
"""

from __future__ import annotations

import pytest

from eval.signal_report import (
    MUST_CATCH_B,
    MUST_CATCH_C,
    MUST_NEIGHBOR,
    MUST_REVERSE,
    REVERSAL_TAGS,
    Case,
    closings_with_group_b,
    load_cases,
    real_closings,
    reversal_after_closing,
)
from meeting_extractor.signals import GROUP_A, GROUP_B, closing_utterance_id, tags_of, windows


@pytest.fixture(scope="module")
def cases() -> dict[str, Case]:
    loaded = load_cases()
    assert len(loaded) == 12
    return {c.label: c for c in loaded}


def test_every_utterance_is_tagged_with_a_list(cases: dict[str, Case]) -> None:
    for case in cases.values():
        assert set(case.tagged) == {u.id for u in case.utterances}


def test_real_closing_sentences_never_carry_group_b(cases: dict[str, Case]) -> None:
    offenders = [
        f"{c.label} {uid}: {[s.tag for s in sigs]}" for c in cases.values() for uid, sigs in closings_with_group_b(c)
    ]
    assert offenders == []


def test_section4_closing_of_confirmed_decisions_free_of_group_b(cases: dict[str, Case]) -> None:
    """Closing per section 4 (latest group A sentence in evidence). Supporting evidence may be a question
    (e.g. case2 u128 'Còn người dựng video thì sao chị?', the question that leads to the answer) and is not judged here."""
    offenders = []
    for c in cases.values():
        for item in c.answer.get("items", []):
            if item.get("type") != "decision" or item.get("status") != "confirmed":
                continue
            cid = closing_utterance_id(item["evidence"], c.tagged, c.position)
            bad = tags_of(c.tagged.get(cid, [])) & GROUP_B if cid else set()
            if bad:
                offenders.append(f"{c.label} {cid}: {sorted(bad)}")
    assert offenders == []


def test_closing_id_of_answer_evidence_is_group_a_or_a_listed_sentence(cases: dict[str, Case]) -> None:
    for c in cases.values():
        for item in c.answer.get("items", []):
            if item.get("type") == "decision" and item.get("status") == "confirmed":
                cid = closing_utterance_id(item["evidence"], c.tagged, c.position)
                assert cid in item["evidence"]


@pytest.mark.parametrize("label", sorted(MUST_CATCH_B))
def test_must_catch_group_b(cases: dict[str, Case], label: str) -> None:
    for uid in MUST_CATCH_B[label]:
        assert tags_of(cases[label].tagged[uid]) & GROUP_B, f"{label} {uid} lacks a group B tag"


@pytest.mark.parametrize("label,uid,tag", MUST_CATCH_C)
def test_must_catch_group_c(cases: dict[str, Case], label: str, uid: str, tag: str) -> None:
    assert tag in tags_of(cases[label].tagged[uid])


@pytest.mark.parametrize("label,uid", MUST_REVERSE)
def test_reversal_sentences_are_flagged(cases: dict[str, Case], label: str, uid: str) -> None:
    assert tags_of(cases[label].tagged[uid]) & REVERSAL_TAGS


def test_specific_reversal_tags(cases: dict[str, Case]) -> None:
    assert "DAO_NGUOC" in tags_of(cases["case5"].tagged["u027"])
    assert "DAO_NGUOC" in tags_of(cases["case4"].tagged["u046"])
    assert "HOAN" in tags_of(cases["case3"].tagged["u087"])
    assert "BO_SUNG_NGUOC" in tags_of(cases["case3"].tagged["u024"])


@pytest.mark.parametrize("label,uid,tag", MUST_NEIGHBOR)
def test_ownerless_and_volunteer_chain(cases: dict[str, Case], label: str, uid: str, tag: str) -> None:
    assert tag in tags_of(cases[label].tagged[uid])


def test_no_reversal_right_after_a_real_closing(cases: dict[str, Case]) -> None:
    span = windows()["reversal_after"]
    offenders = [
        f"{c.label} {closing} -> {nid}: {[s.tag for s in sigs]}"
        for c in cases.values()
        for closing, nid, sigs in reversal_after_closing(c, span)
    ]
    assert offenders == []


def test_real_closings_exist_and_have_group_a_or_are_reported(cases: dict[str, Case]) -> None:
    """Closings without any group A tag are allowed (the code then only caps the score), but must be few."""
    total = no_a = 0
    for c in cases.values():
        for uid in set(real_closings(c)):
            total += 1
            no_a += not (tags_of(c.tagged[uid]) & GROUP_A)
    assert total >= 25
    assert no_a / total < 0.5
