"""Photo attachments for repair requests (merged feature). See services/photos.py for the rules."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...models import RequestPhoto, User
from ...schemas import ErrorResponse
from ...services import photos as svc
from ..dependencies import get_current_user, get_db

router = APIRouter(tags=["Photos"], responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})


class PhotoUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_base64: str = Field(min_length=16, description="The image file, base64-encoded (a data: URL prefix is allowed)")


class PhotoOut(BaseModel):
    id: str
    content_type: str
    size_bytes: int
    created_at: datetime
    url: str


class PhotoList(BaseModel):
    photos: list[PhotoOut]
    max_photos: int
    note: str = "Photos are visible to you, MENDORA admins, and a technician only after they accept your booking. They are never sent to the AI."


def _out(p: RequestPhoto) -> PhotoOut:
    created = p.created_at.replace(tzinfo=timezone.utc) if p.created_at.tzinfo is None else p.created_at
    return PhotoOut(id=p.id, content_type=p.content_type, size_bytes=p.size_bytes, created_at=created, url=f"/api/photos/{p.id}")


@router.post("/repair-requests/{request_id}/photos", status_code=status.HTTP_201_CREATED, response_model=PhotoOut, summary="Add a photo (owner)")
def upload_photo(request_id: str, payload: PhotoUpload, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> PhotoOut:
    return _out(svc.upload(db, user, request_id, payload.data_base64, request.app.state.settings))


@router.get("/repair-requests/{request_id}/photos", response_model=PhotoList, summary="Photos for a request")
def list_photos(request_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> PhotoList:
    record = svc.get_request_for(db, request_id, user)
    return PhotoList(photos=[_out(p) for p in svc.list_for(db, record)], max_photos=request.app.state.settings.photos_per_request)


@router.get("/photos/{photo_id}", summary="Photo file", response_class=Response)
def get_photo(photo_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    photo, _ = svc.get_photo_for(db, photo_id, user)
    return Response(
        content=svc.read_bytes(photo, request.app.state.settings),
        media_type=photo.content_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"},
    )


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a photo (owner)")
def delete_photo(photo_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    svc.delete(db, user, photo_id, request.app.state.settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
