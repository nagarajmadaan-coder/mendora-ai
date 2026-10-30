"""Reviews from completed bookings (merged feature)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

REVIEW_SOURCE_NOTE = "Reviews come only from customers whose MENDORA booking with this technician was completed."


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"rating": 5, "comment": "Arrived on time and fixed the leak."}]})

    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return " ".join(value.split()) or None if value else None


class ReviewOut(BaseModel):
    id: str
    rating: int
    comment: str | None
    booking_type: str
    author: str = Field(default="A MENDORA customer", description="Customers are not named publicly")
    verified_booking: bool = Field(default=True, description="Always true: every review is tied to a completed booking")
    created_at: datetime


class ReviewList(BaseModel):
    reviews: list[ReviewOut]
    average: float | None
    count: int
    note: str = REVIEW_SOURCE_NOTE
