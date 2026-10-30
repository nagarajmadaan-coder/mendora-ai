"""
POST /api/safety/assess — check a report WITHOUT saving it.

Open to everyone (no sign-in), so someone in danger gets safety advice immediately.
It never returns repair instructions. Uses the same engine as saved requests.
"""

from fastapi import APIRouter

from ...safety.engine import SafetyInput, assess
from ...schemas import ErrorResponse, SafetyAssessmentOut, SafetyAssessRequest, answers_to_dict

router = APIRouter(prefix="/safety", tags=["Safety"])


@router.post(
    "/assess",
    response_model=SafetyAssessmentOut,
    summary="Run the safety check on a repair report (nothing is saved)",
    description=(
        "Rule-based and deterministic — no AI is used. Returns the risk level (low / medium / high), the hazards found, "
        "whether DIY may continue, and clear advice. Medium-risk results include clarifying questions; send their "
        "answers back in `clarifying_answers` to refine the result. High risk can't be lowered by answers."
    ),
    responses={422: {"model": ErrorResponse, "description": "Invalid trade, description or answers"}},
)
def assess_report(payload: SafetyAssessRequest) -> SafetyAssessmentOut:
    return assess(
        SafetyInput(
            trade_id=payload.trade_id,
            description=payload.description,
            follow_up_answers=[(a.question, a.answer) for a in payload.follow_up_answers],
            clarifying_answers=answers_to_dict(payload.clarifying_answers),
        )
    )
