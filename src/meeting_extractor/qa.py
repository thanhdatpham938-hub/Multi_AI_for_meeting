"""Cited question answering within a single meeting (no embeddings, whole transcript in the prompt)."""

from __future__ import annotations

import json

from pydantic import BaseModel

from .agents.common import format_utterances
from .config import Settings
from .llm import LLMClient, load_prompt
from .models import Item, RunResult

APPROVED_REVIEWS = ("accepted", "edited")
OUT_OF_SCOPE_TEXT = "Không có trong cuộc họp này."
MAX_QUESTION_CHARS = 2000


class QAAnswer(BaseModel):
    text: str
    evidence: list[str] = []  # utterance ids; may be empty on refusal
    out_of_scope: bool = False
    warning: str | None = None


class _LLMAnswer(BaseModel):
    """Raw LLM output; the warning is always computed by code, never by the model."""

    text: str
    evidence: list[str] = []
    out_of_scope: bool = False


def approved_items(result: RunResult) -> list[Item]:
    return [it for it in result.items if it.review in APPROVED_REVIEWS]


def _format_items(items: list[Item]) -> str:
    if not items:
        return "(chưa có mục nào được duyệt)"
    views = [
        it.model_dump(
            mode="json",
            include={"type", "content", "status", "condition", "owner", "deadline", "evidence", "topic"},
        )
        for it in items
    ]
    return "\n".join(json.dumps(v, ensure_ascii=False) for v in views)


def _failed_topics_warning(result: RunResult) -> str | None:
    if not result.failed_topics:
        return None
    titles = {t.topic_id: t.title for t in result.topics}
    names = ", ".join(f"{titles[tid]} ({tid})" if tid in titles else tid for tid in result.failed_topics)
    return f"Kết quả có thể thiếu thông tin về các chủ đề xử lý lỗi: {names}."


def _join(warnings: list[str]) -> str | None:
    return " ".join(warnings) if warnings else None


def validate_answer(raw: _LLMAnswer, result: RunResult) -> QAAnswer:
    """Drop evidence ids that do not exist in the transcript and add warnings."""
    warnings: list[str] = []
    fail_warning = _failed_topics_warning(result)
    if fail_warning:
        warnings.append(fail_warning)

    if raw.out_of_scope:
        text = raw.text.strip() or OUT_OF_SCOPE_TEXT
        return QAAnswer(text=text, evidence=[], out_of_scope=True, warning=_join(warnings))

    known = {u.id for u in result.utterances}
    valid = list(dict.fromkeys(e for e in raw.evidence if e in known))
    dropped = [e for e in raw.evidence if e not in known]
    if dropped:
        warnings.append(f"Đã loại các ID câu không tồn tại trong transcript: {', '.join(dict.fromkeys(dropped))}.")
    if not valid:
        warnings.append("Không có bằng chứng hợp lệ cho câu trả lời này; hãy kiểm tra lại với transcript.")
    return QAAnswer(text=raw.text, evidence=valid, out_of_scope=False, warning=_join(warnings))


def answer(question: str, run_result: RunResult, llm: LLMClient, settings: Settings) -> QAAnswer:
    """Answer `question` using only this meeting.

    `run_result` MUST be the result with review edits already applied, i.e.
    `export.apply_reviews(load_result(run_dir), load_reviews(run_dir))`. Only items with
    review in (accepted, edited) are sent to the LLM; pending/rejected items are excluded
    so pipeline errors are not amplified into answers.
    """
    question = question.strip()[:MAX_QUESTION_CHARS]
    if not question:
        return QAAnswer(
            text="Vui lòng nhập câu hỏi.", evidence=[], out_of_scope=True, warning=_failed_topics_warning(run_result)
        )
    prompt = load_prompt("qa")
    user = prompt.render(
        ITEMS=_format_items(approved_items(run_result)),
        TRANSCRIPT=format_utterances(run_result.utterances),
        QUESTION=question,
    )
    raw = llm.complete_json(
        model=settings.model_strong, system=prompt.system, user=user, schema=_LLMAnswer, purpose="qa"
    )
    return validate_answer(raw, run_result)
