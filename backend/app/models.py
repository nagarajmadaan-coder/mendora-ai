"""
Database tables.

users            — accounts (customer / technician / admin). Passwords are stored ONLY as Argon2 hashes.
repair_requests  — what a user reported, plus the latest successful AI diagnosis (JSON) when available.
(Steps 7–9 add knowledge cases, technician profiles, bookings, slots and notifications; Step 10 adds payments.)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ROLES = ("customer", "technician", "admin")


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # stored lower-case
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repair_requests: Mapped[list["RepairRequest"]] = relationship(back_populates="customer")


class RepairRequest(Base):
    __tablename__ = "repair_requests"
    __table_args__ = (Index("ix_repair_requests_customer_created", "customer_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # NULL for requests made without signing in (allowed, as in Step 3).
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    trade: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    # "accepted" = received, "diagnosed" = has a stored diagnosis result
    status: Mapped[str] = mapped_column(String(20), default="accepted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # ---- Diagnosis ----
    # "not_started" | "completed" | "failed"
    diagnosis_status: Mapped[str] = mapped_column(String(20), default="not_started")
    diagnosis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # latest successful result
    diagnosed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    last_diagnosis_error: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ---- Safety assessment (Step 6) ----
    # All nullable, so older databases can be upgraded by simply adding the columns (see db.upgrade_schema).
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)  # low | medium | high
    safety_assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # latest SafetyAssessmentOut
    safety_answers: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {question_id: yes|no|not_sure}
    # High-risk hazards are kept here once found, so a high-risk request can never drift back to "safe".
    safety_escalations: Mapped[list | None] = mapped_column(JSON, nullable=True)

    customer: Mapped[User | None] = relationship(back_populates="repair_requests")


class RepairCase(Base):
    """
    A resolved repair case (Step 7 "verified-case memory").

    verification_status: "unverified" (default) | "verified" | "rejected"
    A case can only become "verified" with a written verification basis, by an admin, and only when the
    cause was confirmed by a technician — an AI suggestion or a customer's guess is never "verified".
    Symptoms are stored with emails/phone numbers removed. Retrieval never returns customer or request IDs.
    """

    __tablename__ = "repair_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repair_request_id: Mapped[str | None] = mapped_column(ForeignKey("repair_requests.id", ondelete="SET NULL"), nullable=True)
    booking_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # set when recorded from a completed booking
    technician_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trade: Mapped[str] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    symptoms: Mapped[str] = mapped_column(Text)
    clarifying_qa: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confirmed_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    # technician_confirmed | customer_reported | ai_suggestion
    cause_source: Mapped[str] = mapped_column(String(30))
    parts_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    completion_minutes: Mapped[int | None] = mapped_column(nullable=True)
    cost_amount: Mapped[int | None] = mapped_column(nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified", index=True)
    verification_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TechnicianProfile(Base):
    """
    A technician's public profile (Step 8). One per technician user account.

    verification_status: unverified | pending | verified | rejected — only admins can change it.
    is_sample = True marks clearly-labelled DEMO records (created by `python -m app.cli seed-demo`).
    Samples are never "verified" and are only shown when demo mode is on.
    Ratings stay empty until MENDORA has a genuine review system — nothing is invented.
    """

    __tablename__ = "technician_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    trade: Mapped[str] = mapped_column(String(20), index=True)
    service_areas: Mapped[list] = mapped_column(JSON, default=list)  # normalised postal codes / area names
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    years_experience: Mapped[int | None] = mapped_column(nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified", index=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    availability_status: Mapped[str] = mapped_column(String(20), default="available")  # available | busy | unavailable
    visit_rate: Mapped[int | None] = mapped_column(nullable=True)  # call-out estimate, whole currency units
    consultation_rate: Mapped[int | None] = mapped_column(nullable=True)  # per 30-minute consultation
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    rating_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int] = mapped_column(default=0)
    contact_method: Mapped[str] = mapped_column(String(30), default="in_app_booking")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(foreign_keys=[user_id])


BOOKING_TYPES = ("technician_visit", "expert_consultation")
BOOKING_STATUSES = ("requested", "accepted", "rejected", "cancelled", "completed")
ACTIVE_BOOKING_STATUSES = ("requested", "accepted")


class Booking(Base):
    """
    A technician visit or expert consultation request (Step 9). Times are stored in UTC.
    No payment is taken; price_amount is the technician's listed rate as an estimate.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("scheduled_end > scheduled_start", name="ck_booking_end_after_start"),
        CheckConstraint("booking_type IN ('technician_visit', 'expert_consultation')", name="ck_booking_type"),
        CheckConstraint("status IN ('requested', 'accepted', 'rejected', 'cancelled', 'completed')", name="ck_booking_status"),
        Index("ix_bookings_customer", "customer_id", "created_at"),
        Index("ix_bookings_technician", "technician_id", "scheduled_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    technician_id: Mapped[str] = mapped_column(ForeignKey("technician_profiles.id", ondelete="CASCADE"))
    repair_request_id: Mapped[str] = mapped_column(ForeignKey("repair_requests.id", ondelete="CASCADE"))
    booking_type: Mapped[str] = mapped_column(String(30))
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column()
    service_area: Mapped[str | None] = mapped_column(String(60), nullable=True)
    service_address: Mapped[str | None] = mapped_column(Text, nullable=True)  # visits only; shown to the technician after acceptance
    customer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested", index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)  # [{status, at, by, reason}]
    price_amount: Mapped[int | None] = mapped_column(nullable=True)
    price_currency: Mapped[str] = mapped_column(String(3), default="INR")
    safety_risk_level: Mapped[str] = mapped_column(String(10))  # at booking time
    safety_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    technician_is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    # Technician's estimate (merged feature). Customer must approve it before paying.
    estimate_labour: Mapped[int | None] = mapped_column(nullable=True)
    estimate_materials: Mapped[int | None] = mapped_column(nullable=True)
    estimate_status: Mapped[str | None] = mapped_column(String(12), nullable=True)  # proposed | approved | declined
    estimate_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimate_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    technician: Mapped["TechnicianProfile"] = relationship(foreign_keys=[technician_id])
    customer: Mapped[User] = relationship(foreign_keys=[customer_id])
    repair_request: Mapped[RepairRequest] = relationship(foreign_keys=[repair_request_id])


class BookingSlot(Base):
    """
    One row per 30-minute slot an ACTIVE booking occupies. The UNIQUE(technician_id, slot_start)
    constraint makes the database itself refuse a second booking for the same time — even if two
    requests arrive at exactly the same moment. Rows are deleted when a booking is rejected or cancelled.
    """

    __tablename__ = "booking_slots"
    __table_args__ = (UniqueConstraint("technician_id", "slot_start", name="uq_technician_slot"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    technician_id: Mapped[str] = mapped_column(String(36), index=True)
    slot_start: Mapped[str] = mapped_column(String(20))  # "YYYY-MM-DDTHH:MMZ" (UTC), a stable key for the constraint
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)


class Notification(Base):
    """In-app notification (Step 9). Email / SMS / push are NOT configured."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


PAYMENT_STATUSES = ("pending", "succeeded", "failed", "refunded")


class Payment(Base):
    """
    A SANDBOX payment attempt for a booking (Step 10). No real money moves and no card details exist:
    the sandbox provider only simulates an outcome. Card numbers / security codes are never accepted or stored.

    Database rules:
      * at most ONE succeeded payment per booking (partial unique index), so a double click or two
        simultaneous requests can't both succeed;
      * (customer_id, idempotency_key) is unique, so retrying the same attempt returns the same record.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'succeeded', 'failed', 'refunded')", name="ck_payment_status"),
        CheckConstraint("amount >= 0", name="ck_payment_amount"),
        UniqueConstraint("customer_id", "idempotency_key", name="uq_payment_idempotency"),
        Index(
            "uq_payment_one_success_per_booking",
            "booking_id",
            unique=True,
            sqlite_where=text("status = 'succeeded'"),
            postgresql_where=text("status = 'succeeded'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column()  # whole currency units, copied from the booking's stored price
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    method_type: Mapped[str] = mapped_column(String(20), default="sandbox")
    provider: Mapped[str] = mapped_column(String(30), default="sandbox")
    transaction_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)  # simulated, e.g. sbx_txn_…
    failure_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    refund_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sandbox escrow (merged feature): held after payment, released to the technician when the job is completed.
    payout_status: Mapped[str | None] = mapped_column(String(12), nullable=True)  # held | released | returned
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Review(Base):
    """
    A customer's rating of a technician (merged feature). Only allowed for the customer's OWN booking,
    only once that booking is COMPLETED, and only once per booking (unique). No invented reviews.
    """

    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), unique=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    technician_id: Mapped[str] = mapped_column(ForeignKey("technician_profiles.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column()
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RequestPhoto(Base):
    """A photo attached to a repair request (merged feature). Stored on disk with location metadata removed."""

    __tablename__ = "request_photos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repair_request_id: Mapped[str] = mapped_column(ForeignKey("repair_requests.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    content_type: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column()
    stored_name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
