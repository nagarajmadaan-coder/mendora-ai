"""
Core API tests (from Step 3), now running against a temporary SQLite database.

Run from the `backend` folder:
    python -m pytest -v
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import VALID_DESCRIPTION, make_settings

FRONTEND_ORIGIN = "http://localhost:5173"


def create(client: TestClient, trade_id="plumbing", description=VALID_DESCRIPTION):
    return client.post("/api/repair-requests", json={"trade_id": trade_id, "description": description})


def error_fields(response) -> list:
    return [d["field"] for d in response.json()["error"]["details"]]


# ---------- Health ----------


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["message"] == "MENDORA API is running."
    assert body["storage"] == "database"
    assert body["ai_diagnosis"] == {"provider": "anthropic", "model": "claude-sonnet-5-5", "configured": True}


# ---------- Trades ----------


def test_trades_lists_all_three(client):
    r = client.get("/api/trades")
    assert r.status_code == 200
    assert r.json() == {
        "trades": [
            {"id": "plumbing", "name": "Plumbing"},
            {"id": "electrical", "name": "Electrical"},
            {"id": "carpentry", "name": "Carpentry"},
        ]
    }


# ---------- Create ----------


@pytest.mark.parametrize("trade_id,name", [("plumbing", "Plumbing"), ("electrical", "Electrical"), ("carpentry", "Carpentry")])
def test_create_for_each_trade(client, trade_id, name):
    r = create(client, trade_id)
    assert r.status_code == 201
    body = r.json()
    uuid.UUID(body["request_id"])  # raises if not a valid UUID
    assert body["status"] == "accepted"
    assert body["trade"] == {"id": trade_id, "name": name}
    assert body["description"] == VALID_DESCRIPTION
    assert r.headers["location"] == f"/api/repair-requests/{body['request_id']}"


def test_create_does_not_diagnose(client, fake_ai):
    body = create(client).json()
    assert body["diagnosis_status"] == "not_started"
    assert body["diagnosis"] is None
    assert body["owned_by_account"] is False
    assert "Check the safety result" in body["message"]
    assert body["safety"]["risk_level"] == "low" and body["safety"]["allow_diy"] is True
    assert "can miss things" in body["safety_notice"]
    assert fake_ai.calls == []  # creating a request never calls the AI


def test_request_ids_are_unique(client):
    ids = {create(client).json()["request_id"] for _ in range(25)}
    assert len(ids) == 25


def test_trade_id_is_normalised(client):
    r = create(client, "  Electrical ")
    assert r.status_code == 201
    assert r.json()["trade"]["id"] == "electrical"


def test_description_is_trimmed(client):
    r = create(client, description=f"   {VALID_DESCRIPTION}   \n")
    assert r.json()["description"] == VALID_DESCRIPTION


# ---------- Create: validation errors ----------


@pytest.mark.parametrize("bad_trade", ["roofing", "", "PLUMBER", "123"])
def test_unsupported_trade(client, bad_trade):
    r = create(client, bad_trade)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert error_fields(r) == ["trade_id"]
    assert "Supported values: plumbing, electrical, carpentry" in err["details"][0]["message"]


@pytest.mark.parametrize("empty", ["", "   ", "\n\t  "])
def test_empty_description(client, empty):
    r = create(client, description=empty)
    assert r.status_code == 422
    assert error_fields(r) == ["description"]
    assert r.json()["error"]["details"][0]["message"] == "Description must not be empty."


def test_too_short_description(client):
    r = create(client, description="it leaks")
    assert r.status_code == 422
    assert "too short" in r.json()["error"]["details"][0]["message"]


def test_too_long_description(client):
    r = create(client, description="x" * 1001)
    assert r.status_code == 422
    assert "too long" in r.json()["error"]["details"][0]["message"]


def test_both_fields_invalid_reports_both(client):
    r = create(client, "roofing", "")
    assert r.status_code == 422
    assert sorted(error_fields(r)) == ["description", "trade_id"]


def test_missing_fields(client):
    r = client.post("/api/repair-requests", json={})
    assert r.status_code == 422
    assert sorted(error_fields(r)) == ["description", "trade_id"]
    assert all(d["message"] == "Field required" for d in r.json()["error"]["details"])


def test_unknown_field_rejected(client):
    r = client.post("/api/repair-requests", json={"trade_id": "plumbing", "description": VALID_DESCRIPTION, "price": 5})
    assert r.status_code == 422
    assert error_fields(r) == ["price"]


def test_wrong_types(client):
    r = client.post("/api/repair-requests", json={"trade_id": 7, "description": ["a"]})
    assert r.status_code == 422
    assert sorted(error_fields(r)) == ["description", "trade_id"]


def test_invalid_json(client):
    r = client.post("/api/repair-requests", content="{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["message"] == "The request body is not valid JSON."


def test_rejected_request_is_not_stored(client):
    from app.models import RepairRequest

    create(client, "roofing")
    with client.app.state.session_factory() as db:
        assert db.query(RepairRequest).count() == 0


# ---------- Retrieve ----------


def test_get_existing_request(client):
    created = create(client, "carpentry").json()
    r = client.get(f"/api/repair-requests/{created['request_id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_unknown_request_404(client):
    missing = str(uuid.uuid4())
    r = client.get(f"/api/repair-requests/{missing}")
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "repair_request_not_found",
        "message": f"No repair request found with ID '{missing}'.",
        "details": [],
    }


def test_get_malformed_id_404(client):
    assert client.get("/api/repair-requests/not-a-real-id").status_code == 404


def test_requests_survive_restart(tmp_path):
    """Step 4: data is in a database file, so a new app instance (= a server restart) still has it."""
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as first:
        created = create(first).json()
    with TestClient(create_app(settings)) as restarted:
        r = restarted.get(f"/api/repair-requests/{created['request_id']}")
    assert r.status_code == 200
    assert r.json()["description"] == VALID_DESCRIPTION


# ---------- Other errors use the same shape ----------


def test_unknown_url_uses_error_shape(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_wrong_method(client):
    r = client.delete("/api/trades")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


# ---------- CORS ----------


def test_cors_allows_frontend_dev_origin(client):
    r = client.options(
        "/api/repair-requests",
        headers={"Origin": FRONTEND_ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


def test_cors_header_on_normal_request(client):
    r = client.get("/api/health", headers={"Origin": FRONTEND_ORIGIN})
    assert r.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


def test_cors_blocks_unknown_origin(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_allows_authorization_header(client):
    r = client.options(
        "/api/auth/me",
        headers={"Origin": FRONTEND_ORIGIN, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"},
    )
    assert r.status_code == 200
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


def test_cors_origins_configurable(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, cors_origins="https://mendora.example/ , http://localhost:3000")))
    assert c.get("/api/health", headers={"Origin": "https://mendora.example"}).headers["access-control-allow-origin"] == "https://mendora.example"
    assert "access-control-allow-origin" not in c.get("/api/health", headers={"Origin": FRONTEND_ORIGIN}).headers


# ---------- Docs ----------


def test_docs_and_schema_available(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert {"/api/health", "/api/trades", "/api/repair-requests", "/api/repair-requests/{request_id}",
            "/api/repair-requests/{request_id}/diagnosis", "/api/auth/register", "/api/auth/login", "/api/auth/me"} <= set(schema["paths"])
    assert "never invented" in schema["info"]["description"]


def test_root_redirects_to_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/docs"
