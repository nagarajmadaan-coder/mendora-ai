"""Step 9 — bookings, consultations, status rules, privacy, double-booking, notifications."""

import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models import Booking
from conftest import auth, create_request, register

TZ = ZoneInfo("Asia/Kolkata")
PROFILE = {
    "display_name": "Ravi S",
    "trade": "plumbing",
    "service_areas": ["560001"],
    "skills": ["Leak repair"],
    "years_experience": 6,
    "bio": "Residential plumbing.",
    "visit_rate": 450,
    "consultation_rate": 200,
}
HIGH_RISK = "Water is pouring from the ceiling onto the light fitting and sockets, and I can see sparks."


def at(days: int = 3, hour: int = 10, minute: int = 0) -> str:
    d = datetime.now(TZ).date() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ).isoformat()


@pytest.fixture
def admin(make_staff):
    return make_staff("admin", "admin@example.com")


@pytest.fixture
def tech(client, make_staff, admin):
    """A verified plumbing technician."""
    token = make_staff("technician", "tech@example.com")
    profile = client.put("/api/technician/profile", json=PROFILE, headers=auth(token)).json()
    r = client.post(f"/api/admin/technicians/{profile['id']}/verification", json={"decision": "verified", "note": "Checked ID and trade licence in person."}, headers=auth(admin))
    assert r.status_code == 200
    return token, profile


@pytest.fixture
def customer(client):
    token = register(client, "asha@example.com", "Asha Kumar")
    req = create_request(client, auth(token)).json()
    return token, req


def visit(tech_id, req_id, **over):
    body = {
        "technician_id": tech_id,
        "repair_request_id": req_id,
        "booking_type": "technician_visit",
        "scheduled_start": at(),
        "service_area": "560 001",
        "service_address": "Flat 4B, 12 Example Road",
        "customer_note": "Ring twice",
    }
    body.update(over)
    return body


def book(client, token, body):
    return client.post("/api/bookings", json=body, headers=auth(token))


# ---------- creating ----------


def test_successful_visit_booking(client, tech, customer):
    ttoken, profile = tech
    ctoken, req = customer
    r = book(client, ctoken, visit(profile["id"], req["request_id"]))
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "requested" and b["booking_type"] == "technician_visit"
    assert b["duration_minutes"] == 120 and b["price_amount"] == 450 and b["price_currency"] == "INR"
    assert "SANDBOX demonstration" in b["price_note"] and "no real money" in b["price_note"]
    assert b["service_area"] == "560001" and b["service_address"] == "Flat 4B, 12 Example Road"
    assert "10:00–12:00 (Asia/Kolkata)" in b["local_time_label"]
    assert b["allowed_actions"] == ["cancel"]
    assert [h["status"] for h in b["history"]] == ["requested"]


def test_quote_shows_price_before_confirming_and_creates_nothing(client, tech, customer):
    _, profile = tech
    ctoken, req = customer
    q = client.post("/api/bookings/quote", json=visit(profile["id"], req["request_id"]), headers=auth(ctoken))
    assert q.status_code == 200, q.text
    assert q.json()["price_amount"] == 450 and q.json()["requires_safety_acknowledgement"] is False
    assert client.get("/api/bookings", headers=auth(ctoken)).json()["total"] == 0


@pytest.mark.parametrize(
    "over, code",
    [
        ({"scheduled_start": "2020-01-01T10:00:00+05:30"}, "invalid_time"),  # past
        ({"scheduled_start": at(hour=10, minute=15)}, "invalid_time"),  # not on :00/:30
        ({"scheduled_start": at(hour=7)}, "invalid_time"),  # before working hours
        ({"scheduled_start": at(hour=17)}, "invalid_time"),  # visit would end after 18:00
        ({"scheduled_start": at(days=90)}, "invalid_time"),  # too far ahead
        ({"service_area": "999999"}, "area_not_covered"),
    ],
)
def test_invalid_time_or_area(client, tech, customer, over, code):
    _, profile = tech
    ctoken, req = customer
    r = book(client, ctoken, visit(profile["id"], req["request_id"], **over))
    assert r.status_code == 422 and r.json()["error"]["code"] == code, r.text


@pytest.mark.parametrize(
    "over",
    [
        {"scheduled_start": None},
        {"scheduled_start": "2026-12-01T10:00:00"},  # no timezone
        {"service_address": None},
        {"service_area": None},
        {"next_available": True, "scheduled_start": None},  # next_available is for consultations
        {"price_amount": 1},  # unknown field — the customer can't set the price
    ],
)
def test_missing_or_invalid_information(client, tech, customer, over):
    _, profile = tech
    ctoken, req = customer
    body = {k: v for k, v in visit(profile["id"], req["request_id"], **over).items() if v is not None}
    r = book(client, ctoken, body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error", r.text


def test_unauthorized_booking_attempts(client, tech, customer, make_staff):
    ttoken, profile = tech
    ctoken, req = customer
    body = visit(profile["id"], req["request_id"])
    assert client.post("/api/bookings", json=body).status_code == 401
    assert book(client, ttoken, body).status_code == 403  # technicians can't book
    other = register(client, "other@example.com", "Other Person")
    r = book(client, other, body)  # someone else's repair request
    assert r.status_code == 404 and r.json()["error"]["code"] == "repair_request_not_found"


def test_unverified_or_wrong_trade_technician_cannot_be_booked(client, make_staff, customer, tech, admin):
    ctoken, req = customer
    t2 = make_staff("technician", "new@example.com")
    p2 = client.put("/api/technician/profile", json=PROFILE, headers=auth(t2)).json()
    r = book(client, ctoken, visit(p2["id"], req["request_id"]))
    assert r.status_code == 404 and r.json()["error"]["code"] == "technician_not_found"

    t3 = make_staff("technician", "elec@example.com")
    p3 = client.put("/api/technician/profile", json={**PROFILE, "trade": "electrical"}, headers=auth(t3)).json()
    client.post(f"/api/admin/technicians/{p3['id']}/verification", json={"decision": "verified", "note": "Checked ID and trade licence in person."}, headers=auth(admin))
    r = book(client, ctoken, visit(p3["id"], req["request_id"]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "trade_mismatch"

    ttoken, profile = tech
    client.patch("/api/technician/availability", json={"availability_status": "unavailable"}, headers=auth(ttoken))
    r = book(client, ctoken, visit(profile["id"], req["request_id"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "technician_unavailable"


# ---------- conflicts ----------


def test_conflicting_and_duplicate_bookings(client, tech, customer):
    _, profile = tech
    ctoken, req = customer
    assert book(client, ctoken, visit(profile["id"], req["request_id"])).status_code == 201
    # same customer, same request, same type → duplicate
    r = book(client, ctoken, visit(profile["id"], req["request_id"], scheduled_start=at(days=4)))
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_booking"
    # a different customer overlapping 10:00–12:00 (11:00 start) → slot taken
    other = register(client, "other@example.com", "Other Person")
    req2 = create_request(client, auth(other)).json()
    r = book(client, other, visit(profile["id"], req2["request_id"], scheduled_start=at(hour=11)))
    assert r.status_code == 409 and r.json()["error"]["code"] == "time_slot_unavailable"
    # right after it ends is fine
    assert book(client, other, visit(profile["id"], req2["request_id"], scheduled_start=at(hour=12))).status_code == 201


def test_simultaneous_booking_attempts_only_one_wins(client, tech):
    """Many customers try the same slot at the same moment; the database lets exactly one through."""
    from app.schemas_booking import BookingCreate
    from app.services import bookings as svc
    from app.errors import ApiError
    from app.models import User

    _, profile = tech
    ids = []
    for i in range(6):
        token = register(client, f"c{i}@example.com", f"Customer {i}")
        ids.append((token, create_request(client, auth(token)).json()["request_id"]))
    settings = client.app.state.settings
    factory = client.app.state.session_factory
    start = at(days=5, hour=14)
    results: list[str] = []
    barrier = threading.Barrier(len(ids))

    def attempt(token, req_id):
        with factory() as db:
            user = db.query(User).filter(User.id == token["user"]["id"]).one()
            data = BookingCreate(**visit(profile["id"], req_id, scheduled_start=start))
            barrier.wait()
            try:
                svc.create_booking(db, user, data, settings)
                results.append("ok")
            except ApiError as exc:
                results.append(exc.code)

    threads = [threading.Thread(target=attempt, args=pair) for pair in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1, results
    assert set(results) - {"ok"} <= {"time_slot_unavailable"}, results
    with factory() as db:
        assert db.query(Booking).count() == 1


# ---------- status changes ----------


def test_accept_reveals_address_and_notifies(client, tech, customer):
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()

    seen = client.get(f"/api/bookings/{b['id']}", headers=auth(ttoken)).json()
    assert seen["service_address"] is None and "once you accept" in seen["address_note"]
    assert seen["customer_display_name"] == "Asha"  # first name only
    assert "asha@example.com" not in str(seen)
    assert seen["allowed_actions"] == ["accept", "reject", "cancel"]

    assigned = client.get("/api/bookings", headers=auth(ttoken)).json()
    assert assigned["total"] == 1
    overview = client.get("/api/technician/overview", headers=auth(ttoken)).json()
    assert len(overview["assigned_jobs"]) == 1

    notes = client.get("/api/notifications", headers=auth(ttoken)).json()
    assert notes["unread_count"] == 1 and notes["channel"] == "in_app" and "not set up" in notes["note"]

    r = client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken))
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert r.json()["service_address"] == "Flat 4B, 12 Example Road"
    cust_notes = client.get("/api/notifications", headers=auth(ctoken)).json()["notifications"]
    assert any(n["kind"] == "booking_accepted" for n in cust_notes)
    # accepting twice is not a valid transition
    r = client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken))
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_status_transition"


def test_reject_frees_the_slot(client, tech, customer):
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()
    r = client.post(f"/api/bookings/{b['id']}/reject", json={"reason": "Fully booked that day"}, headers=auth(ttoken))
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["status_reason"] == "Fully booked that day"
    assert r.json()["allowed_actions"] == []
    # the same time can be booked again, and the duplicate rule no longer applies
    assert book(client, ctoken, visit(profile["id"], req["request_id"])).status_code == 201


def test_customer_cannot_accept_and_others_cannot_see(client, tech, customer, make_staff):
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()
    r = client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ctoken))
    assert r.status_code == 403
    other_cust = register(client, "other@example.com", "Other")
    other_tech = make_staff("technician", "t2@example.com")
    for token in (other_cust, other_tech):
        assert client.get(f"/api/bookings/{b['id']}", headers=auth(token)).status_code == 404
        assert client.post(f"/api/bookings/{b['id']}/cancel", headers=auth(token)).status_code == 404
        assert client.get("/api/bookings", headers=auth(token)).json()["total"] == 0


def test_cancel_rules(client, tech, customer):
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()
    client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken))
    r = client.post(f"/api/bookings/{b['id']}/cancel", json={"reason": "Fixed it myself"}, headers=auth(ctoken))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert [h["status"] for h in r.json()["history"]] == ["requested", "accepted", "cancelled"]
    tech_notes = client.get("/api/notifications", headers=auth(ttoken)).json()["notifications"]
    assert any(n["kind"] == "booking_cancelled" and "Fixed it myself" in n["message"] for n in tech_notes)
    for action in ("cancel", "accept", "complete"):
        r = client.post(f"/api/bookings/{b['id']}/{action}", headers=auth(ttoken))
        assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_status_transition"


def _move_to_past(client, booking_id):
    with client.app.state.session_factory() as db:
        b = db.get(Booking, booking_id)
        b.scheduled_start = datetime.now(timezone.utc) - timedelta(hours=1)
        b.scheduled_end = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()


def test_complete_only_after_start_and_records_unverified_case(client, tech, customer, admin):
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()
    client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken))
    r = client.post(f"/api/bookings/{b['id']}/complete", headers=auth(ttoken))
    assert r.status_code == 409  # not started yet
    _move_to_past(client, b["id"])
    assert client.post(f"/api/bookings/{b['id']}/cancel", headers=auth(ctoken)).status_code == 409  # already started
    report = {"confirmed_cause": "Grease clog in the sink trap", "parts_used": ["Trap washer"], "completion_minutes": 40, "cost_amount": 450}
    r = client.post(f"/api/bookings/{b['id']}/complete", json=report, headers=auth(ttoken))
    assert r.status_code == 200 and r.json()["status"] == "completed"
    cases = client.get("/api/admin/cases", headers=auth(admin)).json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verification_status"] == "unverified" and cases[0]["cause_source"] == "technician_confirmed"
    assert cases[0]["booking_id"] == b["id"]


def test_unverified_technician_cannot_accept(client, tech, customer, admin):
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()
    client.post(f"/api/admin/technicians/{profile['id']}/verification", json={"decision": "rejected", "note": "Licence could not be confirmed."}, headers=auth(admin))
    r = client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken))
    assert r.status_code == 409 and r.json()["error"]["code"] == "technician_not_verified"
    assert client.post(f"/api/bookings/{b['id']}/cancel", headers=auth(ttoken)).status_code == 200


# ---------- consultations ----------


def test_consultation_next_available_and_status(client, tech, customer):
    ttoken, profile = tech
    ctoken, req = customer
    body = {"technician_id": profile["id"], "repair_request_id": req["request_id"], "booking_type": "expert_consultation", "next_available": True}
    q = client.post("/api/bookings/quote", json=body, headers=auth(ctoken)).json()
    assert q["price_amount"] == 200 and q["duration_minutes"] == 30
    assert any("live audio or video" in n for n in q["notes"])
    r = book(client, ctoken, body)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["scheduled_start"] == q["scheduled_start"] and c["service_address"] is None
    assert "live audio or video" in c["consultation_note"]
    # the next one for someone else skips the taken slot
    other = register(client, "other@example.com", "Other")
    req2 = create_request(client, auth(other)).json()
    c2 = book(client, other, {**body, "repair_request_id": req2["request_id"]}).json()
    assert c2["scheduled_start"] != c["scheduled_start"]
    assert client.post(f"/api/bookings/{c['id']}/accept", headers=auth(ttoken)).json()["status"] == "accepted"
    assert client.get("/api/bookings", params={"status": "accepted"}, headers=auth(ctoken)).json()["total"] == 1


def test_consultation_not_offered(client, make_staff, admin, customer):
    token = make_staff("technician", "noconsult@example.com")
    p = client.put("/api/technician/profile", json={**PROFILE, "consultation_rate": None}, headers=auth(token)).json()
    client.post(f"/api/admin/technicians/{p['id']}/verification", json={"decision": "verified", "note": "Checked ID and trade licence in person."}, headers=auth(admin))
    ctoken, req = customer
    r = book(client, ctoken, {"technician_id": p["id"], "repair_request_id": req["request_id"], "booking_type": "expert_consultation", "next_available": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "consultation_not_offered"


def test_availability_hides_booked_times(client, tech, customer):
    _, profile = tech
    ctoken, req = customer
    day = at()[:10]
    before = client.get(f"/api/technicians/{profile['id']}/availability", params={"date": day}).json()
    assert before["timezone"] == "Asia/Kolkata" and before["duration_minutes"] == 120
    starts = [s["local_time"][:5] for s in before["slots"]]
    assert starts[0] == "09:00" and starts[-1] == "16:00"
    book(client, ctoken, visit(profile["id"], req["request_id"]))
    after = [s["local_time"][:5] for s in client.get(f"/api/technicians/{profile['id']}/availability", params={"date": day}).json()["slots"]]
    for blocked in ("08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30"):
        assert blocked not in after
    assert "12:00" in after


# ---------- safety ----------


def test_high_risk_request_requires_acknowledgement(client, tech):
    _, profile = tech
    ctoken = register(client, "risk@example.com", "Risk Person")
    req = create_request(client, auth(ctoken), description=HIGH_RISK).json()
    assert req["safety"]["risk_level"] == "high", req
    q = client.post("/api/bookings/quote", json=visit(profile["id"], req["request_id"]), headers=auth(ctoken)).json()
    assert q["requires_safety_acknowledgement"] is True and q["emergency_steps"]
    r = book(client, ctoken, visit(profile["id"], req["request_id"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "safety_acknowledgement_required"
    r = book(client, ctoken, visit(profile["id"], req["request_id"], safety_acknowledged=True))
    assert r.status_code == 201 and r.json()["safety_risk_level"] == "high" and r.json()["safety_acknowledged"] is True
    # booking a technician does NOT make the request safe: guidance and AI diagnosis stay blocked
    g = client.get(f"/api/repair-requests/{req['request_id']}/guidance", headers=auth(ctoken)).json()
    assert g["status"] == "blocked_by_safety"
    assert client.post(f"/api/repair-requests/{req['request_id']}/diagnosis", headers=auth(ctoken)).status_code == 409


def test_notifications_mark_read(client, tech, customer):
    ttoken, profile = tech
    ctoken, req = customer
    book(client, ctoken, visit(profile["id"], req["request_id"]))
    notes = client.get("/api/notifications", headers=auth(ttoken)).json()
    nid = notes["notifications"][0]["id"]
    assert client.post(f"/api/notifications/{nid}/read", headers=auth(ctoken)).status_code == 404  # not yours
    assert client.post(f"/api/notifications/{nid}/read", headers=auth(ttoken)).json()["read"] is True
    assert client.get("/api/notifications", headers=auth(ttoken)).json()["unread_count"] == 0
    assert client.post("/api/notifications/read-all", headers=auth(ctoken)).json()["unread_count"] == 0
    assert client.get("/api/notifications").status_code == 401
