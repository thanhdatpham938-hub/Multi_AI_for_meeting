"""Formatting helpers shared by agents."""

from __future__ import annotations

from collections.abc import Iterable

from ..models import MeetingMeta, Utterance


def format_utterances(utterances: Iterable[Utterance]) -> str:
    return "\n".join(f"{u.id} [{u.time}] {u.speaker}: {u.text}" for u in utterances)


def format_agenda(meta: MeetingMeta | None) -> str:
    if not meta or not meta.agenda:
        return "(không có)"
    return "\n".join(f"- {a}" for a in meta.agenda)


def format_participants(meta: MeetingMeta | None) -> str:
    if not meta or not meta.participants:
        return "(không có danh sách)"
    lines = []
    for p in meta.participants:
        role = f" ({p.role})" if p.role else ""
        right = "có quyền chốt" if p.can_decide else "không có quyền chốt"
        lines.append(f"- {p.name}{role}: {right}")
    return "\n".join(lines)


def select(utterances: list[Utterance], ids: Iterable[str]) -> list[Utterance]:
    """Utterances whose id is in `ids`, in transcript order."""
    wanted = set(ids)
    return [u for u in utterances if u.id in wanted]
