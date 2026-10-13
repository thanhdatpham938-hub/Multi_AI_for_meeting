"""Configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
RUNS_DIR = PROJECT_ROOT / "runs"

DEFAULT_MODEL_LIGHT = "claude-haiku-5-5"
DEFAULT_MODEL_STRONG = "claude-sonnet-5-5"


def _strip_inline_comment(value: str | None) -> str | None:
    if value is None:
        return None
    return value.split("#", 1)[0].strip() or None


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    model_light: str
    model_strong: str
    temperature: float | None
    runs_dir: Path = RUNS_DIR


def load_settings(env_file: Path | None = None) -> Settings:
    """Read settings from .env (if present) and the process environment."""
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
    temp_raw = _strip_inline_comment(os.getenv("LLM_TEMPERATURE"))
    return Settings(
        anthropic_api_key=_strip_inline_comment(os.getenv("ANTHROPIC_API_KEY")),
        model_light=_strip_inline_comment(os.getenv("MODEL_LIGHT")) or DEFAULT_MODEL_LIGHT,
        model_strong=_strip_inline_comment(os.getenv("MODEL_STRONG")) or DEFAULT_MODEL_STRONG,
        temperature=float(temp_raw) if temp_raw is not None else None,
        runs_dir=Path(_strip_inline_comment(os.getenv("RUNS_DIR")) or RUNS_DIR),
    )
