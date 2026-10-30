"""
Sandbox payment rules (Step 10).

  * Only the customer who owns a booking can pay for it or see its payment records (admins can see them too).
  * Payable only once the technician has ACCEPTED (or completed) the booking, and only if it has a stored price.
  * The amount always comes from the booking's stored price. The client's `expected_amount` is only a check:
    if it differs, nothing is charged.
  * Duplicates: the same idempotency key returns the earlier result; a second success for the same booking
    is impossible (partial unique index), even with simultaneous requests.
  * A failed attempt never marks the booking paid.
  * Cancelling a paid booking refunds the (simulated) payment.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ApiError
from ..models import Booking, Notification, Payment, TechnicianProfile, User
from ..schemas_payment import BookingPayment, PaymentCreate, PaymentOut, PaymentResult
from ..services.pricing import payable_amount
from .providers import get_provider

log = logging.getLogger("mendora.payments")
PAYABLE_BOOKING_STATUSES = ("accepted", "completed")


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def to_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        booking_id=p.booking_id,
        amount=p.amount,
        currency=p.currency,
        status=p.status,  # type: ignore[arg-type]
        method_type=p.method_type,
        provider=p.provider,
        sandbox=p.provider == "sandbox",
        transaction_ref=p.transaction_ref,
        failure_code=p.failure_code,
        failure_message=p.failure_message,
        refund_ref=p.refund_ref,
        refunded_at=_utc(p.refunded_at),
        payout_status=p.payout_status,  # type: ignore[arg-type]
        released_at=_utc(p.released_at),
        created_at=_utc(p.created_at),  # type: ignore[arg-type]
        updated_at=_utc(p.updated_at),  # type: ignore[arg-type]
    )


def payments_for_booking(db: Session, booking_id: str) -> list[Payment]:
    return list(db.scalars(select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.created_at.desc())).all())


def booking_payment_status(db: Session, booking: Booking) -> str:
    rows = payments_for_booking(db, booking.id)
    if any(p.status == "succeeded" for p in rows):
        return "paid"
    if any(p.status == "refunded" for p in rows):
        return "refunded"
    if booking.status in PAYABLE_BOOKING_STATUSES and (booking.price_amount is not None or booking.estimate_status):
        return "unpaid"
    return "not_payable"


def _not_payable_reason(booking: Booking, settings: Settings) -> str | None:
    if get_provider(settings.payment_provider) is None:
        return "Payments are switched off on this server."
    if booking.status == "requested":
        return "You can pay once the technician accepts the booking."
    if booking.status not in PAYABLE_BOOKING_STATUSES:
        return f"A {booking.status} booking can't be paid."
    if booking.estimate_status == "proposed":
        return "The technician sent an estimate. Review and approve it before paying."
    if booking.estimate_status == "declined":
        return "You declined the estimate. The technician can send a new one, or you can cancel the booking."
    if payable_amount(booking) is None:
        return "The technician hasn't set a price yet."
    return None


def summary(db: Session, booking: Booking, role: str, settings: Settings) -> BookingPayment:
    status = booking_payment_status(db, booking)
    reason = None if status in ("paid", "refunded") else _not_payable_reason(booking, settings)
    rows = payments_for_booking(db, booking.id)
    latest = to_out(rows[0]) if rows and role in ("customer", "admin") else None
    settled = next((p for p in rows if p.status in ("succeeded", "refunded")), None)
    payout = settled.payout_status if settled else None
    payout_note = {
        "held": "Held in sandbox escrow. It is released to the technician when the job is marked completed.",
        "released": "Released to the technician after the job was completed (simulated).",
        "returned": "Returned to the customer (simulated refund).",
    }.get(payout or "")
    return BookingPayment(
        status=status,  # type: ignore[arg-type]
        can_pay=role == "customer" and status == "unpaid" and reason is None,
        amount=settled.amount if settled else payable_amount(booking),
        currency=booking.price_currency,
        reason=reason,
        latest=latest,
        payout_status=payout,  # type: ignore[arg-type]
        payout_note=payout_note,
    )


def _notify(db: Session, user_id: str, booking: Booking, kind: str, message: str) -> None:
    db.add(Notification(recipient_user_id=user_id, booking_id=booking.id, kind=kind, message=message))


def pay(db: Session, user: User, booking_id: str, data: PaymentCreate, settings: Settings) -> tuple[PaymentResult, bool]:
    """Returns (result, created). created=False when an earlier attempt with the same key is replayed."""
    if user.role != "customer":
        raise ApiError(403, "forbidden", "Only the customer who made the booking can pay for it.")
    booking = db.get(Booking, booking_id)
    if booking is None or booking.customer_id != user.id:
        raise ApiError(404, "booking_not_found", f"No booking found with ID '{booking_id}'.")

    # Same attempt sent again (double click, network retry): return what happened, never charge again.
    earlier = db.scalar(select(Payment).where(Payment.customer_id == user.id, Payment.idempotency_key == data.idempotency_key))
    if earlier is not None:
        if earlier.booking_id != booking.id:
            raise ApiError(409, "idempotency_key_reused", "This payment key was already used for a different booking. Start a new attempt.")
        return _result(db, booking, earlier, replayed=True), False

    provider = get_provider(settings.payment_provider)
    reason = _not_payable_reason(booking, settings)
    if reason:
        raise ApiError(409, "booking_not_payable", reason)
    if booking_payment_status(db, booking) == "paid":
        raise ApiError(409, "already_paid", "This booking has already been paid. You haven't been charged again.")
    amount, currency = payable_amount(booking), booking.price_currency
    if amount is None:
        raise ApiError(409, "booking_not_payable", "There's no price to pay yet.")
    if data.expected_amount != amount or data.currency.upper() != currency:
        raise ApiError(
            409,
            "amount_mismatch",
            f"The amount doesn't match this booking's price ({currency} {amount}). Nothing was charged — please review and try again.",
        )

    payment = Payment(
        booking_id=booking.id,
        customer_id=user.id,
        amount=amount,
        currency=currency,
        status="pending",
        method_type="sandbox",
        provider=provider.name,  # type: ignore[union-attr]
        idempotency_key=data.idempotency_key,
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:  # the same key arrived twice at the same moment
        db.rollback()
        earlier = db.scalar(select(Payment).where(Payment.customer_id == user.id, Payment.idempotency_key == data.idempotency_key))
        if earlier is None:
            raise
        return _result(db, booking, earlier, replayed=True), False

    result = provider.charge(amount=amount, currency=currency, reference=payment.id, scenario=data.scenario)  # type: ignore[union-attr]
    payment.transaction_ref = result.transaction_ref
    if not result.succeeded:
        payment.status = "failed"
        payment.failure_code = result.failure_code
        payment.failure_message = result.failure_message
        db.commit()
        return _result(db, booking, payment), True

    payment.status = "succeeded"
    payment.payout_status = "released" if booking.status == "completed" else "held"
    if payment.payout_status == "released":
        payment.released_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        # Another attempt for this booking succeeded a moment earlier. Record this one as failed and
        # reverse the simulated charge, so the customer is never charged twice.
        db.rollback()
        payment = db.get(Payment, payment.id)
        provider.refund(transaction_ref=result.transaction_ref or "", amount=amount, currency=currency)  # type: ignore[union-attr]
        payment.status = "failed"
        payment.failure_code = "duplicate_prevented"
        payment.failure_message = "This booking was already paid by another attempt. This attempt was not charged."
        db.commit()
        raise ApiError(409, "already_paid", "This booking has already been paid. You haven't been charged again.")

    profile = db.get(TechnicianProfile, booking.technician_id)
    _notify(db, user.id, booking, "payment_succeeded", f"Sandbox payment of {currency} {amount} succeeded (simulated — no real money).")
    if profile is not None:
        _notify(db, profile.user_id, booking, "payment_succeeded", f"The customer completed a sandbox payment of {currency} {amount} (simulated).")
    db.commit()
    log.info("Sandbox payment succeeded for booking %s", booking.id)
    return _result(db, booking, payment), True


def _result(db: Session, booking: Booking, payment: Payment, *, replayed: bool = False) -> PaymentResult:
    messages = {
        "succeeded": "Payment succeeded (sandbox — no real money was taken).",
        "failed": (payment.failure_message or "The payment failed.") + " The booking is not marked as paid.",
        "pending": "The payment is still being processed.",
        "refunded": "This payment was refunded (sandbox).",
    }
    message = messages[payment.status]
    if replayed:
        message = "This attempt was already processed — showing its result. " + message
    return PaymentResult(payment=to_out(payment), booking_payment_status=booking_payment_status(db, booking), replayed=replayed, message=message)  # type: ignore[arg-type]


def refund_for_cancelled_booking(db: Session, booking: Booking, settings: Settings) -> Payment | None:
    """Called when a booking is cancelled. Refunds a succeeded sandbox payment. The caller commits."""
    paid = db.scalar(select(Payment).where(Payment.booking_id == booking.id, Payment.status == "succeeded"))
    if paid is None:
        return None
    provider = get_provider(paid.provider) or get_provider("sandbox")
    result = provider.refund(transaction_ref=paid.transaction_ref or "", amount=paid.amount, currency=paid.currency)  # type: ignore[union-attr]
    if result.succeeded:
        paid.status = "refunded"
        paid.payout_status = "returned"
        paid.refund_ref = result.refund_ref
        paid.refunded_at = datetime.now(timezone.utc)
        _notify(db, booking.customer_id, booking, "payment_refunded", f"Your sandbox payment of {paid.currency} {paid.amount} was refunded (simulated).")
    return paid


def visible_payment(db: Session, user: User, payment_id: str) -> Payment:
    p = db.get(Payment, payment_id)
    if p is None or (user.role != "admin" and p.customer_id != user.id):
        raise ApiError(404, "payment_not_found", f"No payment found with ID '{payment_id}'.")
    return p


def release_for_completed_booking(db: Session, booking: Booking) -> Payment | None:
    """Called when a booking is completed: a held (sandbox) payment is released to the technician. The caller commits."""
    paid = db.scalar(select(Payment).where(Payment.booking_id == booking.id, Payment.status == "succeeded"))
    if paid is None or paid.payout_status != "held":
        return None
    paid.payout_status = "released"
    paid.released_at = datetime.now(timezone.utc)
    profile = db.get(TechnicianProfile, booking.technician_id)
    if profile is not None:
        _notify(db, profile.user_id, booking, "payout_released", f"The sandbox payment of {paid.currency} {paid.amount} was released to you (simulated).")
    return paid
