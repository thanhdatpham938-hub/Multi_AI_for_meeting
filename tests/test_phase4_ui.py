"""Phase 4: confidence breakdown, audio upload/playback and the Q&A tab in the Streamlit app (offline)."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from meeting_extractor.config import Settings
from meeting_extractor.llm import LLMError
from meeting_extractor.models import RunResult
from meeting_extractor.parsing import load_meta
from meeting_extractor.pipeline import run
from meeting_extractor.qa import QAAnswer
from tests.test_pipeline_offline import FIXTURES, tc1_llm

APP = str(Path(__file__).resolve().parents[1] / "app" / "review_app.py")
BREAKDOWN = {"base": 0.5, "closing_explicit": 0.2, "closer_can_decide": 0.15, "noisy_evidence": -0.15,
             "cap_authority": -0.08}


def _make_run(tmp_path: Path, monkeypatch, name: str = "runs") -> Path:
    runs = tmp_path / name
    monkeypatch.setenv("RUNS_DIR", str(runs))
    settings = Settings(anthropic_api_key=None, model_light="l", model_strong="s", temperature=None, runs_dir=runs)
    result = run(FIXTURES / "tc1.txt", load_meta(FIXTURES / "tc1.meta.json"), llm=tc1_llm(), settings=settings)
    return runs / result.run_id


def _patch_result(run_dir: Path, mutate) -> None:
    path = run_dir / "result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def run_dir(tmp_path, monkeypatch) -> Path:
    return _make_run(tmp_path, monkeypatch)


def _open_run(run_dir: Path) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["page"] = "run"
    at.session_state["run_dir"] = str(run_dir)
    return at.run()


def _open_detail(at: AppTest, item_id: str = "d01") -> AppTest:
    next(b for b in at.button if b.key == f"open-ov-decision-{item_id}").click()
    return at.run()


def _text(at: AppTest) -> str:
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def _first_decision(run_dir: Path) -> dict:
    return next(i for i in json.loads((run_dir / "result.json").read_text(encoding="utf-8"))["items"]
                if i["item_id"] == "d01")


# ---------------------------------------------------------------- job 1: confidence breakdown


def test_breakdown_shown_with_vietnamese_labels_and_colors(run_dir):
    def mutate(d):
        d["items"][0]["confidence_breakdown"] = BREAKDOWN
        d["items"][0]["confidence"] = 0.62
    _patch_result(run_dir, mutate)
    at = _open_detail(_open_run(run_dir))
    assert not at.exception
    md = _text(at)
    assert "0,62" in md and "+0,20" in md and "câu chốt rõ" in md
    assert "người chốt có quyền" in md and "−0,15" in md and "ghi âm không rõ" in md
    assert "Giới hạn áp dụng: trần: chưa rõ thẩm quyền" in md
    assert "#1e7b3c" in md and "#b42318" in md  # green for plus, red for minus
    assert "0.62" not in md  # decimal comma only


def test_old_run_without_breakdown_does_not_fail(run_dir):
    _patch_result(run_dir, lambda d: d["items"][0].pop("confidence_breakdown", None))
    at = _open_detail(_open_run(run_dir))
    assert not at.exception
    assert "chưa có phân tích chi tiết" in _text(at)


def test_unknown_breakdown_key_is_shown_raw(run_dir):
    _patch_result(run_dir, lambda d: d["items"][0].update(confidence_breakdown={"base": 0.5, "mystery": 0.1}))
    at = _open_detail(_open_run(run_dir))
    assert not at.exception and "mystery" in _text(at)


# ---------------------------------------------------------------- job 2: audio


def _with_audio(run_dir: Path, *, flag: bool, confidence: float = 0.9, write_file: bool = True) -> None:
    def mutate(d):
        d["audio_path"] = "audio.mp3"
        for u in d["utterances"]:
            u["start_sec"] = 60.0 + 10 * int(u["id"][1:])
            u["end_sec"] = u["start_sec"] + 5
        d["items"][0]["flags"] = ["number_check"] if flag else []
        d["items"][0]["confidence"] = confidence
    _patch_result(run_dir, mutate)
    if write_file:
        (run_dir / "audio.mp3").write_bytes(b"ID3fake")


def _audio_count(at: AppTest) -> int:
    return len(at.get("audio"))


def test_player_shown_for_flagged_item_with_audio(run_dir):
    _with_audio(run_dir, flag=True)
    at = _open_detail(_open_run(run_dir))
    assert not at.exception
    assert _audio_count(at) == 1
    first_ev = _first_decision(run_dir)["evidence"][0]
    start = 60 + 10 * int(first_ev[1:]) - 8
    assert f"Đang phát từ {start // 60:02d}:{start % 60:02d}" in _text(at)


def test_player_shown_for_low_confidence_without_flag(run_dir):
    _with_audio(run_dir, flag=False, confidence=0.5)
    assert _audio_count(_open_detail(_open_run(run_dir))) == 1


def test_player_hidden_when_item_is_confident_and_unflagged(run_dir):
    _with_audio(run_dir, flag=False, confidence=0.9)
    assert _audio_count(_open_detail(_open_run(run_dir))) == 0


def test_player_hidden_without_audio(run_dir):
    def mutate(d):
        d["items"][0]["flags"] = ["number_check"]
    _patch_result(run_dir, mutate)
    at = _open_detail(_open_run(run_dir))
    assert not at.exception and _audio_count(at) == 0


def test_missing_audio_file_shows_note_not_error(run_dir):
    _with_audio(run_dir, flag=True, write_file=False)
    at = _open_detail(_open_run(run_dir))
    assert not at.exception and _audio_count(at) == 0
    assert "không thể phát lại" in _text(at)


def test_audio_path_cannot_escape_run_folder(run_dir, tmp_path):
    _with_audio(run_dir, flag=True, write_file=False)
    _patch_result(run_dir, lambda d: d.update(audio_path="../../secret.mp3"))
    (tmp_path / "secret.mp3").write_bytes(b"x")
    at = _open_detail(_open_run(run_dir))
    assert not at.exception and _audio_count(at) == 0


def _audio_uploader(at: AppTest):
    return next(u for u in at.file_uploader if ".mp3" in [t.lower() for t in u.allowed_type] or "mp3" in u.allowed_type)


def _analyze_button(at: AppTest):
    return next(b for b in at.button if "Phân tích" in b.label)


def test_uploader_accepts_audio_and_text_types(run_dir):
    at = AppTest.from_file(APP, default_timeout=30).run()
    types = {t.lstrip(".").lower() for t in _audio_uploader(at).allowed_type}
    assert {"mp3", "m4a", "wav", "mp4", "txt", "vtt"} <= types


def test_audio_upload_calls_run_audio_with_safe_temp_file(run_dir, monkeypatch):
    calls: dict = {}
    result = RunResult.model_validate_json((run_dir / "result.json").read_text(encoding="utf-8"))

    def fake_run_audio(path, meta=None, **kwargs):
        calls["name"] = Path(path).name
        calls["size"] = Path(path).stat().st_size
        calls["has_progress"] = callable(kwargs.get("progress"))
        return result

    monkeypatch.setattr("meeting_extractor.pipeline.run_audio", fake_run_audio)
    at = AppTest.from_file(APP, default_timeout=30).run()
    _audio_uploader(at).upload("cuộc họp (1).mp3", b"ID3" + b"0" * 100, "audio/mpeg")
    at.run()
    assert not at.exception and not at.error
    btn = _analyze_button(at)
    assert not btn.disabled
    btn.click()
    at.run()
    assert not at.exception
    assert calls == {"name": "cu_c_h_p_1.mp3", "size": 103, "has_progress": True}
    assert at.session_state["page"] == "run"


def test_audio_over_limit_errors_before_any_api_call(run_dir, monkeypatch):
    monkeypatch.setattr("meeting_extractor.audio.MAX_AUDIO_BYTES", 50)
    called = []
    monkeypatch.setattr("meeting_extractor.pipeline.run_audio", lambda *a, **k: called.append(1))
    at = AppTest.from_file(APP, default_timeout=30).run()
    _audio_uploader(at).upload("big.wav", b"0" * 200, "audio/wav")
    at.run()
    assert not at.exception
    assert any("quá lớn" in e.value for e in at.error)
    assert _analyze_button(at).disabled and not called


def test_audio_run_error_is_shown_not_raised(run_dir, monkeypatch):
    def boom(*a, **k):
        raise LLMError("hết hạn mức")

    monkeypatch.setattr("meeting_extractor.pipeline.run_audio", boom)
    at = AppTest.from_file(APP, default_timeout=30).run()
    _audio_uploader(at).upload("a.mp3", b"ID3" + b"0" * 10, "audio/mpeg")
    at.run()
    _analyze_button(at).click()
    at.run()
    assert not at.exception and any("hết hạn mức" in e.value for e in at.error)


# ---------------------------------------------------------------- job 3: Q&A tab


def _tab_labels(at: AppTest) -> list[str]:
    return [t.label for t in at.tabs]


def _ask(at: AppTest, question: str) -> AppTest:
    at.text_area[0].set_value(question)
    next(b for b in at.button if b.label == "Gửi câu hỏi").click()
    return at.run()


@pytest.fixture
def fake_qa(monkeypatch):
    """Mock qa.answer + make_llm; records (question, result) for every call."""
    seen: list[tuple[str, RunResult]] = []
    reply: dict = {"answer": QAAnswer(text="Chốt dùng AWS.", evidence=["u019"]), "raise": None}

    def fake_answer(question, run_result, llm, settings):
        seen.append((question, run_result))
        if reply["raise"]:
            raise reply["raise"]
        return reply["answer"]

    monkeypatch.setattr("meeting_extractor.qa.answer", fake_answer)
    monkeypatch.setattr("meeting_extractor.llm.make_llm", lambda settings: object())
    monkeypatch.setattr("meeting_extractor.qa.make_llm", lambda settings: object(), raising=False)
    return seen, reply


def test_qa_tab_exists_after_existing_tabs(run_dir):
    at = _open_run(run_dir)
    labels = _tab_labels(at)
    assert labels[-1] == "Hỏi đáp" and labels[0] == "Tổng quan" and "Quyết định" in labels
    assert "~$0,01–0,02" in _text(at)


def test_qa_answer_with_evidence_text(run_dir, fake_qa):
    seen, _ = fake_qa
    at = _ask(_open_run(run_dir), "Chốt hạ tầng gì?")
    assert not at.exception
    md = _text(at)
    assert "Chốt dùng AWS." in md and "u019" in md and "Chốt hạ tầng gì?" in md
    u019 = next(u for u in seen[0][1].utterances if u.id == "u019")
    assert u019.time in md and u019.text in md
    assert not at.warning


def test_qa_receives_review_applied_result(run_dir, fake_qa):
    seen, _ = fake_qa
    at = _open_run(run_dir)
    next(b for b in at.button if b.label == "✔ Duyệt nhanh").click()
    at.run()
    _ask(at, "hỏi")
    assert any(i.review == "accepted" for i in seen[0][1].items)


def test_qa_out_of_scope_neutral_message(run_dir, fake_qa):
    _, reply = fake_qa
    reply["answer"] = QAAnswer(text="Không có trong cuộc họp này.", out_of_scope=True)
    at = _ask(_open_run(run_dir), "Thủ đô nước Pháp?")
    assert not at.exception and any("Không có trong cuộc họp này." in i.value for i in at.info)
    assert "Trả lời:" not in _text(at)


def test_qa_warning_shown_as_warning(run_dir, fake_qa):
    _, reply = fake_qa
    reply["answer"] = QAAnswer(text="x", evidence=["u019"], warning="Kết quả có thể thiếu thông tin.")
    at = _ask(_open_run(run_dir), "hỏi")
    assert any("có thể thiếu thông tin" in w.value for w in at.warning)


def test_qa_llm_error_shows_message_not_crash(run_dir, fake_qa):
    _, reply = fake_qa
    reply["raise"] = LLMError("Thiếu OPENAI_API_KEY")
    at = _ask(_open_run(run_dir), "hỏi")
    assert not at.exception
    assert any("Thiếu OPENAI_API_KEY" in e.value for e in at.error)


def test_qa_blank_question_is_ignored(run_dir, fake_qa):
    seen, _ = fake_qa
    at = _ask(_open_run(run_dir), "   ")
    assert not at.exception and seen == []


def test_qa_history_separated_per_run(tmp_path, monkeypatch, fake_qa):
    first = _make_run(tmp_path, monkeypatch)
    second = first.parent / "second-run"
    import shutil
    shutil.copytree(first, second)
    at = _ask(_open_run(first), "câu hỏi của họp một")
    assert "câu hỏi của họp một" in _text(at)
    at.session_state["run_dir"] = str(second)
    at.run()
    assert "câu hỏi của họp một" not in _text(at)
    at.session_state["run_dir"] = str(first)
    at.run()
    assert "câu hỏi của họp một" in _text(at)
