"""
Photo attachments (merged feature, done safely).

  * Only JPEG, PNG or WebP — checked from the file's actual bytes, not its name or the type the browser claims.
  * Location and camera metadata (EXIF / XMP / text chunks) are removed before saving.
  * Who can see them: the request's owner, admins, and a technician whose booking for it was ACCEPTED or COMPLETED.
  * Files are stored under random names outside the website; they are never sent to the AI or to web search.
"""

import base64
import binascii
import struct
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ApiError
from ..models import Booking, RepairRequest, RequestPhoto, TechnicianProfile, User

EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _strip_jpeg(data: bytes) -> bytes:
    """Drop APP1 (EXIF/XMP, incl. GPS), APP13 (IPTC) and comment segments; keep the image itself."""
    out, i = bytearray(data[:2]), 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise ValueError("bad JPEG marker")
        marker = data[i + 1]
        if marker == 0xDA:  # start of scan: the rest is image data
            out += data[i:]
            return bytes(out)
        if 0xD0 <= marker <= 0xD9 or marker == 0x01:
            out += data[i : i + 2]
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        segment = data[i : i + 2 + length]
        if len(segment) < 2 + length:
            raise ValueError("truncated JPEG")
        if marker not in (0xE1, 0xED, 0xFE):
            out += segment
        i += 2 + length
    raise ValueError("JPEG has no image data")


def _strip_png(data: bytes) -> bytes:
    out, i = bytearray(data[:8]), 8
    while i + 12 <= len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        chunk = data[i : i + 12 + length]
        if len(chunk) < 12 + length:
            raise ValueError("truncated PNG")
        if ctype not in (b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"tIME"):
            out += chunk
        i += 12 + length
        if ctype == b"IEND":
            return bytes(out)
    raise ValueError("PNG has no end")


def _strip_webp(data: bytes) -> bytes:
    chunks, i = [], 12
    while i + 8 <= len(data):
        fourcc = data[i : i + 4]
        size = struct.unpack("<I", data[i + 4 : i + 8])[0]
        padded = size + (size & 1)
        chunk = data[i : i + 8 + padded]
        if len(chunk) < 8 + size:
            raise ValueError("truncated WebP")
        if fourcc not in (b"EXIF", b"XMP "):
            if fourcc == b"VP8X" and size >= 1:  # clear the "has EXIF/XMP" flags
                flags = chunk[8] & ~0x0C
                chunk = chunk[:8] + bytes([flags]) + chunk[9:]
            chunks.append(chunk)
        i += 8 + padded
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def clean(data: bytes, content_type: str) -> bytes:
    try:
        return {"image/jpeg": _strip_jpeg, "image/png": _strip_png, "image/webp": _strip_webp}[content_type](data)
    except (ValueError, struct.error) as exc:
        raise ApiError(422, "invalid_photo", "This file looks damaged or isn't a real photo. Please try another one.") from exc


def can_view(db: Session, record: RepairRequest, user: User) -> bool:
    if user.role == "admin" or (record.customer_id and record.customer_id == user.id):
        return True
    if user.role == "technician":
        profile = db.scalar(select(TechnicianProfile).where(TechnicianProfile.user_id == user.id))
        if profile is None:
            return False
        return db.scalar(
            select(Booking.id).where(
                Booking.repair_request_id == record.id,
                Booking.technician_id == profile.id,
                Booking.status.in_(("accepted", "completed")),
            )
        ) is not None
    return False


def get_request_for(db: Session, request_id: str, user: User) -> RepairRequest:
    record = db.get(RepairRequest, request_id)
    if record is None or not can_view(db, record, user):
        raise ApiError(404, "repair_request_not_found", f"No repair request found with ID '{request_id}'.")
    return record


def list_for(db: Session, record: RepairRequest) -> list[RequestPhoto]:
    return list(db.scalars(select(RequestPhoto).where(RequestPhoto.repair_request_id == record.id).order_by(RequestPhoto.created_at)).all())


def upload(db: Session, user: User, request_id: str, data_base64: str, settings: Settings) -> RequestPhoto:
    record = get_request_for(db, request_id, user)
    if user.role != "admin" and record.customer_id != user.id:
        raise ApiError(403, "forbidden", "Only the person who reported the problem can add photos.")
    if len(list_for(db, record)) >= settings.photos_per_request:
        raise ApiError(409, "too_many_photos", f"A request can have up to {settings.photos_per_request} photos.")
    limit = settings.photo_max_mb * 1024 * 1024
    if len(data_base64) > (limit * 4) // 3 + 16:
        raise ApiError(413, "photo_too_large", f"Photos must be {settings.photo_max_mb} MB or smaller.")
    try:
        raw = base64.b64decode(data_base64.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ApiError(422, "invalid_photo", "The photo couldn't be read. Please try again.") from exc
    if len(raw) > limit:
        raise ApiError(413, "photo_too_large", f"Photos must be {settings.photo_max_mb} MB or smaller.")
    kind = sniff(raw)
    if kind is None:
        raise ApiError(415, "unsupported_photo_type", "Only JPEG, PNG or WebP photos can be added.")
    cleaned = clean(raw, kind)
    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{EXT[kind]}"
    (folder / name).write_bytes(cleaned)
    photo = RequestPhoto(repair_request_id=record.id, uploaded_by=user.id, content_type=kind, size_bytes=len(cleaned), stored_name=name)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def get_photo_for(db: Session, photo_id: str, user: User) -> tuple[RequestPhoto, RepairRequest]:
    photo = db.get(RequestPhoto, photo_id)
    record = db.get(RepairRequest, photo.repair_request_id) if photo else None
    if photo is None or record is None or not can_view(db, record, user):
        raise ApiError(404, "photo_not_found", "No photo found.")
    return photo, record


def read_bytes(photo: RequestPhoto, settings: Settings) -> bytes:
    path = Path(settings.upload_dir) / photo.stored_name
    if not path.is_file():
        raise ApiError(404, "photo_not_found", "The photo file is missing.")
    return path.read_bytes()


def delete(db: Session, user: User, photo_id: str, settings: Settings) -> None:
    photo, record = get_photo_for(db, photo_id, user)
    if user.role != "admin" and record.customer_id != user.id:
        raise ApiError(403, "forbidden", "Only the person who reported the problem can remove photos.")
    path = Path(settings.upload_dir) / photo.stored_name
    db.delete(photo)
    db.commit()
    path.unlink(missing_ok=True)
