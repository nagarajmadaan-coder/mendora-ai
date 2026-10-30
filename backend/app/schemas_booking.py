"""Request/response shapes for bookings, consultations and notifications (Step 9)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .schemas_payment import BookingPayment, PriceBreakdown
from .schemas_review import ReviewOut
from .schemas_technician import normalize_area

BookingType = Literal["technician_visit", "expert_consultation"]
BookingStatus = Literal["requested", "accepted", "rejected", "cancelled", "completed"]

NO_PAYMENT_NOTE = (
    "Payments in MENDORA are a SANDBOX demonstration: no real money is taken and no card details are used. "
    "The price is the technician's listed rate."
)
NO_CALLS_NOTE = "MENDORA doesn't connect live audio or video calls yet. This records and tracks the consultation request only."
NOTIFICATION_NOTE = "Updates appear inside MENDORA only. Email, SMS and push notifications are not set up yet."


class BookingCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "technician_id": "…",
                    "repair_request_id": "…",
                    "booking_type": "technician_visit",
                    "scheduled_start": "2026-10-29T10:00:00+05:30",
                    "service_area": "560001",
                    "service_address": "Flat 4B, 12 Example Road",
                    "customer_note": "Please ring the bell twice.",
                },
                {"technician_id": "…", "repair_request_id": "…", "booking_type": "expert_consultation", "next_available": True},
            ]
        },
    )

    technician_id: str
    repair_request_id: str
    booking_type: BookingType
    scheduled_start: datetime | None = Field(default=None, description="Start time WITH a timezone offset, on a :00 or :30 minute")
    next_available: bool = Field(default=False, description="Consultations only: book the next free slot")
    service_area: str | None = Field(default=None, max_length=60, description="Visits: your postal code or area")
    service_address: str | None = Field(default=None, max_length=300, description="Visits: shared with the technician only after they accept")
    customer_note: str | None = Field(default=None, max_length=500)
    safety_acknowledged: bool = Field(default=False, description="Required for high-risk requests")

    @field_validator("service_area")
    @classmethod
    def _area(cls, value: str | None) -> str | None:
        return normalize_area(value) if value and value.strip() else None

    @field_validator("service_address", "customer_note")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("scheduled_start")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Include a timezone offset, e.g. 2026-10-29T10:00:00+05:30.")
        return value

    @model_validator(mode="after")
    def _time_and_place(self) -> "BookingCreate":
        if self.next_available and self.booking_type != "expert_consultation":
            raise ValueError("next_available is only for expert consultations; choose a time for visits.")
        if self.next_available and self.scheduled_start is not None:
            raise ValueError("Send either scheduled_start or next_available, not both.")
        if not self.next_available and self.scheduled_start is None:
            raise ValueError("Choose a time (scheduled_start)" + (" or set next_available." if self.booking_type == "expert_consultation" else "."))
        if self.booking_type == "technician_visit":
            if not self.service_area:
                raise ValueError("A visit needs your postal code or area (service_area).")
            if not self.service_address or len(self.service_address) < 5:
                raise ValueError("A visit needs the service address (at least 5 characters).")
        return self


class BookingReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=300)


class CompletionReport(BaseModel):
    """Optional details when a technician completes a visit. Recorded as an UNVERIFIED repair case."""

    model_config = ConfigDict(extra="forbid")
    confirmed_cause: str | None = Field(default=None, min_length=3, max_length=500)
    parts_used: list[str] = Field(default_factory=list, max_length=20)
    completion_minutes: int | None = Field(default=None, ge=1, le=60 * 24)
    cost_amount: int | None = Field(default=None, ge=0, le=10_000_000)
    notes: str | None = Field(default=None, max_length=500)


class TechnicianSummary(BaseModel):
    id: str
    display_name: str
    trade: str
    is_sample: bool
    sample_notice: str | None
    verification_label: str


class RequestSummary(BaseModel):
    id: str
    trade: str
    description: str
    risk_level: str


class HistoryItem(BaseModel):
    status: BookingStatus
    at: datetime
    by: Literal["customer", "technician", "admin", "system"]
    reason: str | None = None


class BookingOut(BaseModel):
    id: str
    booking_type: BookingType
    status: BookingStatus
    status_reason: str | None
    scheduled_start: datetime
    scheduled_end: datetime
    duration_minutes: int
    local_time_label: str = Field(description="Start and end in the service timezone, e.g. 'Thu 29 Oct 2026, 10:00–12:00 (Asia/Kolkata)'")
    timezone: str
    technician: TechnicianSummary
    repair_request: RequestSummary
    customer_display_name: str = Field(description="First name only")
    service_area: str | None
    service_address: str | None = Field(description="Hidden from the technician until they accept")
    address_note: str | None
    customer_note: str | None
    price_amount: int | None
    price_currency: str
    price_note: str
    safety_risk_level: str
    safety_acknowledged: bool
    history: list[HistoryItem]
    allowed_actions: list[str] = Field(description="What YOU may do next: accept, reject, cancel, complete")
    consultation_note: str | None
    payment: BookingPayment
    price_breakdown: PriceBreakdown
    estimate_actions: list[str] = Field(default_factory=list, description="propose (technician) or approve/decline (customer)")
    review: ReviewOut | None = Field(default=None, description="The customer's review of this booking, if any")
    can_review: bool = Field(default=False, description="True when YOU can review this booking now")
    created_at: datetime
    updated_at: datetime


class BookingList(BaseModel):
    bookings: list[BookingOut]
    total: int


class Slot(BaseModel):
    start: datetime
    end: datetime
    local_time: str


class AvailabilityOut(BaseModel):
    technician_id: str
    date: str
    timezone: str
    booking_type: BookingType
    duration_minutes: int
    slots: list[Slot]
    message: str | None = None


class QuoteOut(BaseModel):
    technician: TechnicianSummary
    booking_type: BookingType
    scheduled_start: datetime
    scheduled_end: datetime
    local_time_label: str
    duration_minutes: int
    price_amount: int | None
    price_currency: str
    price_note: str
    safety_risk_level: str
    requires_safety_acknowledgement: bool
    safety_message: str | None
    emergency_steps: list[str]
    notes: list[str]


class NotificationOut(BaseModel):
    id: str
    booking_id: str | None
    kind: str
    message: str
    created_at: datetime
    read: bool


class NotificationList(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int
    channel: Literal["in_app"] = "in_app"
    note: str = NOTIFICATION_NOTE
