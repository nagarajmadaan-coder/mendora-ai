"""
Public technician discovery (Step 8).

Only verified technicians (and, in demo mode, clearly-labelled samples) are visible.
No contact details are ever returned — customers request bookings through MENDORA.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ...errors import ApiError
from ...models import TechnicianProfile
from ...schemas import ErrorResponse
from ...schemas_booking import AvailabilityOut
from ...schemas_review import ReviewList
from ...services import reviews as review_svc
from ...schemas_technician import TechnicianPublic, TechnicianSearchResult
from ...services import bookings as booking_svc
from ...services import technicians as svc
from ..dependencies import get_db

router = APIRouter(prefix="/technicians", tags=["Technicians"])


def demo_mode(request: Request) -> bool:
    return request.app.state.settings.demo_mode_enabled


def get_visible(db: Session, technician_id: str, demo: bool) -> TechnicianProfile:
    profile = db.get(TechnicianProfile, technician_id)
    if profile is None or not svc.is_publicly_visible(profile, demo):
        raise ApiError(404, "technician_not_found", f"No available technician with ID '{technician_id}'.")
    return profile


@router.get(
    "",
    response_model=TechnicianSearchResult,
    summary="Find technicians",
    description=(
        "Filter by trade, service area (postal code or area name) and availability. Results explain why each technician "
        "matches. Sorting uses service-area match and availability — **not distance**."
    ),
)
def search_technicians(
    request: Request,
    trade: str | None = Query(None, max_length=20, description="plumbing, electrical or carpentry (any capitalisation)"),
    area: str | None = Query(None, max_length=60, description="Postal code, neighbourhood or city"),
    available: bool = Query(False, description="Only technicians currently accepting requests"),
    consultation: bool = Query(False, description="Only technicians who offer expert consultations"),
    db: Session = Depends(get_db),
) -> TechnicianSearchResult:
    demo = demo_mode(request)
    trade_id = trade.strip().lower() if trade and trade.strip() else None
    if trade_id and trade_id not in svc.TRADE_NAMES:
        raise ApiError(422, "invalid_trade", f"Unknown trade '{trade}'. Use plumbing, electrical or carpentry.")
    area_text = area.strip() if area and area.strip() else None

    results = svc.search(db, demo_mode=demo, trade=trade_id, area=area_text, available_only=available, consultation_only=consultation)
    message: str | None = None
    covered: list[str] = []
    if not results:
        trade_word = f"{svc.TRADE_NAMES[trade_id].lower()} " if trade_id else ""
        visible_for_trade = svc.search(db, demo_mode=demo, trade=trade_id)
        if not visible_for_trade:
            message = _nobody_visible_message(db, demo, trade_word)
        else:
            covered = svc.covered_areas(db, demo_mode=demo, trade=trade_id)
            in_area = svc.search(db, demo_mode=demo, trade=trade_id, area=area_text) if area_text else visible_for_trade
            if area_text and not in_area:
                message = f"No {trade_word}technicians list '{area_text}' as a service area. Try one of the areas below, or another nearby area."
            else:
                limits = [w for w, on in (("accepting requests now", available), ("offering consultations", consultation)) if on]
                where = f" for '{area_text}'" if area_text else ""
                message = f"There are {trade_word}technicians{where}, but none are {' and '.join(limits)}. Try turning that filter off."
                covered = []
    from ...schemas_technician import MapPoint
    from ...services import areas as area_geo

    c = area_geo.centre(area_text)
    point = MapPoint(lat=c[0], lon=c[1], label=c[2]) if c else None
    return TechnicianSearchResult(results=results, total=len(results), demo_mode=demo, message=message, covered_areas=covered, search_point=point)


def _nobody_visible_message(db: Session, demo: bool, trade_word: str) -> str:
    samples = db.query(TechnicianProfile).filter(TechnicianProfile.is_sample.is_(True)).count()
    if not demo and samples:
        return (
            f"No verified {trade_word}technicians yet. Sample (demo) technicians exist but are hidden because demo mode is off "
            "(set MENDORA_DEMO_MODE=true in backend/.env to show them)."
        )
    if demo and samples == 0:
        return (
            f"No {trade_word}technicians are listed yet. For a local demo, create clearly-labelled sample technicians with: "
            "python -m app.cli seed-demo"
        )
    return f"No verified {trade_word}technicians are listed yet."


@router.get("/{technician_id}", response_model=TechnicianPublic, summary="One technician's public profile", responses={404: {"model": ErrorResponse}})
def get_technician(technician_id: str, request: Request, db: Session = Depends(get_db)) -> TechnicianPublic:
    return svc.to_public(get_visible(db, technician_id, demo_mode(request)))


@router.get(
    "/{technician_id}/availability",
    response_model=AvailabilityOut,
    summary="Free time slots on a day",
    description="Times are within working hours in the service timezone. Already-booked times are left out.",
    responses={404: {"model": ErrorResponse}},
)
def technician_availability(
    technician_id: str,
    request: Request,
    day: date = Query(..., alias="date", description="YYYY-MM-DD in the service timezone"),
    booking_type: str = Query("technician_visit", pattern="^(technician_visit|expert_consultation)$"),
    db: Session = Depends(get_db),
) -> AvailabilityOut:
    settings = request.app.state.settings
    profile = get_visible(db, technician_id, settings.demo_mode_enabled)
    message = None
    if profile.availability_status == "unavailable":
        slots, message = [], "This technician isn't taking new requests right now."
    elif booking_type == "expert_consultation" and profile.consultation_rate is None:
        slots, message = [], "This technician doesn't offer expert consultations."
    else:
        slots = booking_svc.free_slots_for_day(db, profile, day, booking_type, settings)
        if not slots:
            message = "No free times on this day. Try another date."
    return AvailabilityOut(
        technician_id=profile.id,
        date=day.isoformat(),
        timezone=settings.timezone,
        booking_type=booking_type,  # type: ignore[arg-type]
        duration_minutes=booking_svc.DURATION[booking_type],
        slots=slots,
        message=message,
    )


@router.get("/{technician_id}/reviews", response_model=ReviewList, summary="Reviews from completed bookings", responses={404: {"model": ErrorResponse}})
def technician_reviews(technician_id: str, request: Request, db: Session = Depends(get_db)) -> ReviewList:
    profile = get_visible(db, technician_id, demo_mode(request))
    items = review_svc.list_for_technician(db, profile.id)
    return ReviewList(reviews=items, average=profile.rating_average if profile.review_count else None, count=profile.review_count or 0)
