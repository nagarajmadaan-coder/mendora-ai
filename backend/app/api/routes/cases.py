"""
Repair-case memory — admin endpoints (Step 7).

Technicians add cases by completing a booking (see bookings). Admins can also add cases here,
review them, and verify (with a documented basis) or reject them. Only VERIFIED cases are ever
used in retrieval, and only in anonymised form.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ...config import Settings
from ...errors import ApiError
from ...models import RepairCase, RepairRequest, User
from ...schemas import ErrorResponse
from ...schemas_knowledge import CaseRejectRequest, CaseVerifyRequest, RepairCaseCreate, RepairCaseList, RepairCaseOut
from ...services import cases as svc
from ..dependencies import get_app_settings, get_db, require_roles

router = APIRouter(
    prefix="/admin/cases",
    tags=["Repair-case memory (admin)"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse, "description": "Not an admin"}},
)
admin_only = require_roles("admin")


def _get(db: Session, case_id: str) -> RepairCase:
    case = db.get(RepairCase, case_id)
    if case is None:
        raise ApiError(404, "case_not_found", f"No repair case with ID '{case_id}'.")
    return case


@router.get("", response_model=RepairCaseList, summary="List repair cases")
def list_cases(
    verification_status: str | None = Query(None, alias="status", pattern="^(unverified|verified|rejected)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
) -> RepairCaseList:
    rows, total = svc.list_cases(db, status=verification_status, limit=limit, offset=offset)
    return RepairCaseList(cases=[svc.to_out(c) for c in rows], total=total)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RepairCaseOut, summary="Record a repair case (always starts unverified)")
def create_case(
    payload: RepairCaseCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
    settings: Settings = Depends(get_app_settings),
) -> RepairCaseOut:
    if payload.repair_request_id and db.get(RepairRequest, payload.repair_request_id) is None:
        raise ApiError(404, "repair_request_not_found", "That repair request doesn't exist.")
    return svc.to_out(svc.create_case(db, payload, created_by=admin.id, currency=settings.currency))


@router.get("/{case_id}", response_model=RepairCaseOut, summary="Get one repair case", responses={404: {"model": ErrorResponse}})
def get_case(case_id: str, db: Session = Depends(get_db), _: User = Depends(admin_only)) -> RepairCaseOut:
    return svc.to_out(_get(db, case_id))


@router.post(
    "/{case_id}/verify",
    response_model=RepairCaseOut,
    summary="Verify a case (needs a technician-confirmed cause and a written basis)",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def verify_case(case_id: str, payload: CaseVerifyRequest, db: Session = Depends(get_db), admin: User = Depends(admin_only)) -> RepairCaseOut:
    return svc.to_out(svc.verify_case(db, _get(db, case_id), admin_id=admin.id, basis=payload.basis))


@router.post("/{case_id}/reject", response_model=RepairCaseOut, summary="Reject a case", responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
def reject_case(case_id: str, payload: CaseRejectRequest, db: Session = Depends(get_db), admin: User = Depends(admin_only)) -> RepairCaseOut:
    return svc.to_out(svc.reject_case(db, _get(db, case_id), admin_id=admin.id, reason=payload.reason))
