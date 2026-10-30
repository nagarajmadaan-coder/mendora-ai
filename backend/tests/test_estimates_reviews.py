"""Merged features: technician estimates + customer approval, price breakdown, sandbox escrow, reviews."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Booking
from conftest import auth, register
from test_bookings import admin, at, book, customer, tech, visit  # noqa: F401  (fixtures)


def key():
    return f"k-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def accepted(client, tech, customer):
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()
    assert client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken)).status_code == 200
    return ctoken, ttoken, b


def get(client, token, bid):
    return client.get(f"/api/bookings/{bid}", headers=auth(token)).json()


def pay(client, token, bid, amount):
    return client.post(f"/api/bookings/{bid}/payments", json={"expected_amount": amount, "currency": "INR", "scenario": "success", "idempotency_key": key()}, headers=auth(token))


def start_in_past(client, bid):
    with client.app.state.session_factory() as db:
        b = db.get(Booking, bid)
        b.scheduled_start = datetime.now(timezone.utc) - timedelta(hours=1)
        b.scheduled_end = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()


# ---------- price breakdown & estimate ----------


def test_listed_rate_breakdown(client, accepted):
    ctoken, _, b = accepted
    pb = get(client, ctoken, b["id"])["price_breakdown"]
    assert pb["status"] == "listed_rate" and pb["visit_fee"] == 450 and pb["total"] == 450
    assert pb["platform_fee"] == 45.0 and pb["technician_earnings"] == 405.0 and pb["commission_percent"] == 10.0


def test_estimate_flow_changes_amount_and_blocks_payment_until_approved(client, accepted):
    ctoken, ttoken, b = accepted
    assert get(client, ttoken, b["id"])["estimate_actions"] == ["propose"]
    r = client.post(f"/api/bookings/{b['id']}/estimate", json={"labour": 300, "materials": 150, "note": "Replace trap washer"}, headers=auth(ttoken))
    assert r.status_code == 200, r.text
    pb = r.json()["price_breakdown"]
    assert pb["status"] == "proposed" and pb["total"] == 900
    assert pb["platform_fee"] == 75.0 and pb["technician_earnings"] == 825.0  # 10% of visit + labour (750); materials passed through

    mine = get(client, ctoken, b["id"])
    assert mine["estimate_actions"] == ["approve", "decline"]
    assert mine["payment"]["can_pay"] is False and "approve it before paying" in mine["payment"]["reason"]
    assert pay(client, ctoken, b["id"], 900).json()["error"]["code"] == "booking_not_payable"
    assert any(n["kind"] == "estimate_proposed" for n in client.get("/api/notifications", headers=auth(ctoken)).json()["notifications"])

    ok = client.post(f"/api/bookings/{b['id']}/estimate/approve", headers=auth(ctoken)).json()
    assert ok["price_breakdown"]["status"] == "approved" and ok["payment"]["amount"] == 900 and ok["payment"]["can_pay"] is True
    assert pay(client, ctoken, b["id"], 450).json()["error"]["code"] == "amount_mismatch"  # old listed rate no longer valid
    assert pay(client, ctoken, b["id"], 900).json()["payment"]["amount"] == 900
    # once paid, the estimate can't be changed
    r = client.post(f"/api/bookings/{b['id']}/estimate", json={"labour": 1, "materials": 1}, headers=auth(ttoken))
    assert r.status_code == 409


def test_decline_then_new_estimate(client, accepted):
    ctoken, ttoken, b = accepted
    client.post(f"/api/bookings/{b['id']}/estimate", json={"labour": 2000, "materials": 0}, headers=auth(ttoken))
    d = client.post(f"/api/bookings/{b['id']}/estimate/decline", json={"reason": "Too expensive"}, headers=auth(ctoken)).json()
    assert d["price_breakdown"]["status"] == "declined" and "declined the estimate" in d["payment"]["reason"]
    assert any("Too expensive" in n["message"] for n in client.get("/api/notifications", headers=auth(ttoken)).json()["notifications"])
    r = client.post(f"/api/bookings/{b['id']}/estimate", json={"labour": 500, "materials": 0}, headers=auth(ttoken)).json()
    assert r["price_breakdown"]["status"] == "proposed" and r["price_breakdown"]["total"] == 950


def test_estimate_permissions_and_validation(client, accepted, make_staff):
    ctoken, ttoken, b = accepted
    assert client.post(f"/api/bookings/{b['id']}/estimate", json={"labour": 1, "materials": 1}, headers=auth(ctoken)).status_code == 403
    assert client.post(f"/api/bookings/{b['id']}/estimate/approve", headers=auth(ttoken)).status_code == 403
    assert client.post(f"/api/bookings/{b['id']}/estimate/approve", headers=auth(ctoken)).status_code == 409  # nothing proposed
    other = make_staff("technician", "t2@example.com")
    assert client.post(f"/api/bookings/{b['id']}/estimate", json={"labour": 1, "materials": 1}, headers=auth(other)).status_code == 404
    for bad in ({"labour": -1, "materials": 0}, {"labour": 1}, {"labour": 1, "materials": 1, "total": 5}):
        assert client.post(f"/api/bookings/{b['id']}/estimate", json=bad, headers=auth(ttoken)).status_code == 422


def test_estimate_only_on_accepted_booking(client, tech, customer):
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()  # still "requested"
    assert client.post(f"/api/bookings/{b['id']}/estimate", json={"labour": 1, "materials": 1}, headers=auth(ttoken)).status_code == 409


# ---------- sandbox escrow ----------


def test_payment_held_then_released_on_completion(client, accepted):
    ctoken, ttoken, b = accepted
    assert pay(client, ctoken, b["id"], 450).json()["payment"]["payout_status"] == "held"
    assert get(client, ctoken, b["id"])["payment"]["payout_status"] == "held"
    start_in_past(client, b["id"])
    done = client.post(f"/api/bookings/{b['id']}/complete", headers=auth(ttoken)).json()
    assert done["payment"]["payout_status"] == "released" and "Released" in done["payment"]["payout_note"]
    assert any(n["kind"] == "payout_released" for n in client.get("/api/notifications", headers=auth(ttoken)).json()["notifications"])


def test_refund_returns_held_payment(client, accepted):
    ctoken, _, b = accepted
    pay(client, ctoken, b["id"], 450)
    r = client.post(f"/api/bookings/{b['id']}/cancel", headers=auth(ctoken)).json()
    assert r["payment"]["status"] == "refunded" and r["payment"]["payout_status"] == "returned"


def test_paying_after_completion_releases_immediately(client, accepted):
    ctoken, ttoken, b = accepted
    start_in_past(client, b["id"])
    client.post(f"/api/bookings/{b['id']}/complete", headers=auth(ttoken))
    assert pay(client, ctoken, b["id"], 450).json()["payment"]["payout_status"] == "released"


# ---------- reviews ----------


def complete(client, ttoken, bid):
    start_in_past(client, bid)
    assert client.post(f"/api/bookings/{bid}/complete", headers=auth(ttoken)).status_code == 200


def test_review_only_after_completion_once_and_updates_average(client, accepted, tech):
    ctoken, ttoken, b = accepted
    _, profile = tech
    r = client.post(f"/api/bookings/{b['id']}/review", json={"rating": 5}, headers=auth(ctoken))
    assert r.status_code == 409 and r.json()["error"]["code"] == "review_not_allowed"
    assert get(client, ctoken, b["id"])["can_review"] is False
    complete(client, ttoken, b["id"])
    assert get(client, ctoken, b["id"])["can_review"] is True
    r = client.post(f"/api/bookings/{b['id']}/review", json={"rating": 4, "comment": "Good work. Call 9876543210"}, headers=auth(ctoken))
    assert r.status_code == 201, r.text
    assert r.json()["verified_booking"] is True and "9876543210" not in r.json()["comment"]
    again = client.post(f"/api/bookings/{b['id']}/review", json={"rating": 1}, headers=auth(ctoken))
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_reviewed"
    after = get(client, ctoken, b["id"])
    assert after["can_review"] is False and after["review"]["rating"] == 4

    pub = client.get(f"/api/technicians/{profile['id']}").json()["reviews"]
    assert pub == {"average": 4.0, "count": 1, "note": "Based on 1 review from completed MENDORA bookings."}
    lst = client.get(f"/api/technicians/{profile['id']}/reviews").json()
    assert lst["count"] == 1 and lst["reviews"][0]["author"] == "A MENDORA customer"
    assert "asha" not in str(lst).lower()
    assert any(n["kind"] == "review_received" for n in client.get("/api/notifications", headers=auth(ttoken)).json()["notifications"])


def test_review_permissions_and_validation(client, accepted, admin):
    ctoken, ttoken, b = accepted
    complete(client, ttoken, b["id"])
    other = register(client, "other@example.com", "Other Person")
    for token in (other, ttoken, admin):
        assert client.post(f"/api/bookings/{b['id']}/review", json={"rating": 5}, headers=auth(token)).status_code == 404
    for bad in ({"rating": 0}, {"rating": 6}, {"rating": 5, "comment": "x" * 501}, {"rating": 5, "technician_id": "someone-else"}):
        assert client.post(f"/api/bookings/{b['id']}/review", json=bad, headers=auth(ctoken)).status_code == 422


def test_no_reviews_message(client, tech):
    _, profile = tech
    r = client.get(f"/api/technicians/{profile['id']}").json()["reviews"]
    assert r["count"] == 0 and r["average"] is None and "completed MENDORA booking" in r["note"]
