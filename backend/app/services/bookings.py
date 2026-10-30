"""
Bookings and expert consultations (Step 9).

Rules enforced here (and by the database):
  * Only customers book, only for THEIR OWN repair requests, only with bookable technicians
    (admin-verified, or labelled samples in demo mode) of the same trade.
  * Safety comes first: the request's safety is re-checked; high-risk requests need an explicit
    acknowledgement that the person is safe — a booking never makes a dangerous case "safe".
  * Times: in the future (with notice), within working hours in the service timezone, on :00/:30.
  * No double-booking: each booking reserves 30-minute slot rows protected by a UNIQUE constraint,
    so even simultaneous requests can't both succeed.
  * Status changes follow STATUS_RULES; anything else is refused.
  * Privacy: technicians see the customer's first name and area; the address only after accepting.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ApiError
from ..models import ACTIVE_BOOKING_STATUSES, Booking, BookingSlot, Notification, RepairRequest, TechnicianProfile, User
from ..schemas_booking import (
    NO_CALLS_NOTE,
    NO_PAYMENT_NOTE,
    BookingCreate,
    BookingOut,
    CompletionReport,
    HistoryItem,
    QuoteOut,
    RequestSummary,
    Slot,
    TechnicianSummary,
)
from ..schemas_knowledge import RepairCaseCreate
from ..payments import service as payment_svc
from . import pricing
from .cases import create_case
from .safety_workflow import refresh_safety
from .technicians import is_publicly_visible, verification_label

SLOT_MINUTES = 30
DURATION = {"technician_visit": 120, "expert_consultation": 30}
TYPE_LABEL = {"technician_visit": "technician visit", "expert_consultation": "expert consultation"}

# action -> (allowed from-statuses, new status, who may do it)
STATUS_RULES: dict[str, tuple[tuple[str, ...], str, tuple[str, ...]]] = {
    "accept": (("requested",), "accepted", ("technician", "admin")),
    "reject": (("requested",), "rejected", ("technician", "admin")),
    "cancel": (("requested", "accepted"), "cancelled", ("customer", "technician", "admin")),
    "complete": (("accepted",), "completed", ("technician", "admin")),
}


# ---------- time helpers ----------


def utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; everything here is UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def slot_key(dt: datetime) -> str:
    return utc(dt).strftime("%Y-%m-%dT%H:%MZ")


def slot_keys(start: datetime, minutes: int) -> list[str]:
    return [slot_key(start + timedelta(minutes=i)) for i in range(0, minutes, SLOT_MINUTES)]


def local_label(start: datetime, end: datetime, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    s, e = utc(start).astimezone(tz), utc(end).astimezone(tz)
    return f"{s:%a} {s.day} {s:%b %Y}, {s:%H:%M}–{e:%H:%M} ({tz_name})"


def validate_start(start: datetime, booking_type: str, settings: Settings) -> datetime:
    start = utc(start)
    if start.second or start.microsecond or start.minute % SLOT_MINUTES:
        raise ApiError(422, "invalid_time", "Choose a start time on the hour or half hour (e.g. 10:00 or 10:30).")
    now = now_utc()
    if start < now + timedelta(minutes=settings.booking_min_notice_minutes):
        raise ApiError(422, "invalid_time", f"Choose a time at least {settings.booking_min_notice_minutes} minutes from now.")
    if start > now + timedelta(days=settings.booking_max_days_ahead):
        raise ApiError(422, "invalid_time", f"Bookings can be made up to {settings.booking_max_days_ahead} days ahead.")
    tz = ZoneInfo(settings.timezone)
    local_start = start.astimezone(tz)
    local_end = (start + timedelta(minutes=DURATION[booking_type])).astimezone(tz)
    start_minutes = local_start.hour * 60 + local_start.minute
    end_minutes = local_end.hour * 60 + local_end.minute if local_end.date() == local_start.date() else 24 * 60 + 1
    if start_minutes < settings.working_hours_start * 60 or end_minutes > settings.working_hours_end * 60:
        raise ApiError(
            422,
            "invalid_time",
            f"Choose a time within working hours ({settings.working_hours_start:02d}:00–{settings.working_hours_end:02d}:00 "
            f"{settings.timezone}). A {TYPE_LABEL[booking_type]} lasts {DURATION[booking_type]} minutes.",
        )
    return start


def occupied_keys(db: Session, technician_id: str) -> set[str]:
    return set(db.scalars(select(BookingSlot.slot_start).where(BookingSlot.technician_id == technician_id)).all())


def free_slots_for_day(db: Session, profile: TechnicianProfile, day: date, booking_type: str, settings: Settings) -> list[Slot]:
    tz = ZoneInfo(settings.timezone)
    occupied = occupied_keys(db, profile.id)
    minutes = DURATION[booking_type]
    out: list[Slot] = []
    t = datetime(day.year, day.month, day.day, settings.working_hours_start, tzinfo=tz)
    last = datetime(day.year, day.month, day.day, 0, tzinfo=tz) + timedelta(hours=settings.working_hours_end, minutes=-minutes)
    while t <= last:
        try:
            start = validate_start(t, booking_type, settings)
        except ApiError:
            t += timedelta(minutes=SLOT_MINUTES)
            continue
        if not occupied.intersection(slot_keys(start, minutes)):
            end = start + timedelta(minutes=minutes)
            out.append(Slot(start=start, end=end, local_time=f"{start.astimezone(tz):%H:%M}–{end.astimezone(tz):%H:%M}"))
        t += timedelta(minutes=SLOT_MINUTES)
    return out


def next_free_slot(db: Session, profile: TechnicianProfile, booking_type: str, settings: Settings, days: int = 14) -> Slot | None:
    today = now_utc().astimezone(ZoneInfo(settings.timezone)).date()
    for offset in range(days + 1):
        slots = free_slots_for_day(db, profile, today + timedelta(days=offset), booking_type, settings)
        if slots:
            return slots[0]
    return None


# ---------- lookups & permissions ----------


def bookable_profile(db: Session, technician_id: str, settings: Settings) -> TechnicianProfile:
    profile = db.get(TechnicianProfile, technician_id)
    if profile is None or not is_publicly_visible(profile, settings.demo_mode_enabled):
        raise ApiError(404, "technician_not_found", "This technician isn't available for booking (not found or not verified).")
    if profile.availability_status == "unavailable":
        raise ApiError(409, "technician_unavailable", "This technician isn't taking new requests right now.")
    return profile


def role_in(booking: Booking, user: User, db: Session) -> str | None:
    """customer / technician / admin if this user may see the booking, else None."""
    if user.role == "admin":
        return "admin"
    if user.role == "customer" and booking.customer_id == user.id:
        return "customer"
    if user.role == "technician":
        profile = db.get(TechnicianProfile, booking.technician_id)
        if profile is not None and profile.user_id == user.id:
            return "technician"
    return None


def get_for_user(db: Session, booking_id: str, user: User) -> tuple[Booking, str]:
    booking = db.get(Booking, booking_id)
    role = role_in(booking, user, db) if booking else None
    if booking is None or role is None:
        raise ApiError(404, "booking_not_found", f"No booking found with ID '{booking_id}'.")
    return booking, role


# ---------- notifications ----------


def notify(db: Session, user_id: str, booking: Booking, kind: str, message: str) -> None:
    db.add(Notification(recipient_user_id=user_id, booking_id=booking.id, kind=kind, message=message))


# ---------- create / quote ----------


def _prepare(db: Session, user: User, data: BookingCreate, settings: Settings):
    if user.role != "customer":
        raise ApiError(403, "forbidden", "Only customer accounts can request bookings.")
    record = db.get(RepairRequest, data.repair_request_id)
    if record is None or record.customer_id != user.id:
        raise ApiError(404, "repair_request_not_found", "Choose one of your own saved repair requests.")
    profile = bookable_profile(db, data.technician_id, settings)
    if profile.trade != record.trade:
        raise ApiError(422, "trade_mismatch", f"This technician works in {profile.trade}, but your request is for {record.trade}.")
    if data.booking_type == "technician_visit":
        if data.service_area not in (profile.service_areas or []):
            raise ApiError(422, "area_not_covered", f"This technician doesn't cover '{data.service_area}'. Covered: {', '.join(profile.service_areas or [])}.")
        price = profile.visit_rate
    else:
        if profile.consultation_rate is None:
            raise ApiError(422, "consultation_not_offered", "This technician doesn't offer expert consultations.")
        price = profile.consultation_rate

    safety = refresh_safety(db, record)  # never trust an old result

    minutes = DURATION[data.booking_type]
    if data.next_available:
        slot = next_free_slot(db, profile, data.booking_type, settings)
        if slot is None:
            raise ApiError(409, "no_slots_available", "This expert has no free consultation slots in the next 14 days.")
        start = slot.start
    else:
        start = validate_start(data.scheduled_start, data.booking_type, settings)  # type: ignore[arg-type]
    end = start + timedelta(minutes=minutes)
    return record, profile, safety, start, end, minutes, price


def _tech_summary(profile: TechnicianProfile) -> TechnicianSummary:
    from .technicians import SAMPLE_NOTICE

    return TechnicianSummary(
        id=profile.id,
        display_name=profile.display_name,
        trade=profile.trade,
        is_sample=profile.is_sample,
        sample_notice=SAMPLE_NOTICE if profile.is_sample else None,
        verification_label=verification_label(profile),
    )


def quote(db: Session, user: User, data: BookingCreate, settings: Settings) -> QuoteOut:
    record, profile, safety, start, end, minutes, price = _prepare(db, user, data, settings)
    high = safety.risk_level == "high"
    notes = [NO_PAYMENT_NOTE, "Nothing is paid now. Once the technician accepts, you can pay in the sandbox from the booking page."]
    if data.booking_type == "expert_consultation":
        notes.append(NO_CALLS_NOTE)
    if profile.is_sample:
        notes.append("This is a demo sample technician — no real person will respond.")
    return QuoteOut(
        technician=_tech_summary(profile),
        booking_type=data.booking_type,
        scheduled_start=start,
        scheduled_end=end,
        local_time_label=local_label(start, end, settings.timezone),
        duration_minutes=minutes,
        price_amount=price,
        price_currency=profile.currency,
        price_note=NO_PAYMENT_NOTE if price is not None else "Price to be confirmed by the technician. " + NO_PAYMENT_NOTE,
        safety_risk_level=safety.risk_level,
        requires_safety_acknowledgement=high,
        safety_message=f"{safety.safety_message} {safety.recommended_action}" if high else None,
        emergency_steps=safety.emergency_steps if high else [],
        notes=notes,
    )


def create_booking(db: Session, user: User, data: BookingCreate, settings: Settings) -> Booking:
    record, profile, safety, start, end, minutes, price = _prepare(db, user, data, settings)

    if safety.risk_level == "high" and not data.safety_acknowledged:
        raise ApiError(
            409,
            "safety_acknowledgement_required",
            "This request is high risk. Make sure you are safe first: " + safety.recommended_action
            + " Then confirm you are safe and understand MENDORA is not an emergency service (safety_acknowledged = true).",
        )

    duplicate = db.scalar(
        select(Booking.id).where(
            Booking.customer_id == user.id,
            Booking.repair_request_id == record.id,
            Booking.booking_type == data.booking_type,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
    )
    if duplicate:
        raise ApiError(409, "duplicate_booking", "You already have an open booking of this type for this repair request.")

    booking = Booking(
        customer_id=user.id,
        technician_id=profile.id,
        repair_request_id=record.id,
        booking_type=data.booking_type,
        scheduled_start=start,
        scheduled_end=end,
        duration_minutes=minutes,
        service_area=data.service_area if data.booking_type == "technician_visit" else None,
        service_address=data.service_address if data.booking_type == "technician_visit" else None,
        customer_note=data.customer_note,
        status="requested",
        history=[{"status": "requested", "at": now_utc().isoformat(), "by": "customer", "reason": None}],
        price_amount=price,
        price_currency=profile.currency,
        safety_risk_level=safety.risk_level,
        safety_acknowledged=data.safety_acknowledged and safety.risk_level == "high",
        technician_is_sample=profile.is_sample,
    )
    db.add(booking)
    db.flush()
    for key in slot_keys(start, minutes):
        db.add(BookingSlot(technician_id=profile.id, slot_start=key, booking_id=booking.id))
    label = local_label(start, end, settings.timezone)
    notify(db, profile.user_id, booking, "booking_requested", f"New {TYPE_LABEL[data.booking_type]} request for {label}.")
    notify(db, user.id, booking, "booking_requested", f"Your {TYPE_LABEL[data.booking_type]} request was sent to {profile.display_name} for {label}.")
    try:
        db.commit()
    except IntegrityError as exc:  # another booking took this time at the same moment
        db.rollback()
        raise ApiError(409, "time_slot_unavailable", "That time was just booked by someone else. Please choose another time.") from exc
    db.refresh(booking)
    return booking


# ---------- status changes ----------


def transition(
    db: Session,
    booking: Booking,
    role: str,
    action: str,
    *,
    actor: User,
    settings: Settings,
    reason: str | None = None,
    report: CompletionReport | None = None,
) -> Booking:
    allowed_from, new_status, allowed_roles = STATUS_RULES[action]
    if role not in allowed_roles:
        raise ApiError(403, "forbidden", f"You can't {action} this booking.")
    if booking.status not in allowed_from:
        raise ApiError(
            409,
            "invalid_status_transition",
            f"A {booking.status} booking can't be {new_status}. Allowed from: {', '.join(allowed_from)}.",
        )
    now = now_utc()
    if action == "cancel" and utc(booking.scheduled_start) <= now:
        raise ApiError(409, "invalid_status_transition", "This booking has already started, so it can't be cancelled.")
    if action == "complete" and utc(booking.scheduled_start) > now:
        raise ApiError(409, "invalid_status_transition", "A booking can only be completed after its start time.")
    if action == "accept":
        profile = db.get(TechnicianProfile, booking.technician_id)
        if profile is not None and not profile.is_sample and profile.verification_status != "verified":
            raise ApiError(409, "technician_not_verified", "Your profile must be verified before you can accept bookings.")

    booking.status = new_status
    booking.status_reason = reason
    booking.history = [*(booking.history or []), {"status": new_status, "at": now.isoformat(), "by": role, "reason": reason}]
    if new_status in ("rejected", "cancelled"):
        for slot in db.scalars(select(BookingSlot).where(BookingSlot.booking_id == booking.id)).all():
            db.delete(slot)  # free the time again
        payment_svc.refund_for_cancelled_booking(db, booking, settings)  # a paid booking gets its (sandbox) money back

    profile = db.get(TechnicianProfile, booking.technician_id)
    label = local_label(booking.scheduled_start, booking.scheduled_end, settings.timezone)
    kind_text = TYPE_LABEL[booking.booking_type]
    reason_text = f" Reason: {reason}" if reason else ""
    if role in ("technician", "admin"):
        notify(db, booking.customer_id, booking, f"booking_{new_status}", f"Your {kind_text} for {label} was {new_status}.{reason_text}")
    if role in ("customer", "admin") and profile is not None:
        notify(db, profile.user_id, booking, f"booking_{new_status}", f"The {kind_text} for {label} was {new_status} by the {role}.{reason_text}")

    if action == "complete":
        payment_svc.release_for_completed_booking(db, booking)  # sandbox escrow → technician
    if action == "complete" and report is not None and report.confirmed_cause:
        record = db.get(RepairRequest, booking.repair_request_id)
        db.flush()
        create_case(
            db,
            RepairCaseCreate(
                trade=record.trade if record else (profile.trade if profile else "plumbing"),  # type: ignore[arg-type]
                category=None,
                symptoms=(record.description if record else "Not recorded")[:1000].ljust(10),
                clarifying_qa=[],
                confirmed_cause=report.confirmed_cause,
                cause_source="technician_confirmed",
                parts_used=report.parts_used,
                completion_minutes=report.completion_minutes,
                cost_amount=report.cost_amount,
                repair_request_id=booking.repair_request_id,
            ),
            created_by=actor.id,
            currency=settings.currency,
            booking_id=booking.id,
            technician_profile_id=booking.technician_id,
        )  # commits; the case starts UNVERIFIED until an admin checks it
    db.commit()
    db.refresh(booking)
    return booking


def allowed_actions(booking: Booking, role: str) -> list[str]:
    now = now_utc()
    actions = []
    for action, (from_statuses, _new, roles) in STATUS_RULES.items():
        if role not in roles or booking.status not in from_statuses:
            continue
        if action == "cancel" and utc(booking.scheduled_start) <= now:
            continue
        if action == "complete" and utc(booking.scheduled_start) > now:
            continue
        actions.append(action)
    return actions


# ---------- output ----------


def to_out(db: Session, booking: Booking, role: str, settings: Settings) -> BookingOut:
    profile = db.get(TechnicianProfile, booking.technician_id)
    record = db.get(RepairRequest, booking.repair_request_id)
    customer = db.get(User, booking.customer_id)
    show_address = role in ("customer", "admin") or booking.status in ("accepted", "completed")
    address_note = None
    if booking.booking_type == "technician_visit" and not show_address:
        address_note = "The address is shared with you once you accept the booking."
    first_name = (customer.full_name.split() or ["Customer"])[0] if customer else "Customer"
    return BookingOut(
        id=booking.id,
        booking_type=booking.booking_type,  # type: ignore[arg-type]
        status=booking.status,  # type: ignore[arg-type]
        status_reason=booking.status_reason,
        scheduled_start=utc(booking.scheduled_start),
        scheduled_end=utc(booking.scheduled_end),
        duration_minutes=booking.duration_minutes,
        local_time_label=local_label(booking.scheduled_start, booking.scheduled_end, settings.timezone),
        timezone=settings.timezone,
        technician=_tech_summary(profile) if profile else TechnicianSummary(id=booking.technician_id, display_name="(removed)", trade="", is_sample=False, sample_notice=None, verification_label=""),
        repair_request=RequestSummary(
            id=booking.repair_request_id,
            trade=record.trade if record else "",
            description=record.description if record else "",
            risk_level=(record.risk_level or booking.safety_risk_level) if record else booking.safety_risk_level,
        ),
        customer_display_name=first_name,
        service_area=booking.service_area,
        service_address=booking.service_address if show_address else None,
        address_note=address_note,
        customer_note=booking.customer_note,
        price_amount=booking.price_amount,
        price_currency=booking.price_currency,
        price_note=NO_PAYMENT_NOTE if booking.price_amount is not None else "Price to be confirmed by the technician. " + NO_PAYMENT_NOTE,
        safety_risk_level=booking.safety_risk_level,
        safety_acknowledged=booking.safety_acknowledged,
        history=[HistoryItem(**h) for h in (booking.history or [])],
        allowed_actions=allowed_actions(booking, role),
        consultation_note=NO_CALLS_NOTE if booking.booking_type == "expert_consultation" else None,
        payment=payment_svc.summary(db, booking, role, settings),
        price_breakdown=pricing.breakdown(booking, settings.platform_commission_percent),
        estimate_actions=_estimate_actions(db, booking, role),
        review=_review_out(db, booking),
        can_review=role == "customer" and booking.status == "completed" and _review_out(db, booking) is None,
        created_at=utc(booking.created_at),
        updated_at=utc(booking.updated_at),
    )


# ---------- technician estimate (merged feature) ----------


def _estimate_actions(db: Session, booking: Booking, role: str) -> list[str]:
    if booking.status not in ("accepted",) or payment_svc.booking_payment_status(db, booking) in ("paid", "refunded"):
        return []
    if role in ("technician", "admin") and booking.estimate_status != "approved":
        return ["propose"]
    if role == "customer" and booking.estimate_status == "proposed":
        return ["approve", "decline"]
    return []


def propose_estimate(db: Session, booking: Booking, role: str, data, settings: Settings) -> Booking:
    if "propose" not in _estimate_actions(db, booking, role):
        if role not in ("technician", "admin"):
            raise ApiError(403, "forbidden", "Only the assigned technician can send an estimate.")
        raise ApiError(409, "estimate_not_allowed", "An estimate can be sent only for an accepted, unpaid booking without an approved estimate.")
    booking.estimate_labour = data.labour
    booking.estimate_materials = data.materials
    booking.estimate_note = data.note.strip() if data.note and data.note.strip() else None
    booking.estimate_status = "proposed"
    booking.estimate_updated_at = now_utc()
    total = (booking.price_amount or 0) + data.labour + data.materials
    notify(db, booking.customer_id, booking, "estimate_proposed",
           f"Your technician sent an estimate: {booking.price_currency} {total} in total. Please review it before paying.")
    db.commit()
    db.refresh(booking)
    return booking


def decide_estimate(db: Session, booking: Booking, role: str, approve: bool, reason: str | None) -> Booking:
    if ("approve" if approve else "decline") not in _estimate_actions(db, booking, role):
        if role != "customer":
            raise ApiError(403, "forbidden", "Only the customer can approve or decline the estimate.")
        raise ApiError(409, "estimate_not_allowed", "There's no estimate waiting for your decision.")
    booking.estimate_status = "approved" if approve else "declined"
    booking.estimate_updated_at = now_utc()
    profile = db.get(TechnicianProfile, booking.technician_id)
    if profile is not None:
        word = "approved" if approve else "declined"
        notify(db, profile.user_id, booking, f"estimate_{word}", f"The customer {word} your estimate." + (f" Reason: {reason}" if reason else ""))
    db.commit()
    db.refresh(booking)
    return booking


def _review_out(db: Session, booking: Booking):
    from . import reviews  # local import: reviews uses helpers from this module

    r = reviews.for_booking(db, booking.id)
    return reviews.to_out(r, booking.booking_type) if r else None


def list_for_user(db: Session, user: User, status: str | None = None) -> list[tuple[Booking, str]]:
    query = select(Booking)
    if user.role == "customer":
        query = query.where(Booking.customer_id == user.id)
        role = "customer"
    elif user.role == "technician":
        profile = db.scalar(select(TechnicianProfile).where(TechnicianProfile.user_id == user.id))
        if profile is None:
            return []
        query = query.where(Booking.technician_id == profile.id)
        role = "technician"
    else:
        role = "admin"
    if status:
        query = query.where(Booking.status == status)
    rows = db.scalars(query.order_by(Booking.scheduled_start.desc())).all()
    return [(b, role) for b in rows]


def assigned_summary(db: Session, technician_profile_id: str) -> list[dict]:
    rows = db.scalars(
        select(Booking).where(Booking.technician_id == technician_profile_id, Booking.status.in_(ACTIVE_BOOKING_STATUSES)).order_by(Booking.scheduled_start)
    ).all()
    return [{"booking_id": b.id, "booking_type": b.booking_type, "status": b.status, "scheduled_start": utc(b.scheduled_start).isoformat()} for b in rows]
