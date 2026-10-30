"""
Step 11 — end-to-end journeys through the real API (temporary DB, simulated AI transport, sandbox payments).

The customer journey uses the demo configuration exactly as a local install would: clearly-labelled sample
technicians from `seed-demo`, AI provider NOT configured (so diagnosis is reported as unavailable).
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.cli import seed_demo
from app.main import create_app
from conftest import PASSWORD, auth, make_settings

TZ = ZoneInfo("Asia/Kolkata")
LOW = "The kitchen sink drains very slowly and gurgles. It started two days ago."
HIGH = "Sparks come out of the kitchen socket when I plug in the kettle."


def at(days=3, hour=10):
    d = datetime.now(TZ).date() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, tzinfo=TZ).isoformat()


@pytest.fixture
def demo(tmp_path, monkeypatch, fake_ai):
    """Demo install: samples seeded, NO AI key configured."""
    settings = make_settings(tmp_path, environment="development", anthropic_api_key=None)
    monkeypatch.setattr("app.cli.get_settings", lambda: settings)
    assert seed_demo("sample-pass-123") == 0
    with TestClient(create_app(settings, fake_ai)) as c:
        yield c


def login(c, email, password=PASSWORD):
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_customer_and_technician_journey(demo, fake_ai):
    c = demo
    # 1. register + log in
    reg = c.post("/api/auth/register", json={"email": "asha@example.com", "password": PASSWORD, "full_name": "Asha Kumar"})
    assert reg.status_code == 201 and reg.json()["user"]["role"] == "customer"
    cust = login(c, "asha@example.com")
    assert c.get("/api/auth/me", headers=auth(cust)).json()["email"] == "asha@example.com"

    # 2–3. submit a repair request → safety assessment
    req = c.post("/api/repair-requests", json={"trade_id": "plumbing", "description": LOW}, headers=auth(cust)).json()
    assert req["safety"]["risk_level"] == "low" and req["owned_by_account"] is True

    # 4. AI not configured → honest "unavailable", nothing invented, no network call
    d = c.post(f"/api/repair-requests/{req['request_id']}/diagnosis", json={"follow_up_answers": []}, headers=auth(cust))
    assert d.status_code == 503 and d.json()["error"]["code"] == "ai_not_configured" and fake_ai.calls == []
    assert c.get(f"/api/repair-requests/{req['request_id']}", headers=auth(cust)).json()["diagnosis"] is None
    assert c.get("/api/health").json()["ai_diagnosis"]["configured"] is False

    # 5. repair knowledge (allowed for low risk)
    g = c.get(f"/api/repair-requests/{req['request_id']}/guidance", headers=auth(cust)).json()
    assert g["status"] == "matched" and g["mode"] == "full" and g["matches"][0]["entry"]["next_steps"]

    # 6. find technicians (demo samples, clearly labelled)
    found = c.get("/api/technicians", params={"trade": "plumbing", "area": "Bengaluru"}).json()
    tech = found["results"][0]["technician"]
    assert tech["is_sample"] and "not a real technician" in tech["sample_notice"]

    # 7. request a visit (quote first)
    body = {"technician_id": tech["id"], "repair_request_id": req["request_id"], "booking_type": "technician_visit",
            "scheduled_start": at(), "service_area": "bengaluru", "service_address": "Flat 4B, 12 Example Road"}
    q = c.post("/api/bookings/quote", json=body, headers=auth(cust)).json()
    assert q["price_amount"] == tech["visit_rate"]
    b = c.post("/api/bookings", json=body, headers=auth(cust))
    assert b.status_code == 201
    booking = b.json()
    assert booking["status"] == "requested" and booking["payment"]["status"] == "not_payable"

    # technician workflow: log in, availability, see request (no address yet), accept
    t = login(c, "sample.plumbing.1@demo.mendora.local", "sample-pass-123")
    assert c.patch("/api/technician/availability", json={"availability_status": "busy"}, headers=auth(t)).status_code == 200
    assigned = c.get("/api/bookings", headers=auth(t)).json()["bookings"]
    assert [x["id"] for x in assigned] == [booking["id"]] and assigned[0]["service_address"] is None
    acc = c.post(f"/api/bookings/{booking['id']}/accept", headers=auth(t)).json()
    assert acc["status"] == "accepted" and acc["service_address"] == "Flat 4B, 12 Example Road"

    # 8. customer views booking details and status
    mine = c.get(f"/api/bookings/{booking['id']}", headers=auth(cust)).json()
    assert mine["status"] == "accepted" and mine["payment"]["can_pay"] is True

    # 9. sandbox payment
    pay = c.post(f"/api/bookings/{booking['id']}/payments",
                 json={"expected_amount": mine["payment"]["amount"], "currency": "INR", "scenario": "success", "idempotency_key": f"journey-{uuid.uuid4().hex[:8]}"},
                 headers=auth(cust))
    assert pay.status_code == 201 and pay.json()["payment"]["status"] == "succeeded"

    # 10. later: sign in again and see booking + payment status
    again = login(c, "asha@example.com")
    later = c.get("/api/bookings", headers=auth(again)).json()["bookings"][0]
    assert later["status"] == "accepted" and later["payment"]["status"] == "paid"
    assert c.get("/api/payments", headers=auth(again)).json()["payments"][0]["status"] == "succeeded"
    notes = [n["kind"] for n in c.get("/api/notifications", headers=auth(again)).json()["notifications"]]
    assert {"booking_requested", "booking_accepted", "payment_succeeded"} <= set(notes)

    # a second request, declined by the technician
    req2 = c.post("/api/repair-requests", json={"trade_id": "plumbing", "description": "The bathroom tap drips all night and won't stop."}, headers=auth(cust)).json()
    b2 = c.post("/api/bookings", json={**body, "repair_request_id": req2["request_id"], "scheduled_start": at(days=4)}, headers=auth(cust)).json()
    rej = c.post(f"/api/bookings/{b2['id']}/reject", json={"reason": "Fully booked"}, headers=auth(t)).json()
    assert rej["status"] == "rejected" and rej["payment"]["status"] == "not_payable"


def test_admin_only_operations_stay_protected(demo):
    cust = c_register(demo, "c@example.com")
    t = login(demo, "sample.plumbing.1@demo.mendora.local", "sample-pass-123")
    for token in (None, cust, t):
        h = auth(token) if token else {}
        for method, path in [
            ("get", "/api/admin/users"),
            ("get", "/api/admin/repair-requests"),
            ("get", "/api/admin/technicians"),
            ("get", "/api/admin/cases"),
            ("post", "/api/admin/users"),
        ]:
            r = getattr(demo, method)(path, headers=h, **({"json": {}} if method == "post" else {}))
            assert r.status_code in (401, 403), (path, r.status_code)


def c_register(c, email):
    r = c.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Test Person"})
    assert r.status_code == 201
    return r.json()


# ---------- the backend safety engine stays authoritative ----------


@pytest.mark.parametrize(
    "extra",
    [{"risk_level": "low"}, {"safety": {"risk_level": "low"}}, {"allow_diy": True}, {"clarifying_answers": [{"question_id": "x", "answer": "no"}], "risk_level": "low"}],
)
def test_client_cannot_lower_risk_when_creating(demo, extra):
    cust = c_register(demo, f"{uuid.uuid4().hex[:6]}@example.com")
    r = demo.post("/api/repair-requests", json={"trade_id": "electrical", "description": HIGH, **extra}, headers=auth(cust))
    # either rejected outright, or accepted with the server's own (high) assessment
    assert r.status_code == 422 or r.json()["safety"]["risk_level"] == "high"


def test_high_risk_never_reaches_diy_by_any_route(demo):
    cust = c_register(demo, "h@example.com")
    rid = demo.post("/api/repair-requests", json={"trade_id": "electrical", "description": HIGH}, headers=auth(cust)).json()["request_id"]
    # saved-request guidance
    g = demo.get(f"/api/repair-requests/{rid}/guidance", headers=auth(cust)).json()
    assert g["status"] == "blocked_by_safety" and g["matches"] == []
    # stateless knowledge search
    s = demo.post("/api/knowledge/search", json={"trade_id": "electrical", "description": HIGH}).json()
    assert s["mode"] == "blocked" and s["matches"] == []
    # browsing entries never includes steps
    for e in demo.get("/api/knowledge/entries", params={"trade": "electrical"}).json()["entries"]:
        assert "next_steps" not in demo.get(f"/api/knowledge/entries/{e['id']}").json()
    # AI diagnosis refused
    assert demo.post(f"/api/repair-requests/{rid}/diagnosis", json={"follow_up_answers": []}, headers=auth(cust)).status_code == 409
    # answering "no" to every question can't lower a high risk
    req = demo.get(f"/api/repair-requests/{rid}", headers=auth(cust)).json()
    answers = [{"question_id": q["id"], "answer": "no"} for q in req["safety"]["clarifying_questions"]]
    if answers:
        assert demo.post(f"/api/repair-requests/{rid}/safety-answers", json={"answers": answers}, headers=auth(cust)).json()["safety"]["risk_level"] == "high"
    # booking requires acknowledgement and still doesn't lower the risk
    tech = demo.get("/api/technicians", params={"trade": "electrical", "area": "bengaluru"}).json()["results"][0]["technician"]
    body = {"technician_id": tech["id"], "repair_request_id": rid, "booking_type": "technician_visit", "scheduled_start": at(), "service_area": "bengaluru", "service_address": "Flat 4B, 12 Example Road"}
    assert demo.post("/api/bookings", json=body, headers=auth(cust)).json()["error"]["code"] == "safety_acknowledgement_required"
    assert demo.post("/api/bookings", json={**body, "safety_acknowledged": True}, headers=auth(cust)).status_code == 201
    assert demo.get(f"/api/repair-requests/{rid}", headers=auth(cust)).json()["safety"]["risk_level"] == "high"


# ---------- configuration for deployment ----------


def test_production_defaults_are_safe(tmp_path):
    with pytest.raises(ValueError):
        make_settings(tmp_path, environment="production", jwt_secret=None)
    s = make_settings(tmp_path, environment="production")
    assert s.demo_mode_enabled is False and s.api_docs_enabled is False
    with TestClient(create_app(s)) as c:
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
        assert c.get("/", follow_redirects=False).headers["location"] == "/api/health"
        assert c.get("/api/health").status_code == 200
    s2 = make_settings(tmp_path, environment="production", api_docs=True)
    with TestClient(create_app(s2)) as c:
        assert c.get("/docs").status_code == 200


def test_errors_never_leak_internals(demo):
    r = demo.get("/api/bookings/does-not-exist", headers=auth(c_register(demo, "e@example.com")))
    assert r.status_code == 404 and set(r.json()) == {"error"} and "Traceback" not in r.text


def test_expired_or_tampered_token_is_rejected_cleanly(demo):
    cust = c_register(demo, "x@example.com")
    bad = cust["access_token"][:-4] + "abcd"
    r = demo.get("/api/bookings", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401 and r.json()["error"]["code"] in ("invalid_token", "not_authenticated")
