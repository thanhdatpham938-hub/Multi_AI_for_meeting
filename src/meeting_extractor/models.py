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
    "tracker_failed",
    "conflicting_decision",
    "unresolved_reference",
    "needs_recheck",
    "quote_mismatch",
)

# Discrete labels Agent 3 assigns; code turns them into a confidence score.
CLOSING_SIGNALS = ("explicit", "implicit", "none")
# Mission 3 labels (unknown values are coerced to None by code, never drop an item).
COMMITMENTS = ("assigned", "accepted", "volunteered_conditional", "already_done", "hypothetical")
KNOWLEDGE_SCOPES = ("ephemeral", "project", "reusable")
FIELD_EVIDENCE_KEYS = ("owner", "deadline", "condition", "contradicted_by")
EVIDENCE_DIRECTNESS = ("direct", "inferred")

REVIEW_STATES = ("pending", "accepted", "edited", "rejected")


class Utterance(BaseModel):
    id: str  # "u001", "u002"… assigned in order
    time: str  # "41:05"
    speaker: str
    text: str
    start_sec: float | None = None  # set for audio input, used by the audio player
    end_sec: float | None = None


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
    status: Status  # stays required: invalid entries are dropped one by one in the tracker
    content: str | None = None
    reason: str | None = None
    evidence: list[str] = []


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
    # Labels from Agent 3 (None = not provided) – inputs of the confidence formula.
    closing_signal: str | None = None  # explicit | implicit | none
    evidence_directness: str | None = None  # direct | inferred
    contradicted_later: bool | None = None
    in_summary: bool | None = None
    verify_passed: bool | None = None  # Agent 4 result; None = type not verified
    confidence_breakdown: dict[str, float] = {}  # written by code to explain the score
    # Mission 3 – all optional so older results still load.
    commitment: str | None = None  # see COMMITMENTS (actions)
    evidence_quotes: dict[str, str] = {}  # utterance id -> verbatim quote from that utterance
    field_evidence: dict[str, list[str]] = {}  # see FIELD_EVIDENCE_KEYS -> source utterance ids
    knowledge_scope: str | None = None  # see KNOWLEDGE_SCOPES (knowledge items)
    pending_on: str | None = None  # deferred/conditional: what or whom the item waits for
    follow_up_owner: str | None = None  # who follows up an unresolved item
    related_items: list[str] = []  # item_ids of linked items (decision -> actions, blocker -> decision)


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
    audio_path: str | None = None
    failed_topics: list[str] = []  # topic ids whose processing failed at any agent


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
    confidence: float | None = Field(default=None, ge=0, le=1)
    flags: list[str] = []
    closing_signal: str | None = None
    evidence_directness: str | None = None
    contradicted_later: bool | None = None
    in_summary: bool | None = None
    commitment: str | None = None
    evidence_quotes: dict[str, str] = {}
    field_evidence: dict[str, list[str]] = {}
    knowledge_scope: str | None = None
    pending_on: str | None = None
    follow_up_owner: str | None = None


class TrackOutput(BaseModel):
    items: list[TrackedItem]


class VerifyOutput(BaseModel):
    passed: bool
    reason: str
