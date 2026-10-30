"""Request/response shapes for the knowledge base and repair-case memory (Step 7)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .schemas import SafetyAssessmentOut

Trade = Literal["plumbing", "electrical", "carpentry"]


class KnowledgeCauseOut(BaseModel):
    title: str
    explanation: str
    is_possibility: Literal[True] = True  # always a possibility, never a confirmed diagnosis


class KnowledgeSourceOut(BaseModel):
    type: str
    verification_status: Literal["unverified", "professionally_reviewed"]
    note: str


class KnowledgeEntrySummary(BaseModel):
    id: str
    trade: Trade
    category: str
    title: str
    symptoms: list[str]
    professional_recommended: bool
    source: KnowledgeSourceOut


class KnowledgeEntryDetail(KnowledgeEntrySummary):
    """Everything except the steps. Steps are only given after a safety check (POST /api/knowledge/search)."""

    clarifying_questions: list[str]
    possible_causes: list[KnowledgeCauseOut]
    professional_reason: str | None
    safety_restrictions: list[str]
    hazard_categories: list[str]


class KnowledgeEntryList(BaseModel):
    entries: list[KnowledgeEntrySummary]
    total: int
    knowledge_version: str
    note: str = "Repair steps are only shown after a safety check — use POST /api/knowledge/search."


class GuidanceEntryOut(KnowledgeEntryDetail):
    next_steps: list[str] = Field(description="Empty unless the safety check allows guidance")
    steps_shown: bool
    steps_note: str | None = None


class KnowledgeMatchOut(BaseModel):
    entry: GuidanceEntryOut
    relevance: float = Field(ge=0, le=1, description="How well the entry matched your words (0–1)")
    matched_terms: list[str] = Field(description="The words that matched (after simple normalisation)")


class SimilarCaseOut(BaseModel):
    """An anonymised, VERIFIED past case. No customer, address, request or technician details."""

    case_id: str
    trade: Trade
    category: str | None
    symptoms_summary: str
    confirmed_cause: str
    parts_used: list[str]
    completion_minutes: int | None
    cost_amount: int | None
    currency: str | None
    relevance: float


class KnowledgeGuidanceOut(BaseModel):
    status: Literal["matched", "no_match", "blocked_by_safety"]
    mode: Literal["full", "professional_only", "blocked"] = Field(
        description="full = low risk (steps shown); professional_only = medium risk (no steps); blocked = high risk (nothing shown)"
    )
    message: str
    safety: SafetyAssessmentOut
    matches: list[KnowledgeMatchOut]
    similar_verified_cases: list[SimilarCaseOut]
    retriever: str
    knowledge_version: str
    disclaimer: str


# ---------- Repair-case memory ----------

CauseSource = Literal["technician_confirmed", "customer_reported", "ai_suggestion"]


class CaseQA(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=500)


class RepairCaseCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "trade": "plumbing",
                    "category": "Taps",
                    "symptoms": "Kitchen tap dripping from the spout when fully closed.",
                    "clarifying_qa": [{"question": "Spout or handle?", "answer": "Spout"}],
                    "confirmed_cause": "Worn tap washer",
                    "cause_source": "technician_confirmed",
                    "parts_used": ["15 mm tap washer"],
                    "completion_minutes": 25,
                    "cost_amount": 350,
                }
            ]
        },
    )

    trade: Trade
    category: str | None = Field(default=None, max_length=80)
    symptoms: str = Field(min_length=10, max_length=1000)
    clarifying_qa: list[CaseQA] = Field(default_factory=list, max_length=10)
    confirmed_cause: str | None = Field(default=None, max_length=500)
    cause_source: CauseSource
    parts_used: list[str] = Field(default_factory=list, max_length=20)
    completion_minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 7)
    cost_amount: int | None = Field(default=None, ge=0, le=10_000_000)
    repair_request_id: str | None = None

    @field_validator("parts_used")
    @classmethod
    def _clean_parts(cls, parts: list[str]) -> list[str]:
        cleaned = [p.strip() for p in parts if p.strip()]
        if any(len(p) > 120 for p in cleaned):
            raise ValueError("Each part must be at most 120 characters.")
        return cleaned


class RepairCaseOut(BaseModel):
    """Full record — admins only."""

    id: str
    trade: Trade
    category: str | None
    symptoms: str
    clarifying_qa: list[CaseQA]
    confirmed_cause: str | None
    cause_source: CauseSource
    parts_used: list[str]
    completion_minutes: int | None
    cost_amount: int | None
    currency: str | None
    verification_status: Literal["unverified", "verified", "rejected"]
    verification_basis: str | None
    verified_at: datetime | None
    rejection_reason: str | None
    repair_request_id: str | None
    booking_id: str | None
    created_at: datetime


class RepairCaseList(BaseModel):
    cases: list[RepairCaseOut]
    total: int


class CaseVerifyRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"basis": "Technician completion report for booking 1234 with photo of the replaced washer."}]},
    )
    basis: str = Field(min_length=15, max_length=1000, description="The documented reason this case can be trusted")


class CaseRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=1000)
