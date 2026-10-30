"""
Technician self-service (Step 8). Every route requires role = technician.

Technicians manage their own profile and availability. They can submit the profile for
verification, but only an admin can mark it verified.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...config import Settings
from ...errors import ApiError
from ...models import User
from ...schemas import ErrorResponse, TechnicianOverview, UserOut
from ...schemas_technician import AvailabilityUpdate, TechnicianPrivate, TechnicianProfileUpdate
from ...services import technicians as svc
from ..dependencies import get_app_settings, get_db, require_roles

router = APIRouter(
    prefix="/technician",
    tags=["Technician (self-service)"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse, "description": "Not a technician"}},
)
technician_only = require_roles("technician")


def _own_profile(db: Session, user: User):
    profile = svc.get_by_user(db, user.id)
    if profile is None:
        raise ApiError(404, "profile_not_found", "You don't have a technician profile yet. Create one with PUT /api/technician/profile.")
    return profile


@router.get("/overview", response_model=TechnicianOverview, summary="Technician overview")
def technician_overview(user: User = Depends(require_roles("technician", "admin")), db: Session = Depends(get_db)) -> TechnicianOverview:
    from ...services.bookings import assigned_summary  # local import: bookings depends on technicians

    profile = svc.get_by_user(db, user.id)
    jobs = assigned_summary(db, profile.id) if profile else []
    return TechnicianOverview(
        technician=UserOut.model_validate(user, from_attributes=True),
        assigned_jobs=jobs,
        message=(
            "Create your technician profile to start receiving booking requests."
            if profile is None
            else f"Your profile is {svc.verification_label(profile).lower()}. You have {len(jobs)} open booking(s)."
        ),
    )


@router.get("/profile", response_model=TechnicianPrivate, summary="My technician profile", responses={404: {"model": ErrorResponse}})
def get_profile(user: User = Depends(technician_only), db: Session = Depends(get_db)) -> TechnicianPrivate:
    return svc.to_private(_own_profile(db, user))


@router.put(
    "/profile",
    response_model=TechnicianPrivate,
    summary="Create or update my technician profile",
    description="Verification can't be set here. Changing your trade resets verification.",
)
def put_profile(
    payload: TechnicianProfileUpdate,
    user: User = Depends(technician_only),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TechnicianPrivate:
    existing = svc.get_by_user(db, user.id)
    if existing is not None and existing.is_sample:
        raise ApiError(409, "sample_profile", "Demo sample profiles can't be edited.")
    return svc.to_private(svc.upsert_profile(db, user.id, payload, currency=settings.currency))


@router.post("/profile/submit-verification", response_model=TechnicianPrivate, summary="Ask an admin to verify my profile", responses={409: {"model": ErrorResponse}})
def submit_verification(user: User = Depends(technician_only), db: Session = Depends(get_db)) -> TechnicianPrivate:
    return svc.to_private(svc.submit_for_verification(db, _own_profile(db, user)))


@router.patch("/availability", response_model=TechnicianPrivate, summary="Set my availability")
def set_availability(payload: AvailabilityUpdate, user: User = Depends(technician_only), db: Session = Depends(get_db)) -> TechnicianPrivate:
    profile = _own_profile(db, user)
    profile.availability_status = payload.availability_status
    db.commit()
    db.refresh(profile)
    return svc.to_private(profile)
