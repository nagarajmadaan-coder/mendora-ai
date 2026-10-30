"""
Bookings: technician visits and expert consultations (Step 9).

Customers request; the assigned technician accepts or rejects; either side can cancel before the start time;
the technician marks it completed afterwards. Everyone only sees their own bookings (admins see all).
No payment is taken and no live calls are connected — the API says so in every response.
"""

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from ...errors import ApiError
from ...models import User
from ...schemas import ErrorResponse
from ...schemas_payment import EstimateCreate, EstimateDecision
from ...schemas_review import ReviewCreate, ReviewOut
from ...services import reviews as review_svc
from ...schemas_booking import BookingCreate, BookingList, BookingOut, BookingReason, CompletionReport, QuoteOut
from ...services import bookings as svc
from ..dependencies import get_current_user, get_db, require_roles

router = APIRouter(
    prefix="/bookings",
    tags=["Bookings"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
customer_only = require_roles("customer")


@router.post("/quote", response_model=QuoteOut, summary="Preview price, time and safety notes before confirming")
def quote_booking(payload: BookingCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(customer_only)) -> QuoteOut:
    return svc.quote(db, user, payload, request.app.state.settings)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BookingOut, summary="Request a booking")
def create_booking(payload: BookingCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(customer_only)) -> BookingOut:
    limiter = request.app.state.booking_limiter
    if limiter.is_limited(user.id):
        raise ApiError(429, "too_many_bookings", "Too many booking attempts. Please try again later.", headers={"Retry-After": str(limiter.retry_after(user.id))})
    limiter.hit(user.id)
    settings = request.app.state.settings
    booking = svc.create_booking(db, user, payload, settings)
    return svc.to_out(db, booking, "customer", settings)


@router.get("", response_model=BookingList, summary="My bookings (customers) or assigned bookings (technicians)")
def list_bookings(
    request: Request,
    booking_status: str | None = Query(None, alias="status", pattern="^(requested|accepted|rejected|cancelled|completed)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BookingList:
    settings = request.app.state.settings
    rows = svc.list_for_user(db, user, booking_status)
    return BookingList(bookings=[svc.to_out(db, b, role, settings) for b, role in rows], total=len(rows))


@router.get("/{booking_id}", response_model=BookingOut, summary="One booking")
def get_booking(booking_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingOut:
    booking, role = svc.get_for_user(db, booking_id, user)
    return svc.to_out(db, booking, role, request.app.state.settings)


def _act(action: str, booking_id: str, request: Request, db: Session, user: User, reason: str | None = None, report: CompletionReport | None = None) -> BookingOut:
    settings = request.app.state.settings
    booking, role = svc.get_for_user(db, booking_id, user)
    booking = svc.transition(db, booking, role, action, actor=user, settings=settings, reason=reason, report=report)
    return svc.to_out(db, booking, role, settings)


@router.post("/{booking_id}/accept", response_model=BookingOut, summary="Accept (assigned technician)")
def accept(booking_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingOut:
    return _act("accept", booking_id, request, db, user)


@router.post("/{booking_id}/reject", response_model=BookingOut, summary="Reject (assigned technician)")
def reject(booking_id: str, request: Request, payload: BookingReason | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingOut:
    return _act("reject", booking_id, request, db, user, reason=payload.reason if payload else None)


@router.post("/{booking_id}/cancel", response_model=BookingOut, summary="Cancel before the start time")
def cancel(booking_id: str, request: Request, payload: BookingReason | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingOut:
    return _act("cancel", booking_id, request, db, user, reason=payload.reason if payload else None)


@router.post(
    "/{booking_id}/complete",
    response_model=BookingOut,
    summary="Mark completed (assigned technician, after the start time)",
    description="Optionally record the confirmed cause. It's saved as an UNVERIFIED repair case until an admin checks it.",
)
def complete(booking_id: str, request: Request, payload: CompletionReport | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingOut:
    return _act("complete", booking_id, request, db, user, report=payload)


@router.post(
    "/{booking_id}/review",
    status_code=status.HTTP_201_CREATED,
    response_model=ReviewOut,
    summary="Review the technician (your own COMPLETED booking, once)",
)
def review_booking(booking_id: str, payload: ReviewCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ReviewOut:
    return review_svc.create(db, user, booking_id, payload)


@router.post("/{booking_id}/estimate", response_model=BookingOut, summary="Send an estimate (assigned technician, accepted & unpaid booking)")
def propose_estimate(booking_id: str, payload: EstimateCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingOut:
    settings = request.app.state.settings
    booking, role = svc.get_for_user(db, booking_id, user)
    return svc.to_out(db, svc.propose_estimate(db, booking, role, payload, settings), role, settings)


@router.post("/{booking_id}/estimate/approve", response_model=BookingOut, summary="Approve the technician's estimate (customer)")
def approve_estimate(booking_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingOut:
    settings = request.app.state.settings
    booking, role = svc.get_for_user(db, booking_id, user)
    return svc.to_out(db, svc.decide_estimate(db, booking, role, True, None), role, settings)


@router.post("/{booking_id}/estimate/decline", response_model=BookingOut, summary="Decline the technician's estimate (customer)")
def decline_estimate(booking_id: str, request: Request, payload: EstimateDecision | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingOut:
    settings = request.app.state.settings
    booking, role = svc.get_for_user(db, booking_id, user)
    return svc.to_out(db, svc.decide_estimate(db, booking, role, False, payload.reason if payload else None), role, settings)
