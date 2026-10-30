"""Authentication, roles and privacy."""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.cli import create_admin
from app.main import create_app
from app.models import User
from conftest import PASSWORD, auth, create_request, make_settings, register


# ---------- Registration ----------


def test_register_creates_customer_and_returns_token(client):
    body = register(client, email="  Asha@Example.COM ")
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["user"]["email"] == "asha@example.com"  # normalised
    assert body["user"]["role"] == "customer"
    assert set(body["user"]) == {"id", "email", "full_name", "role", "is_active", "created_at"}


def test_password_is_hashed_never_plain(client):
    register(client)
    with client.app.state.session_factory() as db:
        user = db.query(User).one()
    assert user.password_hash != PASSWORD
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_responses_never_include_password_hash(client):
    body = register(client)
    me = client.get("/api/auth/me", headers=auth(body)).json()
    for payload in (body, me):
        assert "password_hash" not in str(payload) and "$argon2" not in str(payload)


def test_duplicate_email_rejected(client):
    register(client)
    r = client.post("/api/auth/register", json={"email": "ASHA@example.com", "password": PASSWORD, "full_name": "Other"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"email": "not-an-email", "password": PASSWORD, "full_name": "A"}, "email"),
        ({"email": "a@example.com", "password": "short", "full_name": "A"}, "password"),
        ({"email": "a@example.com", "password": "        ", "full_name": "A"}, "password"),
        ({"email": "a@example.com", "password": "x" * 129, "full_name": "A"}, "password"),
        ({"email": "a@example.com", "password": PASSWORD, "full_name": "   "}, "full_name"),
        ({"email": "a@example.com", "full_name": "A"}, "password"),
    ],
)
def test_register_validation(client, payload, field):
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 422
    assert field in [d["field"] for d in r.json()["error"]["details"]]


@pytest.mark.parametrize("role", ["admin", "technician", "customer"])
def test_cannot_choose_role_at_registration(client, role):
    r = client.post("/api/auth/register", json={"email": "x@example.com", "password": PASSWORD, "full_name": "X", "role": role})
    assert r.status_code == 422
    assert [d["field"] for d in r.json()["error"]["details"]] == ["role"]


# ---------- Login ----------


def test_login_success(client):
    register(client)
    r = client.post("/api/auth/login", json={"email": "ASHA@example.com", "password": PASSWORD})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=auth(r.json()))
    assert me.status_code == 200 and me.json()["email"] == "asha@example.com"


@pytest.mark.parametrize("email,password", [("asha@example.com", "wrong-password"), ("nobody@example.com", PASSWORD)])
def test_login_wrong_credentials_same_message(client, email, password):
    register(client)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401
    assert r.json()["error"] == {"code": "invalid_credentials", "message": "Incorrect email or password.", "details": []}


def test_login_rate_limited_after_failures(client):
    register(client)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": "nope-nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


def test_disabled_account_cannot_login_or_use_token(client, make_staff):
    customer = register(client)
    admin = make_staff("admin", "admin@example.com")
    assert client.patch(f"/api/admin/users/{customer['user']['id']}", json={"is_active": False}, headers=auth(admin)).status_code == 200
    assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 403
    assert client.get("/api/auth/me", headers=auth(customer)).status_code == 401  # old token stops working too


# ---------- Tokens ----------


def test_protected_endpoints_reject_unauthenticated(client):
    for method, url in [
        ("get", "/api/auth/me"),
        ("get", "/api/repair-requests"),
        ("post", "/api/repair-requests/abc/diagnosis"),
        ("get", "/api/technician/overview"),
        ("get", "/api/admin/users"),
        ("get", "/api/admin/repair-requests"),
    ]:
        r = getattr(client, method)(url)
        assert r.status_code == 401, url
        assert r.json()["error"]["code"] == "not_authenticated"
        assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("bad", ["garbage", "Bearer", "a.b.c"])
def test_invalid_tokens_rejected(client, bad):
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_token_signed_with_other_secret_rejected(client):
    user = register(client)["user"]
    forged = jwt.encode({"sub": user["id"], "role": "admin", "type": "access", "iat": int(time.time()), "exp": int(time.time()) + 600}, "wrong-secret-" + "y" * 40, algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_unsigned_alg_none_token_rejected(client):
    user = register(client)["user"]
    token = jwt.encode({"sub": user["id"], "role": "admin", "type": "access", "iat": int(time.time()), "exp": int(time.time()) + 600}, None, algorithm="none")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_token_rejected(client):
    user = register(client)["user"]
    secret = client.app.state.jwt_secret
    token = jwt.encode({"sub": user["id"], "role": "customer", "type": "access", "iat": int(time.time()) - 7200, "exp": int(time.time()) - 60}, secret, algorithm="HS256")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "expired" in r.json()["error"]["message"]


def test_role_in_token_is_not_trusted(client):
    """Even a correctly-signed token claiming 'admin' only gets the role stored in the database."""
    user = register(client)["user"]
    secret = client.app.state.jwt_secret
    token = jwt.encode({"sub": user["id"], "role": "admin", "type": "access", "iat": int(time.time()), "exp": int(time.time()) + 600}, secret, algorithm="HS256")
    assert client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_tokens_survive_restart_when_secret_configured(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as c1:
        token = register(c1)
    with TestClient(create_app(settings)) as c2:
        assert c2.get("/api/auth/me", headers=auth(token)).status_code == 200


# ---------- Privacy: customers can't see each other's requests ----------


def test_owned_request_private_to_owner(client):
    asha = register(client, "asha@example.com")
    ravi = register(client, "ravi@example.com", "Ravi")
    created = create_request(client, auth(asha)).json()
    assert created["owned_by_account"] is True
    rid = created["request_id"]

    assert client.get(f"/api/repair-requests/{rid}", headers=auth(asha)).status_code == 200
    # Another customer and anonymous visitors get 404 (existence not revealed)
    assert client.get(f"/api/repair-requests/{rid}", headers=auth(ravi)).status_code == 404
    assert client.get(f"/api/repair-requests/{rid}").status_code == 404
    # Nor can they diagnose it
    assert client.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(ravi)).status_code == 404


def test_history_lists_only_own_requests(client):
    asha = register(client, "asha@example.com")
    ravi = register(client, "ravi@example.com", "Ravi")
    for _ in range(3):
        create_request(client, auth(asha))
    create_request(client, auth(ravi), trade_id="carpentry")
    create_request(client)  # anonymous

    mine = client.get("/api/repair-requests", headers=auth(asha)).json()
    assert mine["total"] == 3 and all(i["trade"]["id"] == "plumbing" for i in mine["items"])
    theirs = client.get("/api/repair-requests", headers=auth(ravi)).json()
    assert theirs["total"] == 1 and theirs["items"][0]["trade"]["id"] == "carpentry"


def test_history_pagination(client):
    asha = register(client)
    for _ in range(5):
        create_request(client, auth(asha))
    page = client.get("/api/repair-requests?limit=2&offset=4", headers=auth(asha)).json()
    assert page["total"] == 5 and len(page["items"]) == 1


def test_invalid_token_on_create_is_rejected_not_silently_anonymous(client):
    r = create_request(client, {"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


# ---------- Roles ----------


def test_customer_cannot_use_admin_or_technician_endpoints(client):
    customer = register(client)
    for url in ["/api/admin/users", "/api/admin/repair-requests", "/api/technician/overview"]:
        r = client.get(url, headers=auth(customer))
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    r = client.post("/api/admin/users", json={"email": "t@example.com", "password": PASSWORD, "full_name": "T", "role": "technician"}, headers=auth(customer))
    assert r.status_code == 403


def test_technician_access(client, make_staff):
    asha = register(client)
    rid = create_request(client, auth(asha)).json()["request_id"]
    tech = make_staff("technician", "tech@example.com")
    overview = client.get("/api/technician/overview", headers=auth(tech))
    assert overview.status_code == 200
    assert overview.json()["assigned_jobs"] == [] and "Create your technician profile" in overview.json()["message"]
    # Technicians can't read customers' private data or admin endpoints
    assert client.get(f"/api/repair-requests/{rid}", headers=auth(tech)).status_code == 404
    assert client.get("/api/repair-requests", headers=auth(tech)).status_code == 403
    assert client.get("/api/admin/users", headers=auth(tech)).status_code == 403


def test_admin_access(client, make_staff):
    asha = register(client)
    rid = create_request(client, auth(asha)).json()["request_id"]
    admin = make_staff("admin", "admin@example.com")
    assert client.get(f"/api/repair-requests/{rid}", headers=auth(admin)).status_code == 200
    assert client.get("/api/admin/repair-requests", headers=auth(admin)).json()["total"] == 1
    users = client.get("/api/admin/users", headers=auth(admin)).json()
    assert users["total"] == 2 and "password_hash" not in str(users)

    r = client.post("/api/admin/users", json={"email": "tech@example.com", "password": PASSWORD, "full_name": "Tech", "role": "technician"}, headers=auth(admin))
    assert r.status_code == 201 and r.json()["role"] == "technician"
    tech_login = client.post("/api/auth/login", json={"email": "tech@example.com", "password": PASSWORD})
    assert tech_login.json()["user"]["role"] == "technician"
    assert client.post("/api/admin/users", json={"email": "tech@example.com", "password": PASSWORD, "full_name": "Dup", "role": "technician"}, headers=auth(admin)).status_code == 409
    assert client.post("/api/admin/users", json={"email": "c@example.com", "password": PASSWORD, "full_name": "C", "role": "customer"}, headers=auth(admin)).status_code == 422
    # Admin can't lock themselves out
    me = client.get("/api/auth/me", headers=auth(admin)).json()
    assert client.patch(f"/api/admin/users/{me['id']}", json={"is_active": False}, headers=auth(admin)).status_code == 400


# ---------- Initial admin via CLI ----------


def test_cli_create_admin(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    monkeypatch.setattr("app.cli.get_settings", lambda: settings)
    assert create_admin("boss@example.com", "The Boss", "short") == 1  # weak password rejected
    assert create_admin("boss@example.com", "The Boss", PASSWORD) == 0
    assert create_admin("boss@example.com", "The Boss", PASSWORD) == 1  # already exists
    with TestClient(create_app(settings)) as c:
        token = c.post("/api/auth/login", json={"email": "boss@example.com", "password": PASSWORD}).json()
        assert token["user"]["role"] == "admin"
        assert c.get("/api/admin/users", headers=auth(token)).status_code == 200


def test_production_requires_jwt_secret(tmp_path):
    with pytest.raises(ValueError, match="MENDORA_JWT_SECRET"):
        make_settings(tmp_path, environment="production", jwt_secret=None)


def test_placeholder_secrets_from_env_example_are_not_used(tmp_path):
    settings = make_settings(tmp_path, jwt_secret="replace-with-a-long-random-secret", anthropic_api_key="your-anthropic-api-key-here")
    assert settings.usable_jwt_secret is None
    assert settings.ai_api_key is None
    app = create_app(settings)
    assert app.state.jwt_secret != "replace-with-a-long-random-secret"
    with pytest.raises(ValueError):
        make_settings(tmp_path, environment="production", jwt_secret="replace-with-a-long-random-secret-1234567890")
