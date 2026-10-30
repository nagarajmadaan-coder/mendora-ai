"""Request/response shapes for SANDBOX payments (Step 10)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SANDBOX_NOTICE = (
    "SANDBOX DEMONSTRATION — no real money is taken and no card details are collected. "
    "You choose the simulated outcome."
)

PaymentStatus = Literal["pending", "succeeded", "failed", "refunded"]
BookingPaymentStatus = Literal["not_payable", "unpaid", "paid", "refunded"]


class PaymentCreate(BaseModel):
    """
    Start a sandbox payment. There are deliberately NO card fields: anything extra (e.g. card_number) is rejected.
    `expected_amount` is the price you were shown; the server charges the booking's STORED price and refuses if they differ.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"expected_amount": 399, "currency": "INR", "scenario": "success", "idempotency_key": "pay-3f2a9c1e"}]},
    )

    expected_amount: int = Field(ge=0, le=10_000_000, description="The amount shown to you, in whole currency units")
    currency: str = Field(min_length=3, max_length=3)
    scenario: Literal["success", "card_declined", "insufficient_funds", "processing_error"] = Field(
        default="success", description="Sandbox only: which outcome to simulate"
    )
    idempotency_key: str = Field(
        min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$",
        description="A new random value per payment attempt. Re-sending the same key returns the same result instead of paying twice.",
    )


class PaymentOut(BaseModel):
    id: str
    booking_id: str
    amount: int
    currency: str
    status: PaymentStatus
    method_type: str
    provider: str
    sandbox: bool = True
    transaction_ref: str | None = Field(description="Simulated reference — not a real bank transaction")
    failure_code: str | None
    failure_message: str | None
    refund_ref: str | None
    refunded_at: datetime | None
    payout_status: Literal["held", "released", "returned"] | None = None
    released_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PaymentResult(BaseModel):
    payment: PaymentOut
    booking_payment_status: BookingPaymentStatus
    replayed: bool = Field(default=False, description="True when this repeats an earlier attempt with the same idempotency key")
    message: str
    sandbox_notice: str = SANDBOX_NOTICE


class PaymentList(BaseModel):
    payments: list[PaymentOut]
    total: int
    sandbox_notice: str = SANDBOX_NOTICE


class PriceBreakdown(BaseModel):
    """Visit fee + technician's estimate, with the (sandbox) platform fee split. Nothing real is collected."""

    status: Literal["listed_rate", "proposed", "approved", "declined"]
    currency: str
    visit_fee: int | None
    labour: int
    materials: int
    total: int | None
    commission_percent: float
    platform_fee: float
    technician_earnings: float
    estimate_note: str | None
    note: str


class EstimateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"labour": 300, "materials": 150, "note": "Replace trap washer and clean U-bend."}]})
    labour: int = Field(ge=0, le=1_000_000)
    materials: int = Field(ge=0, le=1_000_000)
    note: str | None = Field(default=None, max_length=300)


class EstimateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=300)


class BookingPayment(BaseModel):
    """Payment summary inside a booking."""

    status: BookingPaymentStatus
    can_pay: bool = Field(description="True when YOU can pay now")
    amount: int | None
    currency: str
    reason: str | None = Field(description="Why it can't be paid yet, when it can't")
    latest: PaymentOut | None = Field(description="Most recent attempt (customer and admin only)")
    payout_status: Literal["held", "released", "returned"] | None = Field(default=None, description="Sandbox escrow state of the successful payment")
    payout_note: str | None = None
    sandbox_notice: str = SANDBOX_NOTICE
