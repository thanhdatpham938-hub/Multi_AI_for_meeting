"""Offline checks of every answer key (7 short + 5 long): valid JSON, IDs exist, new keys well-formed."""

import json
from pathlib import Path
from typing import Any

import pytest

from eval.metrics import evaluate_case
from meeting_extractor.conflicts import flag_conflicts
from meeting_extractor.models import HistoryEntry, Item, MeetingMeta, RunResult, Topic
from meeting_extractor.parsing import parse_file

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
LONG_DIR = ROOT / "test_cases_3_muc_do (1)"

SCOPES = {"ephemeral", "project", "reusable"}
TYPES = {"decision", "action", "blocker", "request", "open_issue", "knowledge"}
STATUSES = {"proposed", "superseded", "confirmed", "conditional", "deferred", "open"}


def _cases() -> list[tuple[str, Path, Path]]:
    cases = [(f"tc{n}", FIXTURES / f"tc{n}.txt", FIXTURES / f"tc{n}.expected.json") for n in range(1, 8)]
    for d in sorted(LONG_DIR.glob("case*")):
        cases.append((d.name, d / "transcript.txt", d / "expected.json"))
    return cases


CASES = _cases()
LONG_CASES = [c for c in CASES if c[0].startswith("case")]


def _load(name: str, transcript: Path, answer: Path) -> tuple[list, dict[str, Any]]:
    utts, _ = parse_file(transcript)
    return utts, json.loads(answer.read_text(encoding="utf-8"))


def _referenced_ids(answer: dict[str, Any]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for i, it in enumerate(answer.get("items", [])):
        refs += [(f"items[{i}].evidence", u) for u in it.get("evidence", [])]
        for s in it.get("history_superseded", []):
            refs += [(f"items[{i}].history_superseded", u) for u in s.get("evidence", [])]
    for i, rule in enumerate(answer.get("forbidden", [])):
        refs += [(f"forbidden[{i}].evidence_only", u) for u in rule.get("evidence_only", [])]
    for i, group in enumerate(answer.get("same_topic", [])):
        refs += [(f"same_topic[{i}]", u) for u in group]
    return refs


def test_five_long_cases_present() -> None:
    assert len(LONG_CASES) == 5
    for _, transcript, answer in LONG_CASES:
        assert transcript.exists() and answer.exists()


@pytest.mark.parametrize("name,transcript,answer", CASES, ids=[c[0] for c in CASES])
def test_answer_ids_exist_in_transcript(name: str, transcript: Path, answer: Path) -> None:
    utts, data = _load(name, transcript, answer)
    known = {u.id for u in utts}
    missing = [(where, uid) for where, uid in _referenced_ids(data) if uid not in known]
    assert missing == []


@pytest.mark.parametrize("name,transcript,answer", CASES, ids=[c[0] for c in CASES])
def test_answer_item_shape(name: str, transcript: Path, answer: Path) -> None:
    _, data = _load(name, transcript, answer)
    assert data["items"], "answer key has no items"
    for it in data["items"]:
        assert it["type"] in TYPES
        assert it["evidence"], f"item without evidence: {it['content']}"
        statuses = set(it.get("accept_statuses", [])) | ({it["status"]} if it.get("status") else set())
        assert statuses <= STATUSES
        if it["type"] == "decision":
            assert statuses, f"decision without status: {it['content']}"
        if "accept_owners" in it:
            assert isinstance(it["accept_owners"], list)
            assert all(o is None or isinstance(o, str) for o in it["accept_owners"])
    for rule in data.get("forbidden", []):
        assert rule["type"] in TYPES and rule["evidence_only"] and set(rule["statuses"]) <= STATUSES
    for f in data.get("expect_flags_any", []):
        assert isinstance(f, str) and f
    if "expect_no_conflicts" in data:
        assert isinstance(data["expect_no_conflicts"], bool)


@pytest.mark.parametrize("name,transcript,answer", CASES, ids=[c[0] for c in CASES])
def test_new_keys_values(name: str, transcript: Path, answer: Path) -> None:
    _, data = _load(name, transcript, answer)
    for it in data["items"]:
        if it["type"] == "knowledge" and "knowledge_scope" in it:
            assert it["knowledge_scope"] in SCOPES
        if it["type"] == "knowledge" and name.startswith("case"):
            assert it.get("knowledge_scope") in SCOPES, f"long-case knowledge needs a scope: {it['content']}"
        if "knowledge_scope" in it:
            assert it["type"] == "knowledge"
        if "pending_on" in it:
            assert isinstance(it["pending_on"], str) and it["pending_on"].strip()
            assert it.get("status") == "deferred" or "deferred" in it.get("accept_statuses", [])
        if it.get("status") == "deferred" and name.startswith("case"):
            assert it.get("pending_on"), f"deferred item needs pending_on: {it['content']}"


@pytest.mark.parametrize("name,transcript,answer", LONG_CASES, ids=[c[0] for c in LONG_CASES])
def test_long_case_has_five_required_items(name: str, transcript: Path, answer: Path) -> None:
    _, data = _load(name, transcript, answer)
    required = [it for it in data["items"] if not it.get("optional")]
    assert len(required) >= 5


def test_long_case_specific_keys() -> None:
    by_name = {n: json.loads(a.read_text(encoding="utf-8")) for n, _, a in LONG_CASES}
    case3 = next(v for k, v in by_name.items() if k.startswith("case3"))
    assert case3["known_limitation"] is True
    assert case3["expect_flags_any"] == ["unresolved_reference"]
    for prefix in ("case2", "case4", "case5"):
        assert next(v for k, v in by_name.items() if k.startswith(prefix))["expect_no_conflicts"] is True
    assert json.loads((FIXTURES / "tc7.expected.json").read_text(encoding="utf-8"))["expect_flags_any"] == [
        "unresolved_reference"
    ]


def _oracle(name: str, transcript: Path, data: dict[str, Any]) -> RunResult:
    """A RunResult built from the answer key (no rules except conflict flagging, as the pipeline will do)."""
    utts, _ = parse_file(transcript)
    items = []
    for idx, exp in enumerate(data["items"]):
        accepted = list(exp.get("accept_statuses", []))
        status = exp.get("status") if exp.get("status") in (accepted or [exp.get("status")]) else accepted[0]
        history = [HistoryEntry(status="superseded", content=s["content"], evidence=s["evidence"])
                   for s in exp.get("history_superseded", [])]
        items.append(Item(
            item_id="", type=exp["type"], topic_id=f"i{idx:02d}", topic="T", content=exp["content"],
            status=status if exp["type"] == "decision" else None, condition=exp.get("condition"),
            owner=exp.get("owner"), deadline=exp.get("deadline"), evidence=exp["evidence"], history=history,
            flags=list(exp.get("required_flags", [])) + (data.get("expect_flags_any", []) if idx == 0 else []),
            confidence=0.9))
    flag_conflicts(items)  # same shared rule the pipeline applies; flagged pairs are allowed by expect_no_conflicts
    topic = Topic(topic_id="t01", title="T", utterance_ids=[u.id for u in utts])
    return RunResult(run_id="x", source_file=name, model_light="l", model_strong="s", prompt_versions={},
                     utterances=utts, topics=[topic], items=items, meta=MeetingMeta())


@pytest.mark.parametrize("name,transcript,answer", CASES, ids=[c[0] for c in CASES])
def test_oracle_runs_without_error(name: str, transcript: Path, answer: Path) -> None:
    _, data = _load(name, transcript, answer)
    rep = evaluate_case(_oracle(name, transcript, data), data)
    # Short cases and long cases alike must be self-consistent: the oracle satisfies its own key,
    # apart from min/max confidence which the oracle sets generically.
    errors = [e for e in rep.errors if "Confidence" not in e]
    assert errors == []
