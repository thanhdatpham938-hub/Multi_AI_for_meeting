"""Smoke tests for the Streamlit review app (offline, FakeLLM-generated run)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from meeting_extractor.config import Settings
from meeting_extractor.export import load_reviews
from meeting_extractor.parsing import load_meta
from meeting_extractor.pipeline import run
from tests.test_pipeline_offline import FIXTURES, tc1_llm

APP = str(Path(__file__).resolve().parents[1] / "app" / "review_app.py")


@pytest.fixture
def run_dir(tmp_path, monkeypatch) -> Path:
    runs = tmp_path / "runs"
    monkeypatch.setenv("RUNS_DIR", str(runs))
    settings = Settings(anthropic_api_key=None, model_light="l", model_strong="s", temperature=None, runs_dir=runs)
    result = run(FIXTURES / "tc1.txt", load_meta(FIXTURES / "tc1.meta.json"), llm=tc1_llm(), settings=settings)
    return runs / result.run_id


def test_home_page_renders_meeting_form(run_dir):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    labels = [t.label for t in at.text_input]
    assert "Tiêu đề cuộc họp" in labels and "Dự án" in labels
    assert any(b.label.startswith("🔍") for b in at.button)


def test_run_page_review_flow(run_dir):
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["page"] = "run"
    at.session_state["run_dir"] = str(run_dir)
    at.run()
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Dùng AWS cho hạ tầng server" in md and "Họp dự án X" in md

    quick = next(b for b in at.button if b.label == "✔ Duyệt nhanh")
    quick.click().run()
    assert not at.exception
    reviews = load_reviews(run_dir)
    assert reviews["items"]["d01"]["review"] == "accepted"
