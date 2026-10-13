"""Pydantic schemas shared by every stage of the pipeline."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

VALID_FLAGS = (
    "no_closing_signal",
    "authority_unclear",
    "number_check",
    "missing_owner",
    "verify_failed",
    "low_confidence",
)

REVIEW_STATES = ("pending", "accepted", "edited", "rejected")


class Utterance(BaseModel):
    id: str  # "u001", "u002"… assigned in order
    time: str  # "41:05"
    speaker: str
    text: str


class Participant(BaseModel):
    name: str
    role: str | None = None
    can_decide: bool = False


class MeetingMeta(BaseModel):
    title: str | None = None
    date: str | None = None  # free text, e.g. "12/04/2025"
    start_time: str | None = None
    end_time: str | None = None
    project: str | None = None
    agenda: list[str] = []
    participants: list[Participant] = []


class Topic(BaseModel):
    topic_id: str  # "t01"
    title: str
    utterance_ids: list[str]  # may be non-contiguous
    is_off_agenda: bool = False


class ItemType(str, Enum):
    decision = "decision"
    action = "action"
    blocker = "blocker"
    request = "request"
    open_issue = "open_issue"
    knowledge = "knowledge"


class Status(str, Enum):
    proposed = "proposed"
    superseded = "superseded"
    confirmed = "confirmed"
    conditional = "conditional"
    deferred = "deferred"
    open = "open"


class Candidate(BaseModel):  # Agent 2 output
    type: ItemType
    topic_id: str
    content: str
    speaker: str
    evidence: list[str] = Field(min_length=1)  # utterance IDs
    owner: str | None = None
    deadline: str | None = None


class HistoryEntry(BaseModel):
    status: Status
    content: str | None = None
    reason: str | None = None
    evidence: list[str]


class Item(BaseModel):  # final output
    item_id: str
    type: ItemType
    topic_id: str
    topic: str
    content: str
    status: Status | None = None  # required only for decisions
    condition: str | None = None  # required when status = conditional
    history: list[HistoryEntry] = []
    owner: str | None = None
    deadline: str | None = None
    evidence: list[str]
    confidence: float = Field(ge=0, le=1)
    flags: list[str] = []
    review: str = "pending"  # pending | accepted | edited | rejected


class RunResult(BaseModel):
    run_id: str
    source_file: str
    model_light: str
    model_strong: str
    prompt_versions: dict[str, str]  # content hash of each prompt file
    utterances: list[Utterance]
    topics: list[Topic]
    items: list[Item]
    warnings: list[str] = []
    meta: MeetingMeta | None = None


# ---- LLM response envelopes (one per agent) ----


class SegmentOutput(BaseModel):
    topics: list[Topic]


class ExtractOutput(BaseModel):
    candidates: list[Candidate]


class TrackedItem(BaseModel):
    """Agent 3 output item: an Item before code assigns id/topic name."""

    type: ItemType
    content: str
    status: Status | None = None
    condition: str | None = None
    history: list[HistoryEntry] = []
    owner: str | None = None
    deadline: str | None = None
    evidence: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    flags: list[str] = []


class TrackOutput(BaseModel):
    items: list[TrackedItem]


class VerifyOutput(BaseModel):
    passed: bool
    reason: str
