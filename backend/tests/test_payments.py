"""Step 10 — SANDBOX payments: success/failure, amounts, permissions, duplicates, refunds, safety."""

import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Payment
from conftest import auth, create_request, make_settings, register
from test_bookings import HIGH_RISK, PROFILE, admin, at, book, customer, tech, visit  # noqa: F401  (fixtures)


def key() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


def pay(client, token, booking_id, **over):
    body = {"expected_amount": 450, "currency": "INR", "scenario": "success", "idempotency_key": key(), **over}
    return client.post(f"/api/bookings/{booking_id}/payments", json=body, headers=auth(token))


@pytest.fixture
def accepted(client, tech, customer):
    """An accepted technician visit (price 450 INR)."""
    ttoken, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()
    assert client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken)).status_code == 200
    return ctoken, ttoken, b


def payment_count(client, **filters):
    with client.app.state.session_factory() as db:
        q = db.query(Payment)
        for k, v in filters.items():
            q = q.filter(getattr(Payment, k) == v)
        return q.count()


# ---------- eligibility ----------


def test_cannot_pay_before_technician_accepts(client, tech, customer):
    _, profile = tech
    ctoken, req = customer
    b = book(client, ctoken, visit(profile["id"], req["request_id"])).json()
    assert b["payment"]["status"] == "not_payable" and b["payment"]["can_pay"] is False
    assert "once the technician accepts" in b["payment"]["reason"]
    r = pay(client, ctoken, b["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "booking_not_payable"
    assert payment_count(client) == 0


def test_accepted_booking_is_payable_by_customer_only(client, accepted):
    ctoken, ttoken, b = accepted
    mine = client.get(f"/api/bookings/{b['id']}", headers=auth(ctoken)).json()["payment"]
    assert mine["status"] == "unpaid" and mine["can_pay"] is True and mine["amount"] == 450
    assert "SANDBOX" in mine["sandbox_notice"]
    theirs = client.get(f"/api/bookings/{b['id']}", headers=auth(ttoken)).json()["payment"]
    assert theirs["can_pay"] is False and theirs["latest"] is None


# ---------- success / failure ----------


def test_successful_sandbox_payment_marks_booking_paid(client, accepted):
    ctoken, ttoken, b = accepted
    r = pay(client, ctoken, b["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["payment"]["status"] == "succeeded" and body["booking_payment_status"] == "paid"
    assert body["payment"]["amount"] == 450 and body["payment"]["currency"] == "INR"
    assert body["payment"]["method_type"] == "sandbox" and body["payment"]["sandbox"] is True
    assert body["payment"]["transaction_ref"].startswith("sbx_txn_")
    assert "no real money" in body["message"]
    after = client.get(f"/api/bookings/{b['id']}", headers=auth(ctoken)).json()["payment"]
    assert after["status"] == "paid" and after["can_pay"] is False and after["latest"]["status"] == "succeeded"
    # the technician sees that it's paid, but not the payment record
    tech_view = client.get(f"/api/bookings/{b['id']}", headers=auth(ttoken)).json()["payment"]
    assert tech_view["status"] == "paid" and tech_view["latest"] is None
    kinds = [n["kind"] for n in client.get("/api/notifications", headers=auth(ttoken)).json()["notifications"]]
    assert "payment_succeeded" in kinds


@pytest.mark.parametrize("scenario", ["card_declined", "insufficient_funds", "processing_error"])
def test_failed_payment_does_not_mark_paid_and_can_retry(client, accepted, scenario):
    ctoken, _, b = accepted
    r = pay(client, ctoken, b["id"], scenario=scenario)
    assert r.status_code == 201
    body = r.json()
    assert body["payment"]["status"] == "failed" and body["payment"]["failure_code"] == scenario
    assert body["booking_payment_status"] == "unpaid" and "not marked as paid" in body["message"]
    assert client.get(f"/api/bookings/{b['id']}", headers=auth(ctoken)).json()["payment"]["status"] == "unpaid"
    retry = pay(client, ctoken, b["id"])
    assert retry.status_code == 201 and retry.json()["payment"]["status"] == "succeeded"
    assert payment_count(client, status="failed") == 1 and payment_count(client, status="succeeded") == 1


# ---------- amounts & input ----------


@pytest.mark.parametrize("over", [{"expected_amount": 1}, {"expected_amount": 449}, {"currency": "USD"}])
def test_amount_must_match_stored_price(client, accepted, over):
    ctoken, _, b = accepted
    r = pay(client, ctoken, b["id"], **over)
    assert r.status_code == 409 and r.json()["error"]["code"] == "amount_mismatch"
    assert "Nothing was charged" in r.json()["error"]["message"]
    assert payment_count(client) == 0


@pytest.mark.parametrize(
    "over",
    [
        {"card_number": "4111111111111111"},  # card details are never accepted
        {"cvv": "123"},
        {"expected_amount": -5},
        {"idempotency_key": "short"},
        {"idempotency_key": "has spaces in it!"},
        {"scenario": "free_money"},
        {"amount": 1},  # the client can't set the charged amount
    ],
)
def test_invalid_payment_input_rejected(client, accepted, over):
    ctoken, _, b = accepted
    r = pay(client, ctoken, b["id"], **over)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert payment_count(client) == 0


# ---------- duplicates ----------


def test_same_key_is_replayed_not_charged_twice(client, accepted):
    ctoken, _, b = accepted
    k = key()
    first = pay(client, ctoken, b["id"], idempotency_key=k)
    again = pay(client, ctoken, b["id"], idempotency_key=k)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["replayed"] is True and again.json()["payment"]["id"] == first.json()["payment"]["id"]
    assert payment_count(client) == 1


def test_second_payment_after_success_refused(client, accepted):
    ctoken, _, b = accepted
    assert pay(client, ctoken, b["id"]).status_code == 201
    r = pay(client, ctoken, b["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_paid"
    assert payment_count(client, status="succeeded") == 1


def test_key_reused_for_another_booking_refused(client, tech, accepted):
    ctoken, ttoken, b = accepted
    k = key()
    assert pay(client, ctoken, b["id"], idempotency_key=k).status_code == 201
    _, profile = tech
    req2 = create_request(client, auth(ctoken), description="The bathroom tap drips all night and won't stop.").json()
    b2 = book(client, ctoken, visit(profile["id"], req2["request_id"], scheduled_start=at(days=4))).json()
    client.post(f"/api/bookings/{b2['id']}/accept", headers=auth(ttoken))
    r = pay(client, ctoken, b2["id"], idempotency_key=k)
    assert r.status_code == 409 and r.json()["error"]["code"] == "idempotency_key_reused"


def test_simultaneous_payments_only_one_succeeds(client, accepted):
    """Several different attempts at the same instant: the database allows exactly one success."""
    from app.errors import ApiError
    from app.models import User
    from app.payments import service as svc
    from app.schemas_payment import PaymentCreate

    ctoken, _, b = accepted
    factory, settings = client.app.state.session_factory, client.app.state.settings
    n = 6
    barrier, outcomes = threading.Barrier(n), []

    def attempt():
        with factory() as db:
            user = db.get(User, ctoken["user"]["id"])
            data = PaymentCreate(expected_amount=450, currency="INR", scenario="success", idempotency_key=key())
            barrier.wait()
            try:
                result, _ = svc.pay(db, user, b["id"], data, settings)
                outcomes.append(result.payment.status)
            except ApiError as exc:
                outcomes.append(exc.code)

    threads = [threading.Thread(target=attempt) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("succeeded") == 1, outcomes
    assert set(outcomes) - {"succeeded"} <= {"already_paid"}, outcomes
    assert payment_count(client, status="succeeded") == 1


# ---------- permissions & privacy ----------


def test_payment_permissions(client, accepted, admin, make_staff):
    ctoken, ttoken, b = accepted
    other = register(client, "other@example.com", "Other Person")
    assert pay(client, other, b["id"]).status_code == 404  # someone else's booking
    assert pay(client, ttoken, b["id"]).status_code == 403  # technicians don't pay
    assert client.post(f"/api/bookings/{b['id']}/payments", json={"expected_amount": 450, "currency": "INR", "idempotency_key": key()}).status_code == 401
    pid = pay(client, ctoken, b["id"]).json()["payment"]["id"]

    assert client.get(f"/api/payments/{pid}", headers=auth(ctoken)).status_code == 200
    assert client.get(f"/api/payments/{pid}", headers=auth(other)).status_code == 404
    assert client.get(f"/api/payments/{pid}", headers=auth(ttoken)).status_code == 404
    assert client.get(f"/api/payments/{pid}", headers=auth(admin)).status_code == 200
    assert client.get("/api/payments", headers=auth(other)).json()["total"] == 0
    assert client.get("/api/payments", headers=auth(ctoken)).json()["total"] == 1
    assert client.get("/api/payments", headers=auth(admin)).json()["total"] == 1
    assert client.get(f"/api/bookings/{b['id']}/payments", headers=auth(ttoken)).status_code == 403
    assert client.get(f"/api/bookings/{b['id']}/payments", headers=auth(other)).status_code == 404
    assert client.get(f"/api/bookings/{b['id']}/payments", headers=auth(ctoken)).json()["total"] == 1
    assert "card" not in str(client.get(f"/api/payments/{pid}", headers=auth(ctoken)).json()).lower()


# ---------- refunds ----------


def test_cancelling_paid_booking_refunds(client, accepted):
    ctoken, ttoken, b = accepted
    pay(client, ctoken, b["id"])
    r = client.post(f"/api/bookings/{b['id']}/cancel", json={"reason": "No longer needed"}, headers=auth(ctoken))
    assert r.status_code == 200 and r.json()["payment"]["status"] == "refunded"
    latest = r.json()["payment"]["latest"]
    assert latest["status"] == "refunded" and latest["refund_ref"].startswith("sbx_ref_") and latest["refunded_at"]
    assert pay(client, ctoken, b["id"]).json()["error"]["code"] == "booking_not_payable"
    kinds = [n["kind"] for n in client.get("/api/notifications", headers=auth(ctoken)).json()["notifications"]]
    assert "payment_refunded" in kinds


# ---------- safety stays authoritative ----------


def test_paying_never_changes_safety(client, tech):
    ttoken, profile = tech
    ctoken = register(client, "risk@example.com", "Risk Person")
    req = create_request(client, auth(ctoken), description=HIGH_RISK).json()
    b = book(client, ctoken, visit(profile["id"], req["request_id"], safety_acknowledged=True)).json()
    client.post(f"/api/bookings/{b['id']}/accept", headers=auth(ttoken))
    assert pay(client, ctoken, b["id"]).json()["payment"]["status"] == "succeeded"
    assert client.get(f"/api/repair-requests/{req['request_id']}/guidance", headers=auth(ctoken)).json()["status"] == "blocked_by_safety"
    assert client.post(f"/api/repair-requests/{req['request_id']}/diagnosis", headers=auth(ctoken)).status_code == 409
    assert client.get(f"/api/repair-requests/{req['request_id']}", headers=auth(ctoken)).json()["safety"]["risk_level"] == "high"


# ---------- configuration ----------


def test_health_reports_sandbox_payments(client):
    h = client.get("/api/health").json()
    assert h["payments"] == {"provider": "sandbox", "enabled": True, "real_money": False}


def test_payments_switched_off(tmp_path, fake_ai):
    settings = make_settings(tmp_path, payment_provider="none")
    with TestClient(create_app(settings, fake_ai)) as c:
        h = c.get("/api/health").json()
        assert h["payments"]["enabled"] is False


def test_database_itself_refuses_two_successes(client, accepted):
    """Even code that skipped the checks couldn't store two succeeded payments for one booking."""
    from sqlalchemy.exc import IntegrityError

    ctoken, _, b = accepted
    with client.app.state.session_factory() as db:
        for i in range(2):
            db.add(Payment(booking_id=b["id"], customer_id=ctoken["user"]["id"], amount=450, currency="INR", status="succeeded", idempotency_key=f"direct-key-{i}"))
        with pytest.raises(IntegrityError):
            db.commit()
