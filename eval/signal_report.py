"""Offline report of the lexical signal tagger over the 12 answer-key transcripts. Costs nothing.

Usage: uv run python eval/signal_report.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from meeting_extractor.models import MeetingMeta, Utterance  # noqa: E402
from meeting_extractor.parsing import load_meta, parse_file  # noqa: E402
from meeting_extractor.signals import (  # noqa: E402
    GROUP_A,
    GROUP_B,
    TAG_ORDER,
    Signal,
    tag_transcript,
    tags_of,
    windows,
)

FIXTURES = ROOT / "tests" / "fixtures"
LONG_DIR = ROOT / "test_cases_3_muc_do (1)"

# Utterances the tagger must flag with at least one group B tag (PLAN_SIGNALS.md section 9).
MUST_CATCH_B: dict[str, list[str]] = {
    "tc3": ["u003", "u004"],
    "tc4": ["u005", "u006"],
    "tc7": ["u005"],
    "case1": ["u040", "u086", "u087"],
    "case2": ["u027", "u028", "u029", "u051", "u052", "u077"],
    "case3": ["u029", "u071", "u050"],
    "case4": ["u065", "u066"],
    "case5": ["u045", "u056", "u060", "u089", "u090", "u092"],
}

# (case, utterance id, required tag) for group C frames.
MUST_CATCH_C: list[tuple[str, str, str]] = [
    ("case2", "u045", "MIA_MAI"),
    ("case5", "u020", "MIA_MAI"),
    ("case2", "u012", "DE_XUAT"),
    ("tc7", "u006", "CHUYEN_Y"),
]

# Reversal pairs (section 14.2): the flipping utterance must carry one of the accepted tags.
REVERSAL_TAGS = frozenset({"DAO_NGUOC", "BO_SUNG_NGUOC", "HOAN"})
MUST_REVERSE: list[tuple[str, str]] = [("case5", "u027"), ("case4", "u046"), ("case3", "u087"), ("case3", "u024")]

# Section 16: (case, utterance id, required tag).
MUST_NEIGHBOR: list[tuple[str, str, str]] = [
    ("case2", "u069", "VO_CHU"),
    ("case2", "u070", "XUNG_PHONG"),
    ("case2", "u071", "HOAN"),
]


@dataclass
class Case:
    label: str  # "tc1" ... "case5"
    utterances: list[Utterance]
    answer: dict[str, Any]
    tagged: dict[str, list[Signal]]
    position: dict[str, int]


def case_paths() -> list[tuple[str, Path, Path, Path | None]]:
    paths: list[tuple[str, Path, Path, Path | None]] = []
    for n in range(1, 8):
        paths.append((f"tc{n}", FIXTURES / f"tc{n}.txt", FIXTURES / f"tc{n}.expected.json", None))
    for d in sorted(LONG_DIR.glob("case*")):
        paths.append((d.name.split("_")[0], d / "transcript.txt", d / "expected.json", d / "meeting_meta.json"))
    return paths


def load_cases() -> list[Case]:
    cases: list[Case] = []
    for label, transcript, answer, meta_path in case_paths():
        utterances, _ = parse_file(transcript)
        meta: MeetingMeta | None = load_meta(meta_path) if meta_path and meta_path.exists() else None
        cases.append(
            Case(
                label=label,
                utterances=utterances,
                answer=json.loads(answer.read_text(encoding="utf-8")),
                tagged=tag_transcript(utterances, meta),
                position={u.id: i for i, u in enumerate(utterances)},
            )
        )
    return cases


def real_closings(case: Case) -> list[str]:
    """First evidence id of every confirmed decision in the answer key (the true closing utterance)."""
    return [
        e["evidence"][0]
        for e in case.answer.get("items", [])
        if e.get("type") == "decision" and e.get("status") == "confirmed" and e.get("evidence")
    ]


def closings_with_group_b(case: Case) -> list[tuple[str, list[Signal]]]:
    out = []
    for uid in dict.fromkeys(real_closings(case)):
        bad = [s for s in case.tagged.get(uid, []) if s.tag in GROUP_B]
        if bad:
            out.append((uid, bad))
    return out


def neighbors_after(case: Case, uid: str, span: int) -> list[str]:
    pos = case.position.get(uid)
    if pos is None:
        return []
    return [u.id for u in case.utterances[pos + 1 : pos + 1 + span]]


def reversal_after_closing(case: Case, span: int) -> list[tuple[str, str, list[Signal]]]:
    """(closing id, neighbour id, tags) where a real closing is followed by DAO_NGUOC / BO_SUNG_NGUOC."""
    hits = []
    for uid in dict.fromkeys(real_closings(case)):
        for nid in neighbors_after(case, uid, span):
            bad = [s for s in case.tagged[nid] if s.tag in {"DAO_NGUOC", "BO_SUNG_NGUOC"}]
            if bad:
                hits.append((uid, nid, bad))
    return hits


def missed_must_catch(cases: list[Case]) -> list[str]:
    by_label = {c.label: c for c in cases}
    missed: list[str] = []
    for label, ids in MUST_CATCH_B.items():
        for uid in ids:
            if not tags_of(by_label[label].tagged[uid]) & GROUP_B:
                missed.append(f"{label} {uid} (nhóm B)")
    for label, uid, tag in MUST_CATCH_C:
        if tag not in tags_of(by_label[label].tagged[uid]):
            missed.append(f"{label} {uid} ({tag})")
    for label, uid in MUST_REVERSE:
        if not tags_of(by_label[label].tagged[uid]) & REVERSAL_TAGS:
            missed.append(f"{label} {uid} (đảo ý)")
    for label, uid, tag in MUST_NEIGHBOR:
        if tag not in tags_of(by_label[label].tagged[uid]):
            missed.append(f"{label} {uid} ({tag})")
    return missed


def build_report(cases: list[Case]) -> str:
    counts: Counter[str] = Counter()
    total = tagged_any = 0
    for case in cases:
        for sigs in case.tagged.values():
            total += 1
            tagged_any += bool(sigs)
            counts.update(tags_of(sigs))
    lines = [f"# Báo cáo bộ dò tín hiệu ({len(cases)} transcript, {total} câu)", ""]
    lines += ["| Nhãn | Nhóm | Số câu khớp |", "| --- | --- | ---: |"]
    for tag in TAG_ORDER:
        group = "A" if tag in GROUP_A else "B" if tag in GROUP_B else "C/lân cận"
        lines.append(f"| {tag} | {group} | {counts[tag]} |")
    lines += ["", f"Tỷ lệ câu có ít nhất một nhãn: {tagged_any}/{total} = {tagged_any / total:.1%}", ""]
    lines += _closing_section(cases)
    missed = missed_must_catch(cases)
    lines += ["", f"Câu 'phải bắt được' bị sót: {len(missed)}"] + [f"- {m}" for m in missed]
    lines += ["", f"Cửa sổ trong lexicon: {windows()}"]
    return "\n".join(lines)


def _closing_section(cases: list[Case]) -> list[str]:
    span = windows()["reversal_after"]
    by_b: list[str] = []
    after: list[str] = []
    n_closings = 0
    for case in cases:
        n_closings += len(set(real_closings(case)))
        for uid, sigs in closings_with_group_b(case):
            by_b.append(f"- {case.label} {uid}: " + ", ".join(f"{s.tag}({s.phrase})" for s in sigs))
        for uid, nid, sigs in reversal_after_closing(case, span):
            after.append(f"- {case.label} {uid} -> {nid}: " + ", ".join(f"{s.tag}({s.phrase})" for s in sigs))
    lines = [f"Câu chốt thật (decision confirmed, bằng chứng đầu): {n_closings}"]
    lines += [f"Câu chốt thật mang nhóm B (mục tiêu 0): {len(by_b)}"] + by_b
    lines += [f"Câu chốt thật có câu đảo ý trong {span} câu sau (mục tiêu 0): {len(after)}"] + after
    return lines


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(build_report(load_cases()))


if __name__ == "__main__":
    main()
