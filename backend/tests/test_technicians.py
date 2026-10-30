"""Step 8 — technician profiles, search, verification, roles."""

import pytest
from fastapi.testclient import TestClient

from app.cli import seed_demo
from app.main import create_app
from conftest import auth, make_settings, register

PROFILE = {
    "display_name": "Ravi S",
    "trade": "plumbing",
    "service_areas": ["560 001", "Indira  Nagar"],
    "skills": ["Leak repair"],
    "years_experience": 6,
    "bio": "Residential plumbing.",
    "visit_rate": 450,
    "consultation_rate": 200,
}


@pytest.fixture
def tech(client, make_staff):
    """A technician with a profile (unverified)."""
    token = make_staff("technician", "tech@example.com")
    r = client.put("/api/technician/profile", json=PROFILE, headers=auth(token))
    assert r.status_code == 200, r.text
    return token, r.json()


@pytest.fixture
def admin(make_staff):
    return make_staff("admin", "admin@example.com")


def verify(client, admin, profile_id, decision="verified"):
    return client.post(f"/api/admin/technicians/{profile_id}/verification", json={"decision": decision, "note": "Checked ID and trade licence in person."}, headers=auth(admin))


def find(client, **params):
    return client.get("/api/technicians", params=params).json()


# ---------- Profiles ----------


def test_profile_created_unverified_and_normalised(tech):
    _, profile = tech
    assert profile["verification_status"] == "unverified" and profile["verification_label"] == "Not verified"
    assert profile["service_areas"] == ["560001", "indira nagar"]
    assert profile["offers_consultation"] is True and profile["currency"] == "INR"
    assert profile["reviews"] == {"average": None, "count": 0, "note": "No reviews yet. Reviews come only from customers with a completed MENDORA booking."}
    assert "email" not in profile and "phone" not in str(profile)


@pytest.mark.parametrize("field", ["verification_status", "is_sample", "rating_average", "review_count", "verified_at"])
def test_technician_cannot_set_protected_fields(client, tech, field):
    token, _ = tech
    r = client.put("/api/technician/profile", json={**PROFILE, field: "verified" if field == "verification_status" else 5}, headers=auth(token))
    assert r.status_code == 422


@pytest.mark.parametrize(
    "patch",
    [{"trade": "roofing"}, {"service_areas": []}, {"service_areas": ["  "]}, {"display_name": "x"}, {"visit_rate": -1}, {"years_experience": 99}],
)
def test_profile_validation(client, tech, patch):
    token, _ = tech
    assert client.put("/api/technician/profile", json={**PROFILE, **patch}, headers=auth(token)).status_code == 422


def test_profile_endpoints_require_technician_role(client, admin):
    customer = register(client)
    for headers in ({}, auth(customer), auth(admin)):
        assert client.get("/api/technician/profile", headers=headers).status_code in (401, 403)
        assert client.put("/api/technician/profile", json=PROFILE, headers=headers).status_code in (401, 403)
        assert client.patch("/api/technician/availability", json={"availability_status": "busy"}, headers=headers).status_code in (401, 403)


def test_no_profile_yet(client, make_staff):
    token = make_staff("technician", "new@example.com")
    assert client.get("/api/technician/profile", headers=auth(token)).status_code == 404


# ---------- Verification ----------


def test_unverified_hidden_from_customers_until_admin_verifies(client, tech, admin):
    token, profile = tech
    assert find(client, trade="plumbing")["total"] == 0
    assert client.get(f"/api/technicians/{profile['id']}").status_code == 404

    assert client.post("/api/technician/profile/submit-verification", headers=auth(token)).json()["verification_status"] == "pending"
    assert client.post("/api/technician/profile/submit-verification", headers=auth(token)).status_code == 409
    assert find(client, trade="plumbing")["total"] == 0  # pending is still hidden

    r = verify(client, admin, profile["id"])
    assert r.status_code == 200 and r.json()["verification_status"] == "verified" and r.json()["verified_at"]
    result = find(client, trade="plumbing")
    assert result["total"] == 1 and result["results"][0]["technician"]["verification_label"] == "Verified by a MENDORA admin"
    assert client.get(f"/api/technicians/{profile['id']}").status_code == 200


def test_only_admin_can_verify(client, tech):
    token, profile = tech
    customer = register(client)
    for headers in ({}, auth(customer), auth(token)):
        assert client.post(f"/api/admin/technicians/{profile['id']}/verification", json={"decision": "verified", "note": "I verify myself."}, headers=headers).status_code in (401, 403)
    assert client.get("/api/admin/technicians", headers=auth(token)).status_code == 403


def test_verification_needs_a_note(client, tech, admin):
    _, profile = tech
    r = client.post(f"/api/admin/technicians/{profile['id']}/verification", json={"decision": "verified", "note": "ok"}, headers=auth(admin))
    assert r.status_code == 422


def test_rejected_hidden_and_can_resubmit(client, tech, admin):
    token, profile = tech
    verify(client, admin, profile["id"], "rejected")
    assert find(client)["total"] == 0
    assert client.post("/api/technician/profile/submit-verification", headers=auth(token)).json()["verification_status"] == "pending"


def test_changing_trade_resets_verification(client, tech, admin):
    token, profile = tech
    verify(client, admin, profile["id"])
    r = client.put("/api/technician/profile", json={**PROFILE, "trade": "electrical"}, headers=auth(token)).json()
    assert r["verification_status"] == "unverified" and "Trade changed" in r["verification_note"]
    assert find(client)["total"] == 0
    # Other edits keep verification
    verify(client, admin, profile["id"])
    r = client.put("/api/technician/profile", json={**PROFILE, "trade": "electrical", "bio": "Updated."}, headers=auth(token)).json()
    assert r["verification_status"] == "verified"


def test_admin_list_filter(client, tech, admin):
    assert client.get("/api/admin/technicians?status=unverified", headers=auth(admin)).json()["total"] == 1
    assert client.get("/api/admin/technicians?status=verified", headers=auth(admin)).json()["total"] == 0


# ---------- Search ----------


def _make_verified(client, make_staff, admin, email, **over):
    token = make_staff("technician", email)
    p = client.put("/api/technician/profile", json={**PROFILE, **over}, headers=auth(token)).json()
    verify(client, admin, p["id"])
    return token, p


def test_search_filters_and_reasons(client, make_staff, admin):
    _make_verified(client, make_staff, admin, "p1@example.com", display_name="Plumber One", service_areas=["560001"])
    _make_verified(client, make_staff, admin, "p2@example.com", display_name="Plumber Two", service_areas=["560034"], consultation_rate=None)
    t3, _ = _make_verified(client, make_staff, admin, "e1@example.com", display_name="Electric One", trade="electrical", service_areas=["560001"])

    assert {r["technician"]["display_name"] for r in find(client, trade="plumbing")["results"]} == {"Plumber One", "Plumber Two"}
    r = find(client, trade="plumbing", area=" 560 001 ")
    assert [x["technician"]["display_name"] for x in r["results"]] == ["Plumber One"]
    assert "Covers your area (560001)" in r["results"][0]["match_reasons"]
    assert "not by distance" in r["sort_note"] and "nearest" in r["sort_note"]
    assert [x["technician"]["display_name"] for x in find(client, trade="plumbing", consultation=True)["results"]] == ["Plumber One"]
    assert find(client, trade="electrical", area="560034")["total"] == 0

    client.patch("/api/technician/availability", json={"availability_status": "unavailable"}, headers=auth(t3))
    assert find(client, trade="electrical", available=True)["total"] == 0
    listed = find(client, trade="electrical")["results"][0]
    assert listed["technician"]["availability_status"] == "unavailable" and "Not taking new requests right now" in listed["match_reasons"]


def test_search_ranks_available_and_area_first(client, make_staff, admin):
    busy, _ = _make_verified(client, make_staff, admin, "a@example.com", display_name="Busy Tech", service_areas=["560001"], years_experience=20)
    _make_verified(client, make_staff, admin, "b@example.com", display_name="Free Tech", service_areas=["560001"], years_experience=1)
    client.patch("/api/technician/availability", json={"availability_status": "busy"}, headers=auth(busy))
    names = [x["technician"]["display_name"] for x in find(client, trade="plumbing", area="560001")["results"]]
    assert names == ["Free Tech", "Busy Tech"]


def test_no_matching_technicians_message(client):
    r = find(client, trade="carpentry", area="999999")
    assert r["total"] == 0 and "No carpentry technicians are listed yet" in r["message"]


def test_search_validation(client):
    assert client.get("/api/technicians?trade=roofing").status_code == 422


# ---------- Demo samples ----------


def test_seed_demo_samples_are_labelled_and_hidden_when_demo_off(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    monkeypatch.setattr("app.cli.get_settings", lambda: settings)
    assert seed_demo("short") == 1
    assert seed_demo("sample-pass-123") == 0
    assert seed_demo("sample-pass-123") == 0  # idempotent: nothing duplicated
    with TestClient(create_app(settings)) as c:
        r = c.get("/api/technicians").json()
        assert r["total"] == 6 and r["demo_mode"] is True
        for m in r["results"]:
            t = m["technician"]
            assert t["is_sample"] and t["verification_status"] == "unverified"
            assert t["verification_label"] == "Demo sample (not verified)"
            assert "not a real technician" in t["sample_notice"]
            assert t["reviews"]["count"] == 0 and t["reviews"]["average"] is None
            assert "Demo sample — not a real technician" in m["match_reasons"]
        # Sample accounts can sign in as technicians, but can't be verified or edited
        login = c.post("/api/auth/login", json={"email": "sample.plumbing.1@demo.mendora.local", "password": "sample-pass-123"}).json()
        assert login["user"]["role"] == "technician"
        assert c.put("/api/technician/profile", json=PROFILE, headers=auth(login)).status_code == 409
    off = make_settings(tmp_path, demo_mode=False)
    with TestClient(create_app(off)) as c:
        assert c.get("/api/technicians").json()["total"] == 0


def test_samples_cannot_be_verified(tmp_path, monkeypatch):
    from app.repositories import users as users_repo
    from app.security import hash_password

    settings = make_settings(tmp_path)
    monkeypatch.setattr("app.cli.get_settings", lambda: settings)
    seed_demo("sample-pass-123")
    with TestClient(create_app(settings)) as c:
        with c.app.state.session_factory() as db:
            users_repo.create(db, email="boss@example.com", full_name="Boss", password_hash=hash_password("boss-pass-123"), role="admin")
        admin = c.post("/api/auth/login", json={"email": "boss@example.com", "password": "boss-pass-123"}).json()
        sample_id = c.get("/api/technicians").json()["results"][0]["technician"]["id"]
        r = c.post(f"/api/admin/technicians/{sample_id}/verification", json={"decision": "verified", "note": "Trying to verify a sample."}, headers=auth(admin))
        assert r.status_code == 409 and r.json()["error"]["code"] == "sample_profile"
