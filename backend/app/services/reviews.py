"""
Reviews (merged feature, done safely):
  * only the booking's own customer, only after the booking is COMPLETED, only once per booking;
  * the technician is taken from the booking — never from the request (so nobody can rate a technician they didn't book);
  * contact details in comments are removed; customers are not named publicly;
  * the technician's average is recalculated from stored reviews only.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.privacy import redact
from ..errors import ApiError
from ..models import Booking, Notification, Review, TechnicianProfile, User
from ..schemas_review import ReviewCreate, ReviewOut
from .bookings import utc


def to_out(review: Review, booking_type: str) -> ReviewOut:
    return ReviewOut(id=review.id, rating=review.rating, comment=review.comment, booking_type=booking_type, created_at=utc(review.created_at))


def for_booking(db: Session, booking_id: str) -> Review | None:
    return db.scalar(select(Review).where(Review.booking_id == booking_id))


def recompute(db: Session, technician_id: str) -> None:
    avg, count = db.execute(select(func.avg(Review.rating), func.count(Review.id)).where(Review.technician_id == technician_id)).one()
    profile = db.get(TechnicianProfile, technician_id)
    if profile is not None:
        profile.review_count = int(count or 0)
        profile.rating_average = round(float(avg), 2) if count else None


def create(db: Session, user: User, booking_id: str, data: ReviewCreate) -> ReviewOut:
    booking = db.get(Booking, booking_id)
    if booking is None or user.role != "customer" or booking.customer_id != user.id:
        raise ApiError(404, "booking_not_found", f"No booking found with ID '{booking_id}'.")
    if booking.status != "completed":
        raise ApiError(409, "review_not_allowed", "You can review a technician once the booking is completed.")
    if for_booking(db, booking.id) is not None:
        raise ApiError(409, "already_reviewed", "You've already reviewed this booking.")
    review = Review(
        booking_id=booking.id,
        customer_id=user.id,
        technician_id=booking.technician_id,
        rating=data.rating,
        comment=redact(data.comment) if data.comment else None,
    )
    db.add(review)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "already_reviewed", "You've already reviewed this booking.") from exc
    recompute(db, booking.technician_id)
    profile = db.get(TechnicianProfile, booking.technician_id)
    if profile is not None:
        db.add(Notification(recipient_user_id=profile.user_id, booking_id=booking.id, kind="review_received",
                            message=f"You received a {data.rating}-star review for a completed booking."))
    db.commit()
    return to_out(review, booking.booking_type)


def list_for_technician(db: Session, technician_id: str, limit: int = 50) -> list[ReviewOut]:
    rows = db.execute(
        select(Review, Booking.booking_type).join(Booking, Booking.id == Review.booking_id)
        .where(Review.technician_id == technician_id).order_by(Review.created_at.desc()).limit(limit)
    ).all()
    return [to_out(r, bt) for r, bt in rows]
