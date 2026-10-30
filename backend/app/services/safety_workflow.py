"""
Connects the safety engine to stored repair requests.

Every route that could lead to AI diagnosis or DIY guidance calls `refresh_safety` first, so the
decision is always made on the server from the stored facts — never taken from the browser.

Rules of thumb enforced here:
  * The assessment is recomputed from the description + all stored answers (rules may have changed).
  * Once a request is HIGH risk, its high hazards are saved as "escalations" and always re-applied,
    so later answers or edits can never make it look safe again.
"""

from sqlalchemy.orm import Session

from ..models import RepairRequest
from ..repositories import repair_requests as repo
from ..safety.engine import SafetyInput, assess
from ..safety.rules import RULES_VERSION
from ..schemas import MatchedHazardOut, SafetyAssessmentOut


def _input_for(record: RepairRequest, extra_follow_ups: list[tuple[str, str]] | None = None) -> SafetyInput:
    follow_ups = [(a["question"], a["answer"]) for a in (record.follow_up_answers or [])]
    follow_ups += extra_follow_ups or []
    sticky = [MatchedHazardOut.model_validate(h) for h in (record.safety_escalations or [])]
    return SafetyInput(
        trade_id=record.trade,
        description=record.description,
        follow_up_answers=follow_ups,
        clarifying_answers=dict(record.safety_answers or {}),
        extra_hazards=sticky,
    )


def compute(record: RepairRequest, extra_follow_ups: list[tuple[str, str]] | None = None) -> SafetyAssessmentOut:
    return assess(_input_for(record, extra_follow_ups))


def refresh_safety(db: Session, record: RepairRequest) -> SafetyAssessmentOut:
    """Recompute, store and return the safety assessment for a request."""
    assessment = compute(record)
    escalations = [h.model_dump() for h in assessment.matched_hazards if h.risk == "high"]
    # Keep earlier sticky hazards too (union by id).
    known = {h["id"] for h in escalations}
    for old in record.safety_escalations or []:
        if old["id"] not in known:
            escalations.append(old)
    repo.save_safety(db, record, assessment=assessment.model_dump(mode="json"), risk_level=assessment.risk_level, escalations=escalations)
    return assessment


def ensure_safety(db: Session, record: RepairRequest) -> SafetyAssessmentOut:
    """Use the stored assessment if it is current; otherwise (older request or new rules) recompute it."""
    stored = record.safety_assessment
    if stored and stored.get("rules_version") == RULES_VERSION:
        return SafetyAssessmentOut.model_validate(stored)
    return refresh_safety(db, record)


def escalate(db: Session, record: RepairRequest, hazard: MatchedHazardOut) -> SafetyAssessmentOut:
    """Add a high-risk hazard found after the fact (e.g. flagged by the AI). It can never be removed."""
    sticky = list(record.safety_escalations or [])
    if hazard.id not in {h["id"] for h in sticky}:
        sticky.append(hazard.model_dump())
    record.safety_escalations = sticky
    return refresh_safety(db, record)
