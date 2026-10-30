"""
Shared test setup.

- Every test gets a fresh temporary SQLite database.
- The AI provider is replaced by `FakeTransport`, which returns canned HTTP responses
  in the real provider formats. Tests NEVER call a real AI API.
"""

import json
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.ai.http import HttpResponse
from app.config import Settings
from app.main import create_app
from app.security import hash_password

VALID_DESCRIPTION = "The kitchen sink drains very slowly and gurgles. It started two days ago."
PASSWORD = "correct-horse-battery"

GOOD_MODEL_OUTPUT = {
    "summary": "Your kitchen sink is draining slowly and making gurgling sounds.",
    "possible_causes": [
        {"title": "Partial clog in the trap", "explanation": "Grease or food can build up in the U-bend under the sink."},
        {"title": "Blocked vent pipe", "explanation": "Gurgling can happen when the drain vent is restricted."},
    ],
    "follow_up_questions": ["Are other drains in the house also slow?"],
    "recommended_next_step": "Check whether other sinks or the shower are also draining slowly.",
    "professional_recommended": False,
    "professional_reason": "",
    "urgent_danger": False,
}


def anthropic_body(tool_input: dict | None = None, *, stop_reason: str = "tool_use", content: list | None = None) -> str:
    if content is None:
        content = [{"type": "tool_use", "id": "toolu_test", "name": "submit_diagnosis", "input": tool_input or GOOD_MODEL_OUTPUT}]
    return json.dumps(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    )


class FakeTransport:
    """Stands in for the network. Queue responses (or exceptions); it records every call."""

    def __init__(self) -> None:
        self.queue: list[HttpResponse | Exception] = []
        self.calls: list[dict] = []

    def add(self, status: int = 200, body: str | None = None, headers: dict | None = None) -> "FakeTransport":
        self.queue.append(HttpResponse(status, body if body is not None else anthropic_body(), headers or {}))
        return self

    def add_error(self, exc: Exception) -> "FakeTransport":
        self.queue.append(exc)
        return self

    def __call__(self, url: str, headers: dict, body: bytes, timeout: float) -> HttpResponse:
        self.calls.append({"url": url, "headers": headers, "payload": json.loads(body), "timeout": timeout})
        if not self.queue:
            raise AssertionError("FakeTransport called but no response queued")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_settings(tmp_path, **overrides) -> Settings:
    values = {
        "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "upload_dir": tmp_path / "uploads",
        "jwt_secret": "test-secret-" + "x" * 48,
        "environment": "test",
        "ai_provider": "anthropic",
        "anthropic_api_key": "test-key-not-real",
        "openai_api_key": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def fake_ai() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings, fake_ai) -> TestClient:
    with TestClient(create_app(settings, fake_ai)) as c:
        yield c


def register(client: TestClient, email: str = "asha@example.com", name: str = "Asha Kumar") -> dict:
    r = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def auth(token_response: dict) -> dict:
    return {"Authorization": f"Bearer {token_response['access_token']}"}


def create_request(client: TestClient, headers: dict | None = None, trade_id: str = "plumbing", description: str = VALID_DESCRIPTION):
    return client.post("/api/repair-requests", json={"trade_id": trade_id, "description": description}, headers=headers or {})


@pytest.fixture
def make_staff(client) -> Callable[..., dict]:
    """Create a technician/admin directly in the DB (as the CLI would), then log in."""

    def _make(role: str, email: str) -> dict:
        from app.repositories import users as users_repo

        with client.app.state.session_factory() as db:
            users_repo.create(db, email=email, full_name=f"Test {role}", password_hash=hash_password(PASSWORD), role=role)
        r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return r.json()

    return _make
