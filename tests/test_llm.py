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



# ---------------------------------------------------------------- OpenAI client (mocked, no network)

from types import SimpleNamespace  # noqa: E402

from meeting_extractor.config import Settings, load_settings  # noqa: E402
from meeting_extractor.llm import AnthropicLLM, OpenAILLM, make_llm  # noqa: E402


def _openai_settings(**kw) -> Settings:
    base = dict(anthropic_api_key=None, model_light="gpt-4.1-mini", model_strong="gpt-4.1",
                temperature=0.0, provider="openai", openai_api_key="test-key")
    base.update(kw)
    return Settings(**base)


class _FakeCompletions:
    def __init__(self, content: str):
        self.content = content
        self.kwargs: list[dict] = []

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        message = SimpleNamespace(content=self.content, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30))


def _mocked_openai(content: str, **kw) -> tuple[OpenAILLM, _FakeCompletions]:
    llm = OpenAILLM(_openai_settings(**kw))
    fake = _FakeCompletions(content)
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return llm, fake


def test_openai_json_mode_and_usage():
    llm, fake = _mocked_openai('{"passed": true, "reason": "ok"}')
    out = llm.complete_json(model="gpt-4.1", system="sys JSON", user="u", schema=VerifyOutput, purpose="verify")
    assert out.passed
    sent = fake.kwargs[0]
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["messages"][0] == {"role": "system", "content": "sys JSON"}
    assert sent["temperature"] == 0.0 and sent["seed"] == 0
    assert llm.usage.input_tokens == 120 and llm.usage.output_tokens == 30
    assert llm.usage.cost_usd() > 0


def test_openai_reasoning_models_skip_temperature():
    llm, fake = _mocked_openai('{"passed": false, "reason": "x"}')
    llm.complete_json(model="o4-mini", system="s", user="u", schema=VerifyOutput)
    llm.complete_json(model="gpt-5-mini", system="s", user="u", schema=VerifyOutput)
    assert all("temperature" not in k and "seed" not in k for k in fake.kwargs)


def test_openai_refusal_raises():
    llm, fake = _mocked_openai("")
    fake.create = lambda **kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, refusal="không"), finish_reason="stop")],
        usage=None)
    with pytest.raises(LLMError, match="từ chối"):
        llm.complete_json(model="gpt-4.1", system="s", user="u", schema=VerifyOutput)


def test_make_llm_dispatch_and_missing_key():
    assert isinstance(make_llm(_openai_settings()), OpenAILLM)
    assert isinstance(make_llm(_openai_settings(provider="anthropic", anthropic_api_key="k")), AnthropicLLM)
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        make_llm(_openai_settings(openai_api_key=None))


def test_load_settings_provider_defaults(tmp_path, monkeypatch):
    for var in ("LLM_PROVIDER", "MODEL_LIGHT", "MODEL_STRONG", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    s = load_settings(empty_env)
    assert (s.provider, s.model_light, s.model_strong) == ("openai", "gpt-4.1-mini", "gpt-4.1")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    s = load_settings(empty_env)
    assert (s.model_light, s.model_strong) == ("claude-haiku-5-5", "claude-sonnet-5-5")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValueError):
        load_settings(empty_env)


def test_openai_base_url_ignores_inline_comment(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=k\nOPENAI_BASE_URL=        # để trống\n", encoding="utf-8")
    s = load_settings(env)
    assert s.openai_base_url is None
    assert str(OpenAILLM(s)._client.base_url).startswith("https://api.openai.com/v1")
