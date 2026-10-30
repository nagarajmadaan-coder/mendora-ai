"""Merged features: photo attachments (metadata stripped, access-controlled), admin dashboard API, backup command."""

import base64
import sqlite3
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import auth, create_request, make_settings, register
from test_bookings import admin, book, customer, tech, visit  # noqa: F401  (fixtures)

GPS = b"GPSLatitude=12.9716;GPSLongitude=77.5946"


def jpeg_with_exif() -> bytes:
    app1 = b"Exif\x00\x00" + GPS
    app0 = b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sos = b"\x00\x08\x01\x01\x00\x00\x3f\x00"
    return (b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
            + b"\xff\xe0" + struct.pack(">H", len(app0) + 2) + app0
            + b"\xff\xda" + sos + b"\x12\x34\x56\x78" + b"\xff\xd9")


def png_with_text() -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"tEXt", b"Location\x00" + GPS)
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


def webp_with_exif() -> bytes:
    def chunk(t, d):
        return t + struct.pack("<I", len(d)) + d + (b"\x00" if len(d) & 1 else b"")
    body = b"WEBP" + chunk(b"VP8X", bytes([0x08, 0, 0, 0, 0, 0, 0, 0, 0, 0])) + chunk(b"VP8 ", b"\x00" * 10) + chunk(b"EXIF", GPS)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def upload(c, token, rid, data):
    return c.post(f"/api/repair-requests/{rid}/photos", json={"data_base64": b64(data)}, headers=auth(token))


@pytest.mark.parametrize("maker, ctype", [(jpeg_with_exif, "image/jpeg"), (png_with_text, "image/png"), (webp_with_exif, "image/webp")])
def test_upload_strips_location_metadata(client, customer, maker, ctype):
    ctoken, req = customer
    r = upload(client, ctoken, req["request_id"], maker())
    assert r.status_code == 201, r.text
    assert r.json()["content_type"] == ctype
    f = client.get(r.json()["url"], headers=auth(ctoken))
    assert f.status_code == 200 and f.headers["content-type"] == ctype and f.headers["cache-control"] == "private, no-store"
    assert GPS not in f.content and b"GPS" not in f.content
    if ctype == "image/webp":
        assert struct.unpack("<I", f.content[4:8])[0] == len(f.content) - 8  # RIFF size still correct


def test_rejects_fake_damaged_large_and_too_many(tmp_path, fake_ai):
    with TestClient(create_app(make_settings(tmp_path, photo_max_mb=1), fake_ai)) as c:
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        assert upload(c, token, rid, b"<script>alert(1)</script> not an image").status_code == 415
        assert upload(c, token, rid, b"\xff\xd8\xff\xe1\x00\x50truncated").status_code == 422
        big = jpeg_with_exif()[:-2] + b"\x00" * (1024 * 1024 + 10) + b"\xff\xd9"
        assert upload(c, token, rid, big).status_code == 413
        assert c.post(f"/api/repair-requests/{rid}/photos", json={"data_base64": "!!!!not-base64!!!!"}, headers=auth(token)).status_code == 422
        for _ in range(3):
            assert upload(c, token, rid, jpeg_with_exif()).status_code == 201
        r = upload(c, token, rid, jpeg_with_exif())
        assert r.status_code == 409 and r.json()["error"]["code"] == "too_many_photos"


def test_photo_access_rules(client, tech, customer, make_staff):
    ttoken, profile = tech
    ctoken, req = customer
    rid = req["request_id"]
    photo = upload(client, ctoken, rid, jpeg_with_exif()).json()
    other = register(client, "other@example.com", "Other Person")
    stranger_tech = make_staff("technician", "t2@example.com")
    for token in (other, stranger_tech, ttoken):  # ttoken: no accepted booking yet
        assert client.get(f"/api/repair-requests/{rid}/photos", headers=auth(token)).status_code == 404
        assert client.get(photo["url"], headers=auth(token)).status_code == 404
    assert client.get(photo["url"]).status_code == 401

    b = book(client, ctoken, visit(profile["id"], rid)).json()
    assert client.get(photo["url"], headers=auth(ttoken)).status_code == 404  # requested, not accepted
    client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken))
    assert client.get(f"/api/repair-requests/{rid}/photos", headers=auth(ttoken)).json()["photos"][0]["id"] == photo["id"]
    assert client.get(photo["url"], headers=auth(ttoken)).status_code == 200
    assert upload(client, ttoken, rid, jpeg_with_exif()).status_code == 403  # technicians can't add
    assert client.delete(photo["url"], headers=auth(ttoken)).status_code == 403

    assert client.delete(photo["url"], headers=auth(ctoken)).status_code == 204
    assert client.get(photo["url"], headers=auth(ctoken)).status_code == 404
    assert list((client.app.state.settings.upload_dir).iterdir()) == []


def test_photos_never_sent_to_ai(client, fake_ai, customer):
    from conftest import GOOD_MODEL_OUTPUT, anthropic_body  # noqa: F401

    ctoken, req = customer
    upload(client, ctoken, req["request_id"], jpeg_with_exif())
    fake_ai.add(body=anthropic_body())
    client.post(f"/api/repair-requests/{req['request_id']}/diagnosis", json={"follow_up_answers": []}, headers=auth(ctoken))
    assert "photo" not in str(fake_ai.calls[0]["payload"]).lower() and "base64" not in str(fake_ai.calls[0]["payload"])


# ---------- admin dashboard ----------


def test_admin_stats_and_escalations(client, admin, customer):
    ctoken, _ = customer
    create_request(client, auth(ctoken), trade_id="electrical", description="Sparks come out of the socket when I plug in the kettle. Call 9876543210")
    s = client.get("/api/admin/stats", headers=auth(admin)).json()
    assert s["users"]["customer"] == 1 and s["users"]["admin"] == 1
    assert s["repair_requests"]["total"] == 2 and s["repair_requests"]["by_risk"]["high"] == 1
    assert s["system"]["payments_provider"] == "sandbox" and "Sandbox" in s["payments_sandbox"]["note"]
    e = client.get("/api/admin/safety-escalations", headers=auth(admin)).json()
    assert e["total"] == 1 and e["items"][0]["trade"] == "electrical" and e["items"][0]["hazards"]
    assert "9876543210" not in str(e)
    for path in ("/api/admin/stats", "/api/admin/safety-escalations"):
        assert client.get(path, headers=auth(ctoken)).status_code == 403
        assert client.get(path).status_code == 401


# ---------- backup ----------


def test_backup_command(tmp_path, monkeypatch, capsys):
    from app.cli import backup

    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as c:
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        upload(c, token, rid, png_with_text())
    monkeypatch.setattr("app.cli.get_settings", lambda: settings)
    out = tmp_path / "bk"
    assert backup(str(out)) == 0
    con = sqlite3.connect(out / "mendora.db")
    assert con.execute("select count(*) from users").fetchone()[0] == 1
    assert len(list((out / "uploads").iterdir())) == 1
    assert "Backup saved" in capsys.readouterr().out
