from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import RepairRequest


def create(
    db: Session, *, trade: str, description: str, customer_id: str | None, safety_answers: dict | None = None
) -> RepairRequest:
    record = RepairRequest(trade=trade, description=description, customer_id=customer_id, safety_answers=safety_answers or None)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get(db: Session, request_id: str) -> RepairRequest | None:
    return db.get(RepairRequest, request_id)


def list_for_customer(db: Session, customer_id: str, *, limit: int = 50, offset: int = 0) -> tuple[list[RepairRequest], int]:
    base = select(RepairRequest).where(RepairRequest.customer_id == customer_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(RepairRequest.created_at.desc()).limit(limit).offset(offset)).all()
    return list(rows), total


def list_all(db: Session, *, limit: int = 50, offset: int = 0) -> tuple[list[RepairRequest], int]:
    total = db.scalar(select(func.count()).select_from(RepairRequest)) or 0
    rows = db.scalars(select(RepairRequest).order_by(RepairRequest.created_at.desc()).limit(limit).offset(offset)).all()
    return list(rows), total


def save_safety(db: Session, record: RepairRequest, *, assessment: dict, risk_level: str, escalations: list[dict] | None) -> RepairRequest:
    record.safety_assessment = assessment
    record.risk_level = risk_level
    record.safety_escalations = escalations or None
    db.commit()
    db.refresh(record)
    return record


MAX_STORED_FOLLOW_UPS = 50


def add_follow_up_answers(record: RepairRequest, answers: list[dict]) -> None:
    """Follow-up answers ACCUMULATE (never replaced), so a dangerous answer can't be dropped later."""
    existing = list(record.follow_up_answers or [])
    for answer in answers:
        if answer not in existing:
            existing.append(answer)
    record.follow_up_answers = existing[-MAX_STORED_FOLLOW_UPS:] or None


def save_diagnosis(db: Session, record: RepairRequest, *, diagnosis: dict) -> RepairRequest:
    record.diagnosis = diagnosis
    record.diagnosis_status = "completed"
    record.status = "diagnosed"
    record.diagnosed_at = datetime.now(timezone.utc)
    record.last_diagnosis_error = None
    db.commit()
    db.refresh(record)
    return record


def mark_diagnosis_failed(db: Session, record: RepairRequest, *, error_code: str) -> RepairRequest:
    """Record that an attempt failed. An earlier successful diagnosis (if any) is kept, never replaced with a fake one."""
    if record.diagnosis is None:
        record.diagnosis_status = "failed"
    record.last_diagnosis_error = error_code
    db.commit()
    db.refresh(record)
    return record
