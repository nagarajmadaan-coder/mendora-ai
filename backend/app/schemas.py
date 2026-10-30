"""
Request and response shapes (Pydantic models).

FastAPI uses these to validate incoming JSON, shape outgoing JSON, and build /docs.
Passwords and password hashes never appear in any response model.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .safety.rules import QUESTIONS
from .services.trades import SUPPORTED_TRADE_IDS, get_trade

# Same limits as the frontend form (src/lib/validateIntake.ts), so both sides agree.
DESCRIPTION_MIN_LENGTH = 20
DESCRIPTION_MAX_LENGTH = 1000
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

EXAMPLE_REQUEST_ID = "3f2b8c1e-6a4d-4e7b-9c0a-2d5e8f1b7a90"
EXAMPLE_USER_ID = "8c0a2d5e-1b7a-4e7b-9f2b-3f2b8c1e6a4d"
EXAMPLE_DESCRIPTION = "The kitchen sink drains very slowly and gurgles. It started two days ago."

Role = Literal["customer", "technician", "admin"]


# =====================================================================
# Shared / health / trades
# =====================================================================


class TradeOut(BaseModel):
    id: str = Field(examples=["plumbing"])
    name: str = Field(examples=["Plumbing"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "service": "MENDORA API",
                    "version": "0.2.0",
                    "message": "MENDORA API is running.",
                    "storage": "database",
                    "safety_engine": {"enabled": True, "rules_version": "2026-10-27.1", "needs_ai_key": False},
                    "ai_diagnosis": {"provider": "anthropic", "model": "claude-sonnet-5-5", "configured": True},
                }
            ]
        }
    )

    class AIStatus(BaseModel):
        provider: str
        model: str | None
        configured: bool = Field(description="True when a provider, model and API key are all set. Does not prove the key works.")

    class WebResearchStatus(BaseModel):
        provider: str
        configured: bool = Field(description="True when a Tavily API key is set. Does not prove the key works.")

    class PaymentStatus(BaseModel):
        provider: str
        enabled: bool
        real_money: bool = Field(default=False, description="Always false: only a sandbox (simulated) provider exists.")

    class SafetyEngineStatus(BaseModel):
        enabled: bool
        rules_version: str
        needs_ai_key: bool = Field(default=False, description="The safety engine is rule-based and never needs an AI key.")

    status: Literal["ok"]
    service: str
    version: str
    message: str
    storage: Literal["database"]
    safety_engine: SafetyEngineStatus
    ai_diagnosis: AIStatus
    payments: PaymentStatus | None = None
    web_research: WebResearchStatus | None = None


class TradeListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "trades": [
                        {"id": "plumbing", "name": "Plumbing"},
                        {"id": "electrical", "name": "Electrical"},
                        {"id": "carpentry", "name": "Carpentry"},
                    ]
                }
            ]
        }
    )

    trades: list[TradeOut]


# =====================================================================
# Authentication & users
# =====================================================================


def _check_password(value: str) -> str:
    if not value.strip():
        raise ValueError("Password must not be empty.")
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters.")
    return value


def _check_name(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError("Full name must not be empty.")
    if len(text) > 100:
        raise ValueError("Full name must be at most 100 characters.")
    return text


class RegisterRequest(BaseModel):
    """Public sign-up. Always creates a CUSTOMER account — the role cannot be chosen here."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"email": "asha@example.com", "password": "a-long-passphrase", "full_name": "Asha Kumar"}]},
    )

    email: EmailStr
    password: str = Field(description=f"{PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} characters")
    full_name: str

    _password = field_validator("password")(_check_password)
    _name = field_validator("full_name")(_check_name)


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"email": "asha@example.com", "password": "a-long-passphrase"}]},
    )

    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class UserOut(BaseModel):
    id: str = Field(examples=[EXAMPLE_USER_ID])
    email: str = Field(examples=["asha@example.com"])
    full_name: str = Field(examples=["Asha Kumar"])
    role: Role
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str = Field(description="Send as the header  Authorization: Bearer <token>")
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the token expires", examples=[3600])
    user: UserOut


class AdminCreateUserRequest(BaseModel):
    """Admins create technician (or additional admin) accounts. There is no public way to do this."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"email": "ravi.tech@example.com", "password": "another-long-passphrase", "full_name": "Ravi S", "role": "technician"}]
        },
    )

    email: EmailStr
    password: str
    full_name: str
    role: Literal["technician", "admin"]

    _password = field_validator("password")(_check_password)
    _name = field_validator("full_name")(_check_name)


class UpdateUserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class UserListResponse(BaseModel):
    users: list[UserOut]
    total: int


class TechnicianOverview(BaseModel):
    technician: UserOut
    assigned_jobs: list[dict] = Field(default_factory=list)
    message: str


# =====================================================================
# Safety assessment (Step 6)
# =====================================================================

RiskLevel = Literal["low", "medium", "high"]
HazardCategory = Literal["electrical", "gas", "structural", "plumbing", "carpentry", "general"]
SafetyAnswer = Literal["yes", "no", "not_sure"]


class MatchedHazardOut(BaseModel):
    id: str = Field(examples=["electrical_sparking"])
    category: HazardCategory
    label: str = Field(examples=["Sparking or arcing"])
    risk: Literal["medium", "high"]
    matched_text: str | None = Field(default=None, description="The words that triggered this hazard", examples=["sparks"])
    guidance: str = Field(default="general_danger", description="Internal key of the safety advice used")


class SafetyQuestionOut(BaseModel):
    id: str = Field(examples=["crack_signs"])
    text: str
    options: list[SafetyAnswer] = Field(default_factory=lambda: ["yes", "no", "not_sure"])


class AnsweredQuestionOut(BaseModel):
    id: str
    text: str
    answer: SafetyAnswer


class SafetyAssessmentOut(BaseModel):
    """The safety engine's decision. It is made BEFORE any AI diagnosis and the AI can't override it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "risk_level": "high",
                    "matched_hazards": [
                        {"id": "electrical_sparking", "category": "electrical", "label": "Sparking or arcing", "risk": "high", "matched_text": "sparks", "guidance": "electrical_fire"}
                    ],
                    "allow_diy": False,
                    "requires_professional": True,
                    "recommended_action": "Keep away from it and don't touch it. If there is smoke or fire, leave and call the emergency number. Otherwise contact a qualified electrician.",
                    "safety_message": "Sparks, smoke, burning smells or scorch marks can mean wiring is overheating, which can start a fire. For your safety, MENDORA won't give do-it-yourself repair steps for this.",
                    "emergency": True,
                    "emergency_steps": ["Don't touch the socket, switch, appliance or cable.", "…"],
                    "clarifying_questions": [],
                    "answered_questions": [],
                    "resolved_hazards": [],
                    "ai_diagnosis": "blocked",
                    "professional": "a qualified electrician",
                    "rules_version": "2026-10-27.1",
                    "assessed_at": "2026-10-27T15:00:00Z",
                    "disclaimer": "This is an automatic, rule-based check of the words you used — not an inspection. …",
                }
            ]
        }
    )

    risk_level: RiskLevel
    matched_hazards: list[MatchedHazardOut]
    allow_diy: bool = Field(description="True only for low risk: the case may continue to low-risk guidance.")
    requires_professional: bool
    recommended_action: str
    safety_message: str
    emergency: bool = Field(description="True when the advice is to leave or move away from the area now.")
    emergency_steps: list[str] = Field(default_factory=list)
    clarifying_questions: list[SafetyQuestionOut] = Field(default_factory=list, description="Medium risk: questions that can clarify the risk")
    answered_questions: list[AnsweredQuestionOut] = Field(default_factory=list)
    resolved_hazards: list[str] = Field(default_factory=list, description="Medium hazards cleared by your answers")
    ai_diagnosis: Literal["full", "professional_only", "blocked"] = Field(
        description="full = normal AI diagnosis; professional_only = AI may explain possible causes but gives no DIY steps; blocked = no AI diagnosis"
    )
    professional: str = Field(examples=["a qualified electrician"])
    rules_version: str
    assessed_at: datetime
    disclaimer: str


class ClarifyingAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(description="An id from clarifying_questions", examples=["crack_signs"])
    answer: SafetyAnswer

    @field_validator("question_id")
    @classmethod
    def _known_question(cls, value: str) -> str:
        if value not in QUESTIONS:
            raise ValueError(f"Unknown safety question '{value}'.")
        return value


def answers_to_dict(answers: list[ClarifyingAnswer]) -> dict[str, str]:
    """Later answers to the same question win."""
    return {a.question_id: a.answer for a in answers}


# =====================================================================
# Diagnosis
# =====================================================================


class PossibleCause(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=600)


class DiagnosisSource(BaseModel):
    title: str
    url: str
    domain: str


class DiagnosisOut(BaseModel):
    """
    A stored AI diagnosis (possible causes are NOT confirmed).

    safety_mode = "full"              → low-risk case: the AI may suggest a simple, safe next step
    safety_mode = "professional_only" → medium-risk case: no DIY steps; the next step is always a professional
    safety_filter_applied             → MENDORA removed something the AI wrote because it wasn't safe to do yourself
    High-risk cases never get a diagnosis.
    """

    source: Literal["ai"]
    summary: str
    possible_causes: list[PossibleCause] = Field(default_factory=list, max_length=6)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)
    recommended_next_step: str
    professional_recommended: bool
    professional_reason: str | None = None
    safety_mode: Literal["full", "professional_only"] = "full"
    safety_filter_applied: bool = False
    disclaimer: str
    # trial = True: made by the Tavily TRIAL provider (a web-search summary, not a full AI diagnosis)
    trial: bool = False
    sources: list[DiagnosisSource] = Field(default_factory=list, max_length=5)
    provider: str | None = None
    model: str | None = None
    generated_at: datetime


class FollowUpAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=500)

    @field_validator("question", "answer")
    @classmethod
    def _strip(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Must not be empty.")
        return text


class DiagnosisRequest(BaseModel):
    """Optional answers to the follow-up questions from a previous diagnosis."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"follow_up_answers": []},
                {"follow_up_answers": [{"question": "Is the water backing up in other drains too?", "answer": "No, only the kitchen sink."}]},
            ]
        },
    )

    follow_up_answers: list[FollowUpAnswer] = Field(default_factory=list, max_length=5)


# =====================================================================
# Repair requests
# =====================================================================


class RepairRequestCreate(BaseModel):
    """What the client sends to create a repair request."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"trade_id": "plumbing", "description": EXAMPLE_DESCRIPTION}]},
    )

    trade_id: str = Field(description=f"One of: {', '.join(SUPPORTED_TRADE_IDS)}", examples=["plumbing"])
    description: str = Field(
        description=f"The problem in the user's own words ({DESCRIPTION_MIN_LENGTH}–{DESCRIPTION_MAX_LENGTH} characters).",
        examples=[EXAMPLE_DESCRIPTION],
    )
    clarifying_answers: list[ClarifyingAnswer] = Field(
        default_factory=list, max_length=20, description="Optional answers to safety questions (from POST /api/safety/assess)"
    )

    @field_validator("trade_id")
    @classmethod
    def trade_must_be_supported(cls, value: str) -> str:
        normalized = value.strip().lower()
        if get_trade(normalized) is None:
            raise ValueError(f"Unsupported trade_id '{value}'. Supported values: {', '.join(SUPPORTED_TRADE_IDS)}.")
        return normalized

    @field_validator("description")
    @classmethod
    def description_must_be_meaningful(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Description must not be empty.")
        if len(text) < DESCRIPTION_MIN_LENGTH:
            raise ValueError(
                f"Description is too short ({len(text)} characters). Please use at least {DESCRIPTION_MIN_LENGTH} characters."
            )
        if len(text) > DESCRIPTION_MAX_LENGTH:
            raise ValueError(f"Description is too long. Please use at most {DESCRIPTION_MAX_LENGTH} characters.")
        return text


class RepairRequestResponse(BaseModel):
    """A stored repair request (returned by create, get, list and diagnosis endpoints)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "request_id": EXAMPLE_REQUEST_ID,
                    "status": "accepted",
                    "trade": {"id": "plumbing", "name": "Plumbing"},
                    "description": EXAMPLE_DESCRIPTION,
                    "created_at": "2026-10-25T10:15:30.123456Z",
                    "updated_at": "2026-10-25T10:15:30.123456Z",
                    "owned_by_account": True,
                    "safety": {"risk_level": "low", "allow_diy": True, "ai_diagnosis": "full", "…": "see SafetyAssessmentOut"},
                    "diagnosis_status": "not_started",
                    "diagnosis": None,
                    "diagnosed_at": None,
                    "last_diagnosis_error": None,
                    "message": "Your repair request has been saved. No diagnosis has been generated yet.",
                    "safety_notice": "MENDORA does not yet have a full safety assessment engine. …",
                }
            ]
        }
    )

    request_id: str
    status: Literal["accepted", "diagnosed"]
    trade: TradeOut
    description: str
    created_at: datetime
    updated_at: datetime
    owned_by_account: bool = Field(description="True if the request belongs to a signed-in customer (then only they and admins can read it).")
    safety: SafetyAssessmentOut = Field(description="The safety check for this request. Always present; it decides what can happen next.")
    diagnosis_status: Literal["not_started", "completed", "failed", "blocked_by_safety"]
    diagnosis: DiagnosisOut | None = Field(default=None, description="Always null when the safety risk is high.")
    diagnosed_at: datetime | None = None
    last_diagnosis_error: str | None = Field(default=None, description="Error code of the most recent failed attempt, if any.")
    message: str
    safety_notice: str


class RepairRequestListResponse(BaseModel):
    items: list[RepairRequestResponse]
    total: int


class SafetyAssessRequest(RepairRequestCreate):
    """Check a report without saving it. Same rules as creating a request."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"trade_id": "electrical", "description": "Sparks come out of the kitchen socket when I plug in the kettle."},
                {"trade_id": "carpentry", "description": "There is a crack in the bedroom wall above the door frame.",
                 "clarifying_answers": [{"question_id": "crack_signs", "answer": "no"}]},
            ]
        },
    )

    follow_up_answers: list[FollowUpAnswer] = Field(default_factory=list, max_length=10)


class SafetyAnswersRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"answers": [{"question_id": "crack_signs", "answer": "no"}]}]},
    )
    answers: list[ClarifyingAnswer] = Field(min_length=1, max_length=20)


# =====================================================================
# Errors
# =====================================================================


class ErrorDetail(BaseModel):
    field: str | None = Field(default=None, examples=["trade_id"])
    message: str = Field(examples=["Unsupported trade_id 'roofing'. Supported values: plumbing, electrical, carpentry."])


class ErrorBody(BaseModel):
    code: str = Field(examples=["validation_error"])
    message: str = Field(examples=["The request is invalid. See 'details' for each problem."])
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Every error from this API has this shape."""

    error: ErrorBody
