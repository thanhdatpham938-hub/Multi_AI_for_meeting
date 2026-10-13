import pytest

from meeting_extractor.llm import (
    FakeLLM,
    LLMError,
    _NO_SAMPLING_RE,
    extract_json,
)
from meeting_extractor.models import VerifyOutput


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Đây là kết quả: {"a": [1, 2]} xong.') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("không có json")


def test_complete_json_valid_first_try():
    llm = FakeLLM({"verify": {"passed": True, "reason": "ok"}})
    out = llm.complete_json(model="m", system="s", user="u", schema=VerifyOutput, purpose="verify")
    assert out.passed is True
    assert llm.usage.calls == 1


def test_complete_json_retries_with_error_feedback():
    llm = FakeLLM({"verify": ["không phải json", {"passed": "x"}, {"passed": False, "reason": "sai"}]})
    out = llm.complete_json(model="m", system="s", user="u", schema=VerifyOutput, purpose="verify")
    assert out.passed is False
    assert len(llm.calls) == 3
    assert "không hợp lệ" in llm.calls[1][2]


def test_complete_json_gives_up_after_two_retries():
    llm = FakeLLM({"verify": ["x", "y", "z", {"passed": True, "reason": "late"}]})
    with pytest.raises(LLMError, match="3 lần"):
        llm.complete_json(model="m", system="s", user="u", schema=VerifyOutput, purpose="verify")


def test_fake_llm_callable_handler():
    llm = FakeLLM({"verify": lambda system, user: {"passed": "AWS" in user, "reason": "r"}})
    out = llm.complete_json(model="m", system="s", user="chốt AWS", schema=VerifyOutput, purpose="verify")
    assert out.passed


def test_no_sampling_models():
    assert _NO_SAMPLING_RE.search("claude-haiku-5-5")
    assert _NO_SAMPLING_RE.search("claude-sonnet-5")
    assert _NO_SAMPLING_RE.search("claude-opus-4-7")
    assert not _NO_SAMPLING_RE.search("claude-haiku-4-5")
    assert not _NO_SAMPLING_RE.search("claude-sonnet-4-6")

