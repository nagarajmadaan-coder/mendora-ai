"""
Technician profiles, visibility rules and matching (Step 8).

Who customers can see / book:
  * real technicians whose profile an admin has VERIFIED, and
  * clearly-labelled SAMPLE technicians, only when demo mode is on.
Unverified, pending and rejected profiles are hidden from customers.

Matching uses service areas (postal codes / area names). There is no GPS distance, so results
are never described as "nearest".
"""

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import TechnicianProfile
from ..schemas_technician import (
    MapPoint,
    ReviewSummary,
    TechnicianMatch,
    TechnicianPrivate,
    TechnicianProfileUpdate,
    TechnicianPublic,
    normalize_area,
)

SAMPLE_NOTICE = "Demo sample — not a real technician and not verified. For testing MENDORA only."

TRADE_NAMES = {"plumbing": "Plumbing", "electrical": "Electrical", "carpentry": "Carpentry"}

# ---------- Service-area matching ----------
# Areas are matched as text (postal code, neighbourhood or city) — there's no map or distance.
# To avoid missing obvious matches, comparison ignores case, spaces and punctuation, accepts common
# alternative city names, and checks each comma-separated part of what the customer typed.
AREA_ALIASES = {
    "bangalore": "bengaluru",
    "bengalooru": "bengaluru",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "gurgaon": "gurugram",
    "new delhi": "delhi",
    "poona": "pune",
    "mysore": "mysuru",
    "trivandrum": "thiruvananthapuram",
    "cochin": "kochi",
}


def area_key(value: str) -> str:
    """'Indira  Nagar' / 'indiranagar' / 'INDIRA-NAGAR' -> 'indiranagar'; 'Bangalore' -> 'bengaluru'."""
    text = re.sub(r"[^\w\s]", " ", normalize_area(value))
    text = " ".join(text.split())
    text = AREA_ALIASES.get(text, text)
    return text.replace(" ", "")


def query_area_keys(value: str) -> set[str]:
    """Keys for the whole text and for each part: 'Koramangala, Bangalore' -> {koramangalabangalore, koramangala, bengaluru}."""
    parts = [value, *re.split(r"[,;/|]", value)]
    return {k for k in (area_key(p) for p in parts if p.strip()) if k}


def matching_area(profile_areas: list[str], keys: set[str]) -> str | None:
    """The technician's own area label that matches what the customer typed, if any."""
    for label in profile_areas:
        if area_key(label) in keys:
            return label
    return None


def covered_areas(db: Session, *, demo_mode: bool, trade: str | None = None) -> list[str]:
    """All areas covered by technicians customers can currently see (optionally for one trade)."""
    query = select(TechnicianProfile)
    if trade:
        query = query.where(TechnicianProfile.trade == trade)
    seen: dict[str, str] = {}
    for p in db.scalars(query).all():
        if is_publicly_visible(p, demo_mode):
            for label in p.service_areas or []:
                seen.setdefault(area_key(label), label)
    return sorted(seen.values())


def is_publicly_visible(profile: TechnicianProfile, demo_mode: bool) -> bool:
    if profile.is_sample:
        return demo_mode
    return profile.verification_status == "verified"


def verification_label(profile: TechnicianProfile) -> str:
    if profile.is_sample:
        return "Demo sample (not verified)"
    return {
        "verified": "Verified by a MENDORA admin",
        "pending": "Verification pending",
        "rejected": "Verification rejected",
    }.get(profile.verification_status, "Not verified")


def to_public(profile: TechnicianProfile) -> TechnicianPublic:
    count = profile.review_count or 0
    reviews = ReviewSummary(average=profile.rating_average if count else None, count=count)
    if count:
        reviews.note = f"Based on {count} review{'s' if count != 1 else ''} from completed MENDORA bookings."
    return TechnicianPublic(
        id=profile.id,
        display_name=profile.display_name,
        trade=profile.trade,  # type: ignore[arg-type]
        service_areas=list(profile.service_areas or []),
        skills=list(profile.skills or []),
        years_experience=profile.years_experience,
        bio=profile.bio,
        verification_status=profile.verification_status,  # type: ignore[arg-type]
        verification_label=verification_label(profile),
        is_sample=profile.is_sample,
        sample_notice=SAMPLE_NOTICE if profile.is_sample else None,
        availability_status=profile.availability_status,  # type: ignore[arg-type]
        visit_rate=profile.visit_rate,
        consultation_rate=profile.consultation_rate,
        offers_consultation=profile.consultation_rate is not None,
        currency=profile.currency,
        reviews=reviews,
    )


def to_private(profile: TechnicianProfile) -> TechnicianPrivate:
    return TechnicianPrivate(
        **to_public(profile).model_dump(),
        user_id=profile.user_id,
        verification_note=profile.verification_note,
        verified_at=profile.verified_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def get_by_user(db: Session, user_id: str) -> TechnicianProfile | None:
    return db.scalar(select(TechnicianProfile).where(TechnicianProfile.user_id == user_id))


def upsert_profile(db: Session, user_id: str, data: TechnicianProfileUpdate, *, currency: str) -> TechnicianProfile:
    profile = get_by_user(db, user_id)
    if profile is None:
        profile = TechnicianProfile(user_id=user_id, currency=currency, verification_status="unverified")
        db.add(profile)
    elif profile.trade != data.trade and profile.verification_status in ("verified", "pending"):
        # A different trade must be checked again by an admin.
        profile.verification_status = "unverified"
        profile.verification_note = "Trade changed — please submit the profile for verification again."
        profile.verified_at = None
        profile.verified_by = None
    for field in ("display_name", "trade", "service_areas", "skills", "years_experience", "bio", "visit_rate", "consultation_rate"):
        setattr(profile, field, getattr(data, field))
    db.commit()
    db.refresh(profile)
    return profile


def submit_for_verification(db: Session, profile: TechnicianProfile) -> TechnicianProfile:
    if profile.is_sample:
        raise ApiError(409, "sample_profile", "Demo sample profiles can't be verified.")
    if profile.verification_status not in ("unverified", "rejected"):
        raise ApiError(409, "invalid_verification_status", f"This profile is already {profile.verification_status}.")
    profile.verification_status = "pending"
    db.commit()
    db.refresh(profile)
    return profile


def decide_verification(db: Session, profile: TechnicianProfile, *, admin_id: str, decision: str, note: str) -> TechnicianProfile:
    if profile.is_sample:
        raise ApiError(409, "sample_profile", "Demo sample profiles can't be verified — they aren't real technicians.")
    profile.verification_status = decision
    profile.verification_note = note.strip()
    profile.verified_by = admin_id
    profile.verified_at = datetime.now(timezone.utc) if decision == "verified" else None
    db.commit()
    db.refresh(profile)
    return profile


def search(
    db: Session,
    *,
    demo_mode: bool,
    trade: str | None = None,
    area: str | None = None,
    available_only: bool = False,
    consultation_only: bool = False,
) -> list[TechnicianMatch]:
    keys = query_area_keys(area) if area and area.strip() else None
    from . import areas as area_geo  # local import: areas imports helpers from this module

    customer_centre = area_geo.centre(area)
    query = select(TechnicianProfile)
    if trade:
        query = query.where(TechnicianProfile.trade == trade)
    matches: list[TechnicianMatch] = []
    for p in db.scalars(query).all():
        if not is_publicly_visible(p, demo_mode):
            continue
        areas = list(p.service_areas or [])
        matched_area = matching_area(areas, keys) if keys else None
        if keys and matched_area is None:
            continue
        if available_only and p.availability_status != "available":
            continue
        if consultation_only and p.consultation_rate is None:
            continue
        reasons: list[str] = []
        score = 0.0
        if trade:
            reasons.append(f"Offers {TRADE_NAMES.get(p.trade, p.trade).lower()} services")
            score += 1
        if matched_area:
            reasons.append(f"Covers your area ({matched_area})")
            score += 3
        if p.availability_status == "available":
            reasons.append("Currently accepting requests")
            score += 2
        elif p.availability_status == "busy":
            reasons.append("Busy at the moment — may take longer to respond")
            score += 0.5
        else:
            reasons.append("Not taking new requests right now")
            score -= 5
        if p.is_sample:
            reasons.append("Demo sample — not a real technician")
        else:
            reasons.append("Verified by a MENDORA admin")
            score += 1
        if p.years_experience:
            reasons.append(f"{p.years_experience} years' experience (self-reported)")
            score += min(p.years_experience, 10) / 10  # small tie-breaker: never outweighs availability
        if consultation_only:
            reasons.append("Offers expert consultations")
        distance = None
        if customer_centre is not None:
            km = area_geo.nearest_centre_km(customer_centre, areas)
            if km is not None:
                distance = area_geo.approx_km(km)
                reasons.append(f"About {distance:g} km between area centres (approximate)")
        point = area_geo.technician_point(areas)
        matches.append(
            TechnicianMatch(
                technician=to_public(p),
                match_score=round(score, 2),
                match_reasons=reasons,
                approx_distance_km=distance,
                map_point=MapPoint(lat=point[0], lon=point[1], label=point[2]) if point else None,
            )
        )
    matches.sort(key=lambda m: (-m.match_score, m.technician.display_name))
    return matches
