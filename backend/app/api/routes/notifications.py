"""In-app notifications (Step 9). Nothing is emailed, texted or pushed — the response says so."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...errors import ApiError
from ...models import Notification, User
from ...schemas import ErrorResponse
from ...schemas_booking import NotificationList, NotificationOut
from ...services.bookings import utc
from ..dependencies import get_current_user, get_db

router = APIRouter(prefix="/notifications", tags=["Notifications"], responses={401: {"model": ErrorResponse}})


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(id=n.id, booking_id=n.booking_id, kind=n.kind, message=n.message, created_at=utc(n.created_at), read=n.read_at is not None)


def _list(db: Session, user: User) -> NotificationList:
    rows = db.scalars(select(Notification).where(Notification.recipient_user_id == user.id).order_by(Notification.created_at.desc()).limit(100)).all()
    unread = sum(1 for n in rows if n.read_at is None)
    return NotificationList(notifications=[_out(n) for n in rows], unread_count=unread)


@router.get("", response_model=NotificationList, summary="My notifications (in-app only)")
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> NotificationList:
    return _list(db, user)


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="Mark one as read", responses={404: {"model": ErrorResponse}})
def mark_read(notification_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> NotificationOut:
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_user_id != user.id:
        raise ApiError(404, "notification_not_found", "No notification with this ID.")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        db.commit()
    return _out(n)


@router.post("/read-all", response_model=NotificationList, summary="Mark all as read")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> NotificationList:
    db.execute(update(Notification).where(Notification.recipient_user_id == user.id, Notification.read_at.is_(None)).values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return _list(db, user)
