"""
SANDBOX payments (Step 10). No real money, no card details — every response says so.

POST /api/bookings/{id}/payments   pay for your accepted booking (simulated outcome)
GET  /api/bookings/{id}/payments   payment attempts for your booking
GET  /api/payments                 your payments (admins: all)
GET  /api/payments/{id}            one payment
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import ApiError
from ...models import Payment, User
from ...payments import service as svc
from ...schemas import ErrorResponse
from ...schemas_payment import PaymentCreate, PaymentList, PaymentOut, PaymentResult
from ...services import bookings as booking_svc
from ..dependencies import get_current_user, get_db

router = APIRouter(
    tags=["Payments (sandbox)"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)


@router.post(
    "/bookings/{booking_id}/payments",
    status_code=status.HTTP_201_CREATED,
    response_model=PaymentResult,
    summary="Pay for a booking (SANDBOX — simulated, no real money)",
    description=(
        "Customer only, for their own ACCEPTED (or completed) booking. The amount charged is the booking's stored price; "
        "`expected_amount` must match it. A declined simulated card is returned as a payment with status `failed` "
        "(HTTP 201) — the booking stays unpaid. Re-sending the same `idempotency_key` returns the earlier result (HTTP 200)."
    ),
)
def create_payment(
    booking_id: str,
    payload: PaymentCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaymentResult:
    limiter = request.app.state.payment_limiter
    if limiter.is_limited(user.id):
        raise ApiError(429, "too_many_payment_attempts", "Too many payment attempts. Please wait and try again.", headers={"Retry-After": str(limiter.retry_after(user.id))})
    limiter.hit(user.id)
    result, created = svc.pay(db, user, booking_id, payload, request.app.state.settings)
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/bookings/{booking_id}/payments", response_model=PaymentList, summary="Payment attempts for a booking")
def booking_payments(booking_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> PaymentList:
    booking, role = booking_svc.get_for_user(db, booking_id, user)  # 404 unless you're involved
    if role not in ("customer", "admin"):
        raise ApiError(403, "forbidden", "Payment records are only visible to the customer who made the booking.")
    rows = svc.payments_for_booking(db, booking.id)
    return PaymentList(payments=[svc.to_out(p) for p in rows], total=len(rows))


@router.get("/payments", response_model=PaymentList, summary="My payments (admins: all)")
def my_payments(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> PaymentList:
    query = select(Payment).order_by(Payment.created_at.desc())
    if user.role != "admin":
        query = query.where(Payment.customer_id == user.id)
    rows = db.scalars(query.limit(200)).all()
    return PaymentList(payments=[svc.to_out(p) for p in rows], total=len(rows))


@router.get("/payments/{payment_id}", response_model=PaymentOut, summary="One payment")
def get_payment(payment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> PaymentOut:
    return svc.to_out(svc.visible_payment(db, user, payment_id))
