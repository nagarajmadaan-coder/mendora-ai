"""
Repair-case memory rules (Step 7).

A case only becomes VERIFIED when:
  * an admin verifies it, with a written basis (e.g. "technician completion report for booking X"),
  * it has a confirmed cause, and
  * that cause was confirmed by a technician — never an AI suggestion or a customer's guess.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.privacy import redact
from ..errors import ApiError
from ..models import RepairCase
from ..schemas_knowledge import RepairCaseCreate, RepairCaseOut


def to_out(case: RepairCase) -> RepairCaseOut:
    return RepairCaseOut(
        id=case.id,
        trade=case.trade,  # type: ignore[arg-type]
        category=case.category,
        symptoms=case.symptoms,
        clarifying_qa=case.clarifying_qa or [],
        confirmed_cause=case.confirmed_cause,
        cause_source=case.cause_source,  # type: ignore[arg-type]
        parts_used=list(case.parts_used or []),
        completion_minutes=case.completion_minutes,
        cost_amount=case.cost_amount,
        currency=case.currency,
        verification_status=case.verification_status,  # type: ignore[arg-type]
        verification_basis=case.verification_basis,
        verified_at=case.verified_at,
        rejection_reason=case.rejection_reason,
        repair_request_id=case.repair_request_id,
        booking_id=case.booking_id,
        created_at=case.created_at,
    )


def create_case(
    db: Session,
    data: RepairCaseCreate,
    *,
    created_by: str | None,
    currency: str,
    booking_id: str | None = None,
    technician_profile_id: str | None = None,
) -> RepairCase:
    case = RepairCase(
        repair_request_id=data.repair_request_id,
        booking_id=booking_id,
        technician_profile_id=technician_profile_id,
        trade=data.trade,
        category=data.category,
        symptoms=redact(data.symptoms),  # no emails / phone numbers in the case memory
        clarifying_qa=[{"question": redact(q.question), "answer": redact(q.answer)} for q in data.clarifying_qa] or None,
        confirmed_cause=redact(data.confirmed_cause) if data.confirmed_cause else None,
        cause_source=data.cause_source,
        parts_used=data.parts_used or None,
        completion_minutes=data.completion_minutes,
        cost_amount=data.cost_amount,
        currency=currency if data.cost_amount is not None else None,
        verification_status="unverified",
        created_by=created_by,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def verify_case(db: Session, case: RepairCase, *, admin_id: str, basis: str) -> RepairCase:
    if case.verification_status != "unverified":
        raise ApiError(409, "invalid_case_status", f"Only unverified cases can be verified (this one is {case.verification_status}).")
    if not case.confirmed_cause:
        raise ApiError(422, "cannot_verify", "A case needs a confirmed cause before it can be verified.")
    if case.cause_source != "technician_confirmed":
        raise ApiError(
            422,
            "cannot_verify",
            f"Only causes confirmed by a technician can be verified (this cause is '{case.cause_source}'). "
            "An AI suggestion or a customer's guess is not a confirmed cause.",
        )
    case.verification_status = "verified"
    case.verification_basis = basis.strip()
    case.verified_by = admin_id
    case.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)
    return case


def reject_case(db: Session, case: RepairCase, *, admin_id: str, reason: str) -> RepairCase:
    if case.verification_status == "rejected":
        raise ApiError(409, "invalid_case_status", "This case is already rejected.")
    case.verification_status = "rejected"
    case.rejection_reason = reason.strip()
    case.verified_by = admin_id
    case.verified_at = None
    case.verification_basis = None
    db.commit()
    db.refresh(case)
    return case


def list_cases(db: Session, *, status: str | None, limit: int, offset: int) -> tuple[list[RepairCase], int]:
    query = select(RepairCase)
    if status:
        query = query.where(RepairCase.verification_status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(RepairCase.created_at.desc()).limit(limit).offset(offset)).all()
    return list(rows), total
