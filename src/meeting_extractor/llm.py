"""Thin LLM client: JSON-only calls validated by Pydantic, with retry.

`LLMClient` holds the provider-independent logic (JSON extraction, validation,
retry with error feedback, usage accounting). Subclasses implement `_call`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .config import PROMPTS_DIR, Settings

T = TypeVar("T", bound=BaseModel)

MAX_RETRIES = 2
USER_MARKER = "<!-- USER -->"

# USD per 1M tokens (input, output) – used only for the cost estimate.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}

# Models that reject non-default sampling params (temperature) with HTTP 400.
_NO_SAMPLING_RE = re.compile(r"claude-(fable|mythos)|claude-(opus|sonnet|haiku)-5(-\d+)?$|opus-4-[78]")
# Models that accept the server-side refusal fallback `fallbacks: "default"`.
_FALLBACK_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1")


class LLMError(RuntimeError):
    """Raised when the LLM cannot produce valid output after all retries."""


# ---------------------------------------------------------------- prompts


@dataclass(frozen=True)
class Prompt:
    name: str
    system: str
    user_template: str
    version: str  # short content hash

    def render(self, **values: str) -> str:
        text = self.user_template
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", value)
        return text


def load_prompt(name: str) -> Prompt:
    """Load `prompts/<name>.md`. Text above `<!-- USER -->` is the system prompt."""
    raw = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    system, _, user = raw.partition(USER_MARKER)
    if not user:
        raise ValueError(f"Prompt {name}.md thiếu dòng phân tách {USER_MARKER}")
    version = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return Prompt(name=name, system=system.strip(), user_template=user.strip(), version=version)


# ---------------------------------------------------------------- JSON helpers


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in `text`, tolerating ``` fences and prose."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        raise ValueError("Không tìm thấy JSON trong phản hồi")
    start = min(starts)
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if end <= start:
        raise ValueError("JSON không hoàn chỉnh")
    return json.loads(cleaned[start : end + 1])


# ---------------------------------------------------------------- usage


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_model: dict[str, list[int]] = field(default_factory=dict)  # model -> [in, out]

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        slot = self.by_model.setdefault(model, [0, 0])
        slot[0] += input_tokens
        slot[1] += output_tokens

    def cost_usd(self) -> float:
        total = 0.0
        for model, (tin, tout) in self.by_model.items():
            pin, pout = PRICING.get(model, (0.0, 0.0))
            total += tin / 1e6 * pin + tout / 1e6 * pout
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "by_model": self.by_model,
            "cost_usd_estimate": round(self.cost_usd(), 6),
        }


# ---------------------------------------------------------------- clients


class LLMClient:
    """Base client. Subclasses implement `_call(model, system, user) -> (text, in, out)`."""

    def __init__(self) -> None:
        self.usage = Usage()

    def _call(self, model: str, system: str, user: str, purpose: str) -> tuple[str, int, int]:
        raise NotImplementedError

    def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        purpose: str = "generic",
    ) -> T:
        """Call the model, parse JSON and validate against `schema`.

        On invalid output, retry up to MAX_RETRIES times, telling the model what was wrong.
        """
        prompt = user
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            text, tin, tout = self._call(model, system, prompt, purpose)
            self.usage.add(model, tin, tout)
            try:
                return schema.model_validate(extract_json(text))
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)[:1500]
                prompt = (
                    f"{user}\n\n---\nLần trả lời trước (lần {attempt + 1}) không hợp lệ.\n"
                    f"Lỗi: {last_error}\n"
                    f"Phản hồi trước đó:\n{text[:3000]}\n\n"
                    "Hãy trả lời lại CHỈ bằng một đối tượng JSON hợp lệ đúng schema đã yêu cầu."
                )
        raise LLMError(
            f"[{purpose}] LLM không trả JSON hợp lệ sau {MAX_RETRIES + 1} lần thử. Lỗi cuối: {last_error}"
        )


class AnthropicLLM(LLMClient):
    """Claude via the official `anthropic` SDK."""

    def __init__(self, settings: Settings, max_tokens: int = 16000) -> None:
        super().__init__()
        import anthropic

        if not settings.anthropic_api_key:
            raise LLMError("Thiếu ANTHROPIC_API_KEY. Hãy tạo file .env từ .env.example.")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._temperature = settings.temperature
        self._max_tokens = max_tokens

    def _call(self, model: str, system: str, user: str, purpose: str) -> tuple[str, int, int]:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self._temperature is not None and not _NO_SAMPLING_RE.search(model):
            kwargs["temperature"] = self._temperature
        try:
            if model in _FALLBACK_MODELS:
                response = self._client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                response = self._client.messages.create(**kwargs)
        except self._anthropic.AuthenticationError as exc:
            raise LLMError("API key không hợp lệ (401).") from exc
        except self._anthropic.NotFoundError as exc:
            raise LLMError(f"Không tìm thấy model '{model}'. Kiểm tra MODEL_LIGHT/MODEL_STRONG.") from exc
        except self._anthropic.APIStatusError as exc:
            raise LLMError(f"Lỗi API ({exc.status_code}) khi gọi {purpose}: {exc.message}") from exc
        except self._anthropic.APIConnectionError as exc:
            raise LLMError(f"Không kết nối được tới API khi gọi {purpose}.") from exc

        if response.stop_reason == "refusal":
            raise LLMError(f"[{purpose}] Model từ chối xử lý yêu cầu.")
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, response.usage.input_tokens, response.usage.output_tokens


Handler = Callable[[str, str], Any]


class FakeLLM(LLMClient):
    """Offline LLM for tests.

    `handlers` maps a purpose ("segment", "extract", "track", "verify", "merge", "match")
    to either a fixed response (dict / str) or a callable `(system, user) -> dict | str`.
    A list value is consumed one element per call (scripted responses).
    """

    def __init__(self, handlers: dict[str, Any]) -> None:
        super().__init__()
        self.handlers = handlers
        self.calls: list[tuple[str, str, str]] = []  # (purpose, model, user)

    def _call(self, model: str, system: str, user: str, purpose: str) -> tuple[str, int, int]:
        self.calls.append((purpose, model, user))
        if purpose not in self.handlers:
            raise LLMError(f"FakeLLM không có handler cho '{purpose}'")
        handler = self.handlers[purpose]
        if isinstance(handler, list):
            if not handler:
                raise LLMError(f"FakeLLM hết phản hồi kịch bản cho '{purpose}'")
            result = handler.pop(0)
        elif callable(handler):
            result = handler(system, user)
        else:
            result = handler
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        return text, len(user) // 4, len(text) // 4


def make_llm(settings: Settings) -> LLMClient:
    return AnthropicLLM(settings)
