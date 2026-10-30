"""
Admin-only endpoints. Every route here requires role = admin.

The FIRST admin can't be created through the API (there's no public admin sign-up).
Create it from the command line:  python -m app.cli create-admin  (see backend/README.md).
"""

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ApiError
from ...models import TechnicianProfile, User
from ...repositories import repair_requests as repair_repo
from ...repositories import users as users_repo
from ...schemas import (
    AdminCreateUserRequest,
    ErrorResponse,
    RepairRequestListResponse,
    Role,
    UpdateUserStatusRequest,
    UserListResponse,
    UserOut,
)
from ...schemas_technician import TechnicianAdminList, TechnicianPrivate, VerificationDecision
from ...security import hash_password
from ...services import technicians as tech_svc
from ...services.repair_requests import to_response
from ...services.safety_workflow import ensure_safety
from ..dependencies import get_db, require_roles

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse, "description": "Not an admin"}},
)
admin_only = require_roles("admin")


@router.get("/users", response_model=UserListResponse, summary="List users")
def list_users(
    role: Role | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
) -> UserListResponse:
    rows, total = users_repo.list_users(db, role=role, limit=limit, offset=offset)
    return UserListResponse(users=[UserOut.model_validate(u, from_attributes=True) for u in rows], total=total)


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    summary="Create a technician or admin account",
    responses={409: {"model": ErrorResponse}},
)
def create_staff_user(
    payload: AdminCreateUserRequest,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
) -> UserOut:
    if users_repo.get_by_email(db, payload.email):
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    try:
        user = users_repo.create(
            db, email=payload.email, full_name=payload.full_name, password_hash=hash_password(payload.password), role=payload.role
        )
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists.") from exc
    return UserOut.model_validate(user, from_attributes=True)


@router.patch("/users/{user_id}", response_model=UserOut, summary="Enable or disable an account", responses={404: {"model": ErrorResponse}})
def update_user_status(
    user_id: str,
    payload: UpdateUserStatusRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
) -> UserOut:
    user = users_repo.get_by_id(db, user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "No user with this ID.")
    if user.id == admin.id and not payload.is_active:
        raise ApiError(400, "cannot_disable_self", "You can't disable your own admin account.")
    return UserOut.model_validate(users_repo.set_active(db, user, payload.is_active), from_attributes=True)


@router.get("/repair-requests", response_model=RepairRequestListResponse, summary="List all repair requests")
def list_all_requests(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
) -> RepairRequestListResponse:
    rows, total = repair_repo.list_all(db, limit=limit, offset=offset)
    for row in rows:
        ensure_safety(db, row)
    return RepairRequestListResponse(items=[to_response(r) for r in rows], total=total)


# ---------- Technician verification (Step 8) ----------


@router.get("/technicians", response_model=TechnicianAdminList, summary="List technician profiles (all statuses)")
def list_technicians(
    verification_status: str | None = Query(None, alias="status", pattern="^(unverified|pending|verified|rejected)$"),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
) -> TechnicianAdminList:
    query = db.query(TechnicianProfile)
    if verification_status:
        query = query.filter(TechnicianProfile.verification_status == verification_status)
    rows = query.order_by(TechnicianProfile.created_at.desc()).all()
    return TechnicianAdminList(technicians=[tech_svc.to_private(p) for p in rows], total=len(rows))


@router.post(
    "/technicians/{profile_id}/verification",
    response_model=TechnicianPrivate,
    summary="Verify or reject a technician profile",
    description="Only admins can do this. Write down what was checked (e.g. ID and trade licence seen in person).",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def decide_technician_verification(
    profile_id: str,
    payload: VerificationDecision,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
) -> TechnicianPrivate:
    profile = db.get(TechnicianProfile, profile_id)
    if profile is None:
        raise ApiError(404, "technician_not_found", "No technician profile with this ID.")
    return tech_svc.to_private(tech_svc.decide_verification(db, profile, admin_id=admin.id, decision=payload.decision, note=payload.note))


# ---------- Dashboard (merged feature) ----------


@router.get("/stats", summary="Counts for the admin dashboard")
def admin_stats(request: Request, db: Session = Depends(get_db), _: User = Depends(admin_only)) -> dict:
    from sqlalchemy import func

    from ...ai import web_research
    from ...ai.service import ai_status
    from ...models import Booking, Payment, RepairCase, RepairRequest, Review

    def grouped(column) -> dict:
        return {str(k): int(v) for k, v in db.query(column, func.count()).group_by(column).all()}

    settings = request.app.state.settings
    paid = db.query(Payment.currency, func.count(), func.sum(Payment.amount)).filter(Payment.status == "succeeded").group_by(Payment.currency).all()
    avg, count = db.query(func.avg(Review.rating), func.count(Review.id)).one()
    return {
        "users": grouped(User.role),
        "repair_requests": {"total": db.query(RepairRequest).count(), "by_risk": grouped(RepairRequest.risk_level)},
        "bookings": grouped(Booking.status),
        "payments_sandbox": {
            "by_status": grouped(Payment.status),
            "succeeded_totals": [{"currency": c, "count": int(n), "amount": int(a or 0)} for c, n, a in paid],
            "note": "Sandbox only — no real money.",
        },
        "technicians": {"by_verification": grouped(TechnicianProfile.verification_status), "samples": db.query(TechnicianProfile).filter(TechnicianProfile.is_sample.is_(True)).count()},
        "repair_cases": grouped(RepairCase.verification_status),
        "reviews": {"count": int(count or 0), "average": round(float(avg), 2) if count else None},
        "system": {
            "ai_diagnosis": ai_status(settings),
            "web_research": web_research.status(settings),
            "payments_provider": settings.payment_provider,
            "demo_mode": settings.demo_mode_enabled,
        },
    }


@router.get("/safety-escalations", summary="Recent HIGH-risk reports")
def safety_escalations(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), _: User = Depends(admin_only)) -> dict:
    from ...ai.privacy import redact
    from ...models import Booking, RepairRequest

    rows = db.query(RepairRequest).filter(RepairRequest.risk_level == "high").order_by(RepairRequest.created_at.desc()).limit(limit).all()
    items = []
    for r in rows:
        hazards = [h.get("label") for h in ((r.safety_assessment or {}).get("matched_hazards") or []) if isinstance(h, dict)]
        items.append({
            "request_id": r.id,
            "trade": r.trade,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "hazards": [h for h in hazards if h],
            "description": redact(r.description)[:200],
            "has_account": r.customer_id is not None,
            "bookings": db.query(Booking).filter(Booking.repair_request_id == r.id).count(),
        })
    return {"items": items, "total": len(items), "note": "High-risk reports never get AI diagnosis or DIY guidance."}
