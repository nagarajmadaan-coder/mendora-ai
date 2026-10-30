"""
Turns stored repair requests into API responses, with honest status messages.

Safety comes first: when a request's safety risk is HIGH, the response never includes a diagnosis
(even one stored earlier) and the diagnosis status is reported as "blocked_by_safety".
"""

from pydantic import ValidationError

from ..models import RepairRequest
from ..schemas import DiagnosisOut, RepairRequestResponse, SafetyAssessmentOut, TradeOut
from .safety_workflow import compute
from .trades import get_trade

MESSAGES = {
    "not_started": "Your repair request has been saved. Check the safety result before continuing.",
    "completed": (
        "An AI assessment is available. The causes listed are possibilities, not confirmed facts. "
        "If anything feels unsafe, contact a qualified professional."
    ),
    "failed": "The last diagnosis attempt did not succeed, so no diagnosis was generated. You can try again later.",
    "blocked_by_safety": (
        "For your safety, AI diagnosis and do-it-yourself guidance are switched off for this request. "
        "Follow the safety advice and contact a qualified professional."
    ),
}

SAFETY_NOTICE = (
    "MENDORA's safety check is automatic and rule-based: it reads your words, it can't see the problem, and it can "
    "miss things. If you notice sparking electrical equipment, a suspected gas leak, smoke, or structural danger, "
    "move away and contact your local emergency service or a qualified professional."
)


def _stored_diagnosis(record: RepairRequest) -> DiagnosisOut | None:
    if not record.diagnosis:
        return None
    try:
        return DiagnosisOut.model_validate(record.diagnosis)
    except ValidationError:
        # e.g. an old Step 4/5 "safety_screen" result — never shown as if it were an AI diagnosis.
        return None


def to_response(record: RepairRequest) -> RepairRequestResponse:
    trade = get_trade(record.trade)
    safety = (
        SafetyAssessmentOut.model_validate(record.safety_assessment) if record.safety_assessment else compute(record)
    )
    blocked = safety.risk_level == "high"
    diagnosis = None if blocked else _stored_diagnosis(record)
    if blocked:
        status = "blocked_by_safety"
    elif record.diagnosis_status == "completed" and diagnosis is None:
        status = "not_started"
    else:
        status = record.diagnosis_status
    return RepairRequestResponse(
        request_id=record.id,
        status="diagnosed" if diagnosis else "accepted",
        trade=TradeOut(id=trade.id if trade else record.trade, name=trade.name if trade else record.trade),
        description=record.description,
        created_at=record.created_at,
        updated_at=record.updated_at,
        owned_by_account=record.customer_id is not None,
        safety=safety,
        diagnosis_status=status,  # type: ignore[arg-type]
        diagnosis=diagnosis,
        diagnosed_at=record.diagnosed_at if diagnosis else None,
        last_diagnosis_error=record.last_diagnosis_error,
        message=MESSAGES.get(status, MESSAGES["not_started"]),
        safety_notice=SAFETY_NOTICE,
    )
