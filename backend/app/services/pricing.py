"""
Price breakdown (merged feature). Decimal arithmetic so no floating-point surprises.

  total               = visit fee + labour + materials        (what the customer pays — sandbox)
  platform fee        = commission % of (visit fee + labour)   (materials are passed through)
  technician earnings = total − platform fee
"""

from decimal import ROUND_HALF_UP, Decimal

from ..models import Booking
from ..schemas_payment import PriceBreakdown


def _d(value: int | float | None) -> Decimal:
    return Decimal(str(max(0, value or 0)))


def breakdown(booking: Booking, commission_percent: float) -> PriceBreakdown:
    status = booking.estimate_status or "listed_rate"
    use_estimate = status in ("proposed", "approved", "declined")
    visit = _d(booking.price_amount)
    labour = _d(booking.estimate_labour) if use_estimate else Decimal(0)
    materials = _d(booking.estimate_materials) if use_estimate else Decimal(0)
    rate = Decimal(str(commission_percent)) / Decimal(100)
    total = visit + labour + materials
    fee = ((visit + labour) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    notes = {
        "listed_rate": "The technician's listed rate. They may send an estimate for labour and materials after accepting.",
        "proposed": "The technician sent an estimate. Approve or decline it before paying.",
        "approved": "You approved this estimate. This is the amount you pay (sandbox).",
        "declined": "You declined this estimate. The technician can send a new one, or you can cancel the booking.",
    }
    return PriceBreakdown(
        status=status,  # type: ignore[arg-type]
        currency=booking.price_currency,
        visit_fee=int(visit) if booking.price_amount is not None else None,
        labour=int(labour),
        materials=int(materials),
        total=int(total) if booking.price_amount is not None or use_estimate else None,
        commission_percent=float(commission_percent),
        platform_fee=float(fee),
        technician_earnings=float((total - fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        estimate_note=booking.estimate_note,
        note=notes[status],
    )


def payable_amount(booking: Booking) -> int | None:
    """What the customer can pay now, or None when nothing is payable (no price, or estimate not approved)."""
    status = booking.estimate_status
    if status in ("proposed", "declined"):
        return None
    if status == "approved":
        return int(_d(booking.price_amount) + _d(booking.estimate_labour) + _d(booking.estimate_materials))
    return booking.price_amount
