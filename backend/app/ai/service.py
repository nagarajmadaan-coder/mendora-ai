"""
Diagnosis service: the single entry point the API routes use.

    diagnose(..., safety=<SafetyAssessmentOut>, settings, transport) -> DiagnosisOutcome

The SAFETY ASSESSMENT comes first and always wins (Step 6):
  * high risk              → refused here with SafetyBlockedError (the AI is never called)
  * medium risk            → "professional_only": the AI may explain possible causes, but the next step is
                             always to get a professional, and the AI is told not to give DIY steps
  * low risk               → normal diagnosis
After the AI answers:
  * if the AI itself flags urgent danger → no diagnosis is kept; the case is escalated to HIGH
  * anything the AI wrote that looks like a dangerous DIY instruction is removed and replaced
  * malformed output → AIInvalidResponse (never a made-up result)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError, field_validator

from ..config import Settings
from ..safety.engine import SafetyBlockedError, find_unsafe_instruction
from ..schemas import DiagnosisOut, MatchedHazardOut, PossibleCause, SafetyAssessmentOut
from .errors import AIInvalidResponse, AINotConfigured
from .http import Transport, urllib_transport
from .privacy import redact
from .prompts import DiagnosisInput
from .providers import AnthropicProvider, DiagnosisProvider, NebiusProvider, OpenAIProvider
from .tavily_trial import TRIAL_DISCLAIMER, TavilyTrialProvider

log = logging.getLogger("mendora.ai")

AI_DISCLAIMER = (
    "AI-generated from your description only — MENDORA cannot see the problem. The causes listed are possibilities, "
    "not a confirmed diagnosis. If anything seems unsafe, stop and contact a qualified professional."
)

AI_FLAGGED_HAZARD = MatchedHazardOut(
    id="ai_flagged_danger",
    category="general",
    label="Possible urgent danger noticed during the AI assessment",
    risk="high",
    matched_text=None,
    guidance="general_danger",
)

_PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "nebius": NebiusProvider, "tavily": TavilyTrialProvider}


class _ModelOutput(BaseModel):
    """Strict check of what the model returned. Extra keys are ignored; wrong types/empty text are rejected."""

    summary: str = Field(min_length=1, max_length=1200)
    possible_causes: list[PossibleCause] = Field(max_length=6)
    follow_up_questions: list[str] = Field(max_length=5)
    recommended_next_step: str = Field(min_length=1, max_length=800)
    professional_recommended: bool
    professional_reason: str = Field(default="", max_length=600)
    urgent_danger: bool

    @field_validator("summary", "recommended_next_step", "professional_reason")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("follow_up_questions")
    @classmethod
    def _clean_questions(cls, value: list[str]) -> list[str]:
        cleaned = [q.strip() for q in value if isinstance(q, str) and q.strip()]
        if any(len(q) > 300 for q in cleaned):
            raise ValueError("follow-up question too long")
        return cleaned[:3]


@dataclass(frozen=True)
class DiagnosisOutcome:
    """Either a diagnosis to save, or a danger the AI flagged (then the case must be escalated to HIGH)."""

    diagnosis: dict | None
    escalation: MatchedHazardOut | None = None


def ai_status(settings: Settings) -> dict:
    model = settings.resolved_ai_model
    return {
        "provider": settings.ai_provider,
        "model": model,
        "configured": settings.ai_provider != "none" and bool(model) and bool(settings.ai_api_key),
    }


def build_provider(settings: Settings, transport: Transport | None = None) -> DiagnosisProvider:
    if settings.ai_provider == "none":
        raise AINotConfigured("MENDORA_AI_PROVIDER is 'none'")
    model = settings.resolved_ai_model
    if not model:
        raise AINotConfigured(f"No model set for provider '{settings.ai_provider}'. Set MENDORA_AI_MODEL.")
    api_key = settings.ai_api_key
    if not api_key:
        raise AINotConfigured(f"No API key set for provider '{settings.ai_provider}'.")
    return _PROVIDERS[settings.ai_provider](
        api_key=api_key,
        model=model,
        transport=transport or urllib_transport,
        timeout=settings.ai_timeout_seconds,
        max_tokens=settings.ai_max_output_tokens,
        base_url=settings.ai_base_url,
    )


def diagnose(
    *,
    trade_id: str,
    trade_name: str,
    description: str,
    follow_up_answers: list[tuple[str, str]],
    safety: SafetyAssessmentOut,
    settings: Settings,
    transport: Transport | None = None,
) -> DiagnosisOutcome:
    """Returns a DiagnosisOutcome or raises (AIError / SafetyBlockedError). Never invents a result."""
    # 1. Safety gate — checked here too, not only in the route (defence in depth).
    if safety.risk_level == "high" or safety.ai_diagnosis == "blocked":
        raise SafetyBlockedError("High-risk case: AI diagnosis and DIY guidance are not allowed.")
    mode = "full" if safety.risk_level == "low" and safety.ai_diagnosis == "full" else "professional_only"

    # 2. Provider (raises AINotConfigured if anything is missing).
    provider = build_provider(settings, transport)

    # 3. Call with redacted text only. Safety labels are server-generated, so they contain no personal data.
    data = DiagnosisInput(
        trade_name=trade_name,
        description=redact(description),
        follow_up_answers=[(redact(q), redact(a)) for q, a in follow_up_answers],
        safety_mode=mode,
        safety_labels=[h.label for h in safety.matched_hazards],
    )
    raw = provider.generate(data)

    # 4. Validate.
    trial = provider.name == "tavily"
    trial_sources = raw.get("_sources", []) if trial and isinstance(raw, dict) else []
    trial_filtered = bool(raw.get("_filtered")) if trial and isinstance(raw, dict) else False
    try:
        output = _ModelOutput.model_validate(raw)
    except ValidationError as exc:
        log.error("Invalid model output from %s: %s", provider.name, exc.errors()[:3])
        raise AIInvalidResponse("Model output failed validation") from exc

    # 5. The AI noticed danger the rules missed → escalate; keep nothing the AI wrote.
    if output.urgent_danger:
        log.warning("AI flagged urgent danger; escalating to high risk")
        return DiagnosisOutcome(diagnosis=None, escalation=AI_FLAGGED_HAZARD)

    # 6. Screen the AI's text for unsafe DIY instructions.
    filtered = trial_filtered
    causes = []
    for cause in output.possible_causes[:5]:
        if find_unsafe_instruction(f"{cause.title}. {cause.explanation}"):
            filtered = True
            continue
        causes.append(cause)
    questions = [q for q in output.follow_up_questions if not find_unsafe_instruction(q)]
    filtered = filtered or len(questions) != len(output.follow_up_questions)
    summary = output.summary
    if find_unsafe_instruction(summary):
        filtered = True
        summary = f"You reported a {trade_name.lower()} problem. Some of the AI's wording was removed for safety."

    professional = safety.professional
    next_step = output.recommended_next_step
    professional_recommended = output.professional_recommended or safety.requires_professional
    reason = output.professional_reason or None
    if mode == "professional_only":
        next_step = f"Don't try to repair this yourself. Have {professional} check it."
        professional_recommended = True
        reason = reason or f"The safety check found a possible risk: {', '.join(h.label.lower() for h in safety.matched_hazards)}."
    elif find_unsafe_instruction(next_step):
        filtered = True
        next_step = f"This may need hands-on work that isn't safe without training. Have {professional} take a look."
        professional_recommended = True
        reason = reason or "The suggested fix involves work that should be done by a professional."

    return DiagnosisOutcome(
        diagnosis=DiagnosisOut(
            source="ai",
            summary=summary,
            possible_causes=causes,
            follow_up_questions=questions,
            recommended_next_step=next_step,
            professional_recommended=professional_recommended,
            professional_reason=reason,
            safety_mode=mode,  # type: ignore[arg-type]
            safety_filter_applied=filtered,
            disclaimer=TRIAL_DISCLAIMER if trial else AI_DISCLAIMER,
            trial=trial,
            sources=trial_sources,
            provider=provider.name,
            model=provider.model,
            generated_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
    )
