"""Request/response shapes for technician profiles and search (Step 8)."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Trade = Literal["plumbing", "electrical", "carpentry"]
Availability = Literal["available", "busy", "unavailable"]
VerificationStatus = Literal["unverified", "pending", "verified", "rejected"]


def normalize_area(value: str) -> str:
    """'  560 001 ' -> '560001', 'Indira  Nagar' -> 'indira nagar'."""
    text = " ".join(value.strip().lower().split())
    if re.fullmatch(r"[\d ]+", text):
        text = text.replace(" ", "")
    return text


class TechnicianProfileUpdate(BaseModel):
    """What a technician may edit. Verification fields are NOT here — only admins can set them."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "display_name": "Ravi S",
                    "trade": "plumbing",
                    "service_areas": ["560001", "560038"],
                    "skills": ["Leak repair", "Tap replacement"],
                    "years_experience": 6,
                    "bio": "Residential plumbing repairs.",
                    "visit_rate": 450,
                    "consultation_rate": 200,
                }
            ]
        },
    )

    display_name: str = Field(min_length=2, max_length=80)
    trade: Trade
    service_areas: list[str] = Field(min_length=1, max_length=20, description="Postal codes or area names you cover")
    skills: list[str] = Field(default_factory=list, max_length=20)
    years_experience: int | None = Field(default=None, ge=0, le=60)
    bio: str | None = Field(default=None, max_length=600)
    visit_rate: int | None = Field(default=None, ge=0, le=1_000_000, description="Call-out estimate (whole currency units)")
    consultation_rate: int | None = Field(default=None, ge=0, le=1_000_000, description="Per 30-minute consultation; leave empty if you don't offer consultations")

    @field_validator("display_name", "bio")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value

    @field_validator("service_areas")
    @classmethod
    def _areas(cls, areas: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(normalize_area(a) for a in areas if a.strip()))
        if not cleaned:
            raise ValueError("Add at least one service area.")
        if any(len(a) > 60 for a in cleaned):
            raise ValueError("Each service area must be at most 60 characters.")
        return cleaned

    @field_validator("skills")
    @classmethod
    def _skills(cls, skills: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(" ".join(s.split()) for s in skills if s.strip()))
        if any(len(s) > 60 for s in cleaned):
            raise ValueError("Each skill must be at most 60 characters.")
        return cleaned


class AvailabilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability_status: Availability


class VerificationDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"decision": "verified", "note": "Checked trade licence and ID in person on 27 Oct."}]},
    )
    decision: Literal["verified", "rejected"]
    note: str = Field(min_length=10, max_length=600, description="What was checked (verified) or why not (rejected)")


class ReviewSummary(BaseModel):
    average: float | None = None
    count: int = 0
    note: str = "No reviews yet. Reviews come only from customers with a completed MENDORA booking."


class TechnicianPublic(BaseModel):
    """What customers see. No email, phone or account details."""

    id: str
    display_name: str
    trade: Trade
    service_areas: list[str]
    skills: list[str]
    years_experience: int | None
    bio: str | None
    verification_status: VerificationStatus
    verification_label: str
    is_sample: bool
    sample_notice: str | None
    availability_status: Availability
    visit_rate: int | None
    consultation_rate: int | None
    offers_consultation: bool
    currency: str
    reviews: ReviewSummary
    contact_method: Literal["in_app_booking"] = "in_app_booking"


class TechnicianPrivate(TechnicianPublic):
    """The owner's / admin's view."""

    user_id: str
    verification_note: str | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MapPoint(BaseModel):
    lat: float
    lon: float
    label: str
    approximate: bool = True


class TechnicianMatch(BaseModel):
    technician: TechnicianPublic
    match_score: float
    match_reasons: list[str]
    approx_distance_km: float | None = Field(default=None, description="Rough distance between AREA CENTRES (not addresses), to 0.5 km")
    map_point: MapPoint | None = Field(default=None, description="Approximate centre of one of the technician's areas")


class TechnicianSearchResult(BaseModel):
    results: list[TechnicianMatch]
    total: int
    sort_basis: Literal["service_area_and_availability"] = "service_area_and_availability"
    sort_note: str = (
        "Sorted by service-area match, availability and experience — not by distance. "
        "Distances, when shown, are rough: measured between area centres, not your address. "
        "No technician is described as the nearest."
    )
    demo_mode: bool
    message: str | None = None
    search_point: MapPoint | None = Field(default=None, description="Approximate centre of the area you searched for")
    covered_areas: list[str] = Field(
        default_factory=list, description="When nothing matched your area: the areas that ARE covered (for this trade)"
    )


class TechnicianAdminList(BaseModel):
    technicians: list[TechnicianPrivate]
    total: int
