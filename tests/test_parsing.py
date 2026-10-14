import json
from pathlib import Path

import pytest

from meeting_extractor.parsing import (
    base_speaker_name,
    is_anonymous_speaker,
    load_meta,
    parse_file,
    parse_txt,
    parse_vtt,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_txt_basic_line():
    utts, warnings = parse_txt("[41:05] Hùng (PM): OK, vậy mình chốt dùng AWS nhé.")
    assert warnings == []
    assert len(utts) == 1
    u = utts[0]
    assert (u.id, u.time, u.speaker, u.text) == ("u001", "41:05", "Hùng (PM)", "OK, vậy mình chốt dùng AWS nhé.")


def test_parse_txt_skips_bad_lines_with_warning():
    text = "[00:01] A: xin chào\n(mọi người cười)\n\n[1:02:03] B: tạm biệt"
    utts, warnings = parse_txt(text)
    assert [u.id for u in utts] == ["u001", "u002"]
    assert utts[1].time == "1:02:03"
    assert len(warnings) == 1 and "mọi người cười" in warnings[0]


def test_parse_txt_keeps_colon_inside_text():
    utts, _ = parse_txt("[10:00] Lan: Lưu ý: hạn là 15/11.")
    assert utts[0].speaker == "Lan"
    assert utts[0].text == "Lưu ý: hạn là 15/11."


def test_parse_vtt_voice_and_prefix():
    utts, warnings = parse_file(FIXTURES / "tc_sample.vtt")
    assert warnings == []
    assert [(u.time, u.speaker) for u in utts] == [
        ("05:12", "Nam"),
        ("41:05", "Hùng (PM)"),
        ("1:02:03", "Lan"),
    ]
    assert utts[2].text == "Dạ vâng."


def test_parse_vtt_missing_speaker_warns():
    utts, warnings = parse_vtt("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nkhông có tên\n")
    assert utts[0].speaker == "Không rõ"
    assert warnings


@pytest.mark.parametrize("n", range(1, 8))
def test_fixtures_parse_and_answers_reference_real_ids(n: int):
    utts, _ = parse_file(FIXTURES / f"tc{n}.txt")
    assert 15 <= len(utts) <= 40
    ids = {u.id for u in utts}
    expected = json.loads((FIXTURES / f"tc{n}.expected.json").read_text(encoding="utf-8"))
    for item in expected["items"]:
        assert set(item["evidence"]) <= ids


def test_core_lines_preserved():
    utts, _ = parse_file(FIXTURES / "tc1.txt")
    by_id = {u.id: u for u in utts}
    assert by_id["u019"].text == "OK, vậy mình chốt dùng AWS nhé."
    assert by_id["u019"].time == "41:05"


def test_tc3_has_ten_lines_between_return():
    utts, _ = parse_file(FIXTURES / "tc3.txt")
    times = [u.time for u in utts]
    assert times.index("39:15") - times.index("08:30") - 1 >= 10


def test_tc7_note_line_is_skipped():
    _, warnings = parse_file(FIXTURES / "tc7.txt")
    assert any("gật đầu" in w for w in warnings)


def test_speaker_helpers():
    assert base_speaker_name("Hùng (PM)") == "Hùng"
    assert is_anonymous_speaker("Speaker 2")
    assert not is_anonymous_speaker("Hùng (PM)")


def test_load_meta():
    meta = load_meta(FIXTURES / "tc1.meta.json")
    assert meta is not None
    assert meta.participants[0].can_decide is True
    assert load_meta(None) is None


LONG_CASES = Path(__file__).resolve().parents[1] / "test_cases_3_muc_do (1)"


@pytest.mark.parametrize("case_dir", sorted(p for p in LONG_CASES.glob("case*") if p.is_dir()), ids=lambda p: p.name)
def test_long_cases_have_100_lines_and_continuous_time(case_dir: Path):
    utts, warnings = parse_file(case_dir / "transcript.txt")
    assert len(utts) >= 100
    secs = [sum(int(x) * 60 ** i for i, x in enumerate(reversed(u.time.split(":")))) for u in utts]
    gaps = [b - a for a, b in zip(secs, secs[1:])]
    assert all(0 < g <= 30 for g in gaps), "thời gian phải tăng dần và không ngắt quãng quá 30 giây"
    assert load_meta(case_dir / "meeting_meta.json") is not None
    assert (case_dir / "expected_result.md").exists()
