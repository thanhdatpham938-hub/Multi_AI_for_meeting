"""Audio input (phase 3B): all with faked API responses, no real calls."""

from types import SimpleNamespace

import pytest

from meeting_extractor import audio
from meeting_extractor.audio import (
    MAX_AUDIO_BYTES, build_speaker_map, clip_range, format_time, save_audio, segments_to_utterances, speaker_label, transcribe,
)
from meeting_extractor.cli import main
from meeting_extractor.config import Settings, load_settings
from meeting_extractor.llm import FakeLLM, LLMError
from meeting_extractor.models import Utterance
from meeting_extractor.parsing import is_anonymous_speaker
from meeting_extractor.pipeline import run, run_audio


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(anthropic_api_key=None, model_light="light", model_strong="strong",
                    temperature=None, runs_dir=tmp_path / "runs", openai_api_key="sk-test")


class FakeTranscriptions:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(response=None, error: Exception | None = None):
    transcriptions = FakeTranscriptions(response, error)
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions)), transcriptions


def seg(speaker, start, end, text):
    return SimpleNamespace(speaker=speaker, start=start, end=end, text=text, id="x", type="transcript.text.segment")


def make_audio(tmp_path, name="meeting.mp3", size=100):
    path = tmp_path / name
    path.write_bytes(b"\0" * size)
    return path


# ---- time / speaker conversion

@pytest.mark.parametrize("sec,expected", [
    (0, "00:00"), (5.9, "00:05"), (65, "01:05"), (3599.9, "59:59"), (3600, "1:00:00"), (3725, "1:02:05"), (-3, "00:00"),
])
def test_format_time(sec, expected):
    assert format_time(sec) == expected


@pytest.mark.parametrize("raw,expected", [
    ("A", "Speaker A"), ("b", "Speaker B"), ("Speaker C", "Speaker C"), ("1", "Speaker 1"),
    ("speaker_0", "Speaker 0"), ("SPEAKER-2", "Speaker 2"), ("spk 3", "Speaker 3"),
    ("AA", "Speaker 1"), ("", "Speaker 1"), (None, "Speaker 1"), ("  ", "Speaker 1"),
])
def test_speaker_label(raw, expected):
    result = speaker_label(raw)
    assert result == expected
    assert is_anonymous_speaker(result)


def test_speaker_map_is_deterministic_and_avoids_collisions():
    raws = ["AA", "B", "", "AA", "speaker_1", "BB", None]
    mapping = build_speaker_map(raws)
    assert mapping["B"] == "Speaker B" and mapping["speaker_1"] == "Speaker 1"
    # fallbacks numbered by first appearance, skipping the already-used "Speaker 1"
    assert mapping["AA"] == "Speaker 2" and mapping[""] == "Speaker 3" and mapping["BB"] == "Speaker 4"
    assert all(is_anonymous_speaker(v) for v in mapping.values())
    assert len(set(mapping.values())) == len(mapping)


def test_segments_with_odd_labels_all_anonymous_and_consistent():
    resp = {"segments": [{"speaker": s, "start": i, "end": i + 1, "text": f"t{i}"}
                         for i, s in enumerate(["speaker_0", "AA", "SPEAKER-2", "AA", "", "a"])]}
    utts, _ = segments_to_utterances(resp)
    assert all(is_anonymous_speaker(u.speaker) for u in utts)
    assert utts[1].speaker == utts[3].speaker and utts[1].speaker != utts[4].speaker


def test_anonymous_speaker_letters_and_digits():
    for name in ("Speaker 1", "Speaker A", "speaker b", "Speaker 12", "Speaker A (PM)"):
        assert is_anonymous_speaker(name), name
    for name in ("Hùng", "Speaker Anh", "Speakers", "Speaker AB", "Speaker"):
        assert not is_anonymous_speaker(name), name


# ---- response conversion

def test_segments_convert_keep_same_speaker_runs_separate():
    resp = SimpleNamespace(segments=[
        seg("A", 0.0, 4.2, " Chào mọi người. "), seg("A", 4.5, 9.0, "Bắt đầu nhé."), seg("B", 3725.0, 3730.5, "Dạ."),
    ])
    utts, warns = segments_to_utterances(resp)
    assert [u.id for u in utts] == ["u001", "u002", "u003"]
    assert [u.speaker for u in utts] == ["Speaker A", "Speaker A", "Speaker B"]
    assert [u.time for u in utts] == ["00:00", "00:04", "1:02:05"]
    assert utts[0].text == "Chào mọi người."
    assert (utts[1].start_sec, utts[1].end_sec) == (4.5, 9.0)
    assert warns == []


def test_segments_accept_plain_dicts():
    utts, _ = segments_to_utterances({"segments": [{"speaker": "A", "start": 1, "end": 2, "text": "Xin chào"}]})
    assert utts[0].speaker == "Speaker A"


@pytest.mark.parametrize("resp", [SimpleNamespace(), SimpleNamespace(segments=None), {"segments": []}, {}])
def test_empty_or_missing_segments_raise_clear_error(resp):
    with pytest.raises(LLMError, match="segments"):
        segments_to_utterances(resp)


def test_malformed_segments_warn_instead_of_crash():
    resp = {"segments": [
        {"speaker": "A", "start": 10, "end": 12, "text": "Một"},
        {"speaker": "B", "start": 12, "end": 13, "text": "   "},           # empty text -> skipped
        {"speaker": None, "start": None, "end": None, "text": "Hai"},       # no speaker, no times
        {"speaker": "A", "start": "abc", "end": 5, "text": "Ba"},           # bad number, end < start
    ]}
    utts, warns = segments_to_utterances(resp)
    assert [u.text for u in utts] == ["Một", "Hai", "Ba"]
    assert utts[1].speaker == "Speaker 1" and utts[1].start_sec == 12.0
    assert utts[2].end_sec == utts[2].start_sec
    assert len(warns) >= 3


def test_only_empty_segments_raise():
    with pytest.raises(LLMError):
        segments_to_utterances({"segments": [{"speaker": "A", "start": 0, "end": 1, "text": ""}]})


# ---- transcribe(): size guard, API parameters, errors

def test_file_over_limit_rejected_before_api_call(tmp_path, settings):
    big = tmp_path / "big.mp3"
    with big.open("wb") as fh:
        fh.truncate(MAX_AUDIO_BYTES + 1)
    client, calls = fake_client({"segments": []})
    with pytest.raises(ValueError, match=r"quá lớn.*25 MB.*mp3"):
        transcribe(big, settings, client=client)
    assert calls.calls == []


def test_missing_file_and_bad_extension(tmp_path, settings):
    client, calls = fake_client()
    with pytest.raises(FileNotFoundError):
        transcribe(tmp_path / "nope.mp3", settings, client=client)
    with pytest.raises(ValueError, match="chưa được hỗ trợ"):
        transcribe(make_audio(tmp_path, "a.ogg"), settings, client=client)
    assert calls.calls == []


def test_transcribe_passes_expected_api_parameters(tmp_path, settings):
    client, calls = fake_client({"segments": [{"speaker": "A", "start": 0, "end": 1, "text": "Alo"}]})
    utts = transcribe(make_audio(tmp_path), settings, client=client)
    assert len(utts) == 1
    kw = calls.calls[0]
    assert kw["model"] == "gpt-4o-transcribe-diarize"
    assert kw["response_format"] == "diarized_json" and kw["chunking_strategy"] == "auto"
    assert not ({"prompt", "timestamp_granularities"} & set(kw))


def test_api_error_becomes_llm_error(tmp_path, settings):
    client, _ = fake_client(error=RuntimeError("boom"))
    with pytest.raises(LLMError, match="boom"):
        transcribe(make_audio(tmp_path), settings, client=client)


def test_missing_openai_key_gives_vietnamese_error(tmp_path):
    no_key = Settings(anthropic_api_key=None, model_light="l", model_strong="s", temperature=None,
                      runs_dir=tmp_path, openai_api_key=None)
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        transcribe(make_audio(tmp_path), no_key)


def test_real_sdk_signature_accepts_our_parameters():
    import inspect

    import openai

    params = inspect.signature(openai.OpenAI(api_key="x").audio.transcriptions.create).parameters
    assert {"model", "file", "response_format", "chunking_strategy"} <= set(params)


def test_transcribe_model_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSCRIBE_MODEL", "other-model  # comment")
    assert load_settings(tmp_path / "none.env").transcribe_model == "other-model"
    monkeypatch.delenv("TRANSCRIBE_MODEL")
    assert load_settings(tmp_path / "none.env").transcribe_model == "gpt-4o-transcribe-diarize"


# ---- save_audio / clip_range

def test_save_audio_copies_into_run_dir(tmp_path):
    src = make_audio(tmp_path, "Meet.MP3", size=10)
    dest = save_audio(src, tmp_path / "runs" / "r1")
    assert dest.name == "audio.mp3" and dest.read_bytes() == src.read_bytes()


def test_clip_range():
    u = Utterance(id="u001", time="00:10", speaker="Speaker A", text="x", start_sec=10.0, end_sec=14.0)
    assert clip_range(u) == (2.0, 22.0)
    assert clip_range(u, pad=0) == (10.0, 14.0)
    early = u.model_copy(update={"start_sec": 3.0})
    assert clip_range(early) == (0.0, 22.0)
    no_end = u.model_copy(update={"end_sec": None})
    assert clip_range(no_end) == (2.0, 18.0)
    with pytest.raises(ValueError):
        clip_range(u.model_copy(update={"start_sec": None}))


# ---- pipeline

RESPONSE = {"segments": [
    {"speaker": "A", "start": 0, "end": 4, "text": "Hôm nay mình báo cáo tiến độ."},
    {"speaker": "B", "start": 4.5, "end": 9, "text": "Em đã xong wireframe đăng nhập."},
]}


def audio_llm() -> FakeLLM:
    return FakeLLM({
        "segment": {"topics": [{"topic_id": "t01", "title": "Tiến độ", "utterance_ids": ["u001", "u002"]}]},
        "extract": {"candidates": [
            {"type": "knowledge", "topic_id": "t01", "content": "Xong wireframe", "speaker": "Speaker B",
             "evidence": ["u002"]}]},
        "track": {"items": [{"type": "knowledge", "content": "Xong wireframe đăng nhập", "evidence": ["u002"],
                             "confidence": 0.9}]},
        "verify": {"passed": True, "reason": "ok"},
    })


def test_run_audio_saves_audio_and_sets_audio_path(tmp_path, settings):
    src = make_audio(tmp_path)
    client, _ = fake_client(RESPONSE)
    result = run_audio(src, llm=audio_llm(), settings=settings, transcribe_client=client)
    run_dir = settings.runs_dir / result.run_id
    assert result.audio_path == "audio.mp3" and (run_dir / "audio.mp3").exists()
    assert (run_dir / "result.json").exists()
    assert result.utterances[1].speaker == "Speaker B" and result.utterances[1].start_sec == 4.5
    assert result.run_id.endswith("_meeting")


def test_run_dispatches_audio_by_extension(tmp_path, settings, monkeypatch):
    client, _ = fake_client(RESPONSE)
    monkeypatch.setattr(audio, "make_openai_client", lambda _s: client)
    result = run(make_audio(tmp_path, "call.m4a"), llm=audio_llm(), settings=settings)
    assert result.audio_path == "audio.m4a"


def test_run_audio_save_false_writes_nothing(tmp_path, settings):
    client, _ = fake_client(RESPONSE)
    result = run_audio(make_audio(tmp_path), llm=audio_llm(), settings=settings, save=False,
                       transcribe_client=client)
    assert result.audio_path is None and not settings.runs_dir.exists()


def test_run_audio_oversize_fails_before_creating_run(tmp_path, settings):
    big = tmp_path / "big.wav"
    with big.open("wb") as fh:
        fh.truncate(MAX_AUDIO_BYTES + 1)
    with pytest.raises(ValueError):
        run_audio(big, llm=audio_llm(), settings=settings)
    assert not settings.runs_dir.exists()


def test_cli_audio_flag_reports_error_cleanly(tmp_path, capsys):
    code = main(["run", str(tmp_path / "missing.mp3"), "--audio"])
    assert code == 1 and "Lỗi" in capsys.readouterr().err
