"""Read .txt / .vtt transcripts into a list of Utterance."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import MeetingMeta, Utterance

TXT_LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^:]+):\s*(.+)$")
VTT_TIMING_RE = re.compile(r"^(\d{1,2}:)?(\d{2}):(\d{2})[.,]\d{1,3}\s*-->")
VTT_VOICE_RE = re.compile(r"^<v(?:\.[^\s>]+)*\s+([^>]+)>(.*?)(?:</v>)?$")
VTT_PREFIX_RE = re.compile(r"^([^:]{1,60}):\s*(.+)$")
TAG_RE = re.compile(r"<[^>]+>")
SPEAKER_N_RE = re.compile(r"^speaker(?:\s*\d+|\s+[a-z])$", re.IGNORECASE)
ROLE_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def make_id(index: int) -> str:
    return f"u{index:03d}"


def base_speaker_name(speaker: str) -> str:
    """'Hùng (PM)' -> 'Hùng'."""
    return ROLE_SUFFIX_RE.sub("", speaker).strip()


def is_anonymous_speaker(speaker: str) -> bool:
    """True for diarization labels such as 'Speaker 1' or 'Speaker A'."""
    return bool(SPEAKER_N_RE.match(base_speaker_name(speaker)))


def parse_txt(text: str) -> tuple[list[Utterance], list[str]]:
    utterances: list[Utterance] = []
    warnings: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip().lstrip("﻿")
        if not line:
            continue
        match = TXT_LINE_RE.match(line)
        if not match:
            warnings.append(f"Bỏ qua dòng {lineno} không đúng định dạng: {line[:80]}")
            continue
        time, speaker, content = match.groups()
        utterances.append(
            Utterance(
                id=make_id(len(utterances) + 1),
                time=time,
                speaker=speaker.strip(),
                text=content.strip(),
            )
        )
    return utterances, warnings


def _vtt_time(match: re.Match[str]) -> str:
    hours, minutes, seconds = match.group(1), match.group(2), match.group(3)
    h = int(hours[:-1]) if hours else 0
    return f"{h}:{minutes}:{seconds}" if h else f"{minutes}:{seconds}"


def parse_vtt(text: str) -> tuple[list[Utterance], list[str]]:
    utterances: list[Utterance] = []
    warnings: list[str] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").lstrip("﻿"))
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]
        if not lines or lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        timing_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if timing_idx is None:
            warnings.append(f"Bỏ qua khối VTT không có mốc thời gian: {lines[0][:80]}")
            continue
        timing = VTT_TIMING_RE.match(lines[timing_idx])
        if not timing:
            warnings.append(f"Mốc thời gian VTT không hợp lệ: {lines[timing_idx][:80]}")
            continue
        body = " ".join(lines[timing_idx + 1 :]).strip()
        speaker, content = _split_vtt_speaker(body)
        if not content:
            continue
        if speaker is None:
            warnings.append(f"Không xác định được người nói tại {_vtt_time(timing)}")
            speaker = "Không rõ"
        utterances.append(
            Utterance(
                id=make_id(len(utterances) + 1),
                time=_vtt_time(timing),
                speaker=speaker,
                text=content,
            )
        )
    return utterances, warnings


def _split_vtt_speaker(body: str) -> tuple[str | None, str]:
    voice = VTT_VOICE_RE.match(body)
    if voice:
        return voice.group(1).strip(), TAG_RE.sub("", voice.group(2)).strip()
    plain = TAG_RE.sub("", body).strip()
    prefix = VTT_PREFIX_RE.match(plain)
    if prefix:
        return prefix.group(1).strip(), prefix.group(2).strip()
    return None, plain


def parse_text(text: str, suffix: str = ".txt") -> tuple[list[Utterance], list[str]]:
    if suffix.lower() == ".vtt" or text.lstrip("﻿").startswith("WEBVTT"):
        return parse_vtt(text)
    return parse_txt(text)


def parse_file(path: str | Path) -> tuple[list[Utterance], list[str]]:
    p = Path(path)
    return parse_text(p.read_text(encoding="utf-8-sig"), p.suffix)


def load_meta(path: str | Path | None) -> MeetingMeta | None:
    if path is None:
        return None
    return MeetingMeta.model_validate(json.loads(Path(path).read_text(encoding="utf-8-sig")))
