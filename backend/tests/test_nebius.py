"""Nebius Token Factory provider (OpenAI-compatible). Uses a SIMULATED transport — no real Nebius call is made here."""

import json

import pytest
from fastapi.testclient import TestClient

from app.ai.http import HttpResponse
from app.cli import check_ai
from app.main import create_app
from conftest import GOOD_MODEL_OUTPUT, FakeTransport, auth, create_request, make_settings, register

KEY = "nebius-test-key-1234567890"


def nebius_body(content: str, finish_reason: str = "stop") -> str:
    return json.dumps({"id": "chatcmpl-test", "object": "chat.completion", "model": "openai/gpt-oss-120b",
                       "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}]})


def nebius_settings(tmp_path, **over):
    return make_settings(tmp_path, ai_provider="nebius", nebius_api_key=KEY, anthropic_api_key=None, **over)


@pytest.fixture
def neb(tmp_path):
    fake = FakeTransport()
    with TestClient(create_app(nebius_settings(tmp_path), fake)) as c:
        yield c, fake


def diagnose(c, token, rid):
    return c.post(f"/api/repair-requests/{rid}/diagnosis", json={"follow_up_answers": []}, headers=auth(token))


def test_health_shows_nebius_configured(neb):
    c, _ = neb
    assert c.get("/api/health").json()["ai_diagnosis"] == {"provider": "nebius", "model": "openai/gpt-oss-120b", "configured": True}


def test_request_format_and_successful_diagnosis(neb):
    c, fake = neb
    fake.queue.append(HttpResponse(200, nebius_body(json.dumps(GOOD_MODEL_OUTPUT)), {}))
    token = register(c)
    rid = create_request(c, auth(token), description="Sink drains slowly. Call me on 9876543210 or mail asha@example.com").json()["request_id"]
    r = diagnose(c, token, rid)
    assert r.status_code == 200, r.text
    d = r.json()["diagnosis"]
    assert d["provider"] == "nebius" and d["model"] == "openai/gpt-oss-120b" and d["source"] == "ai"
    call = fake.calls[0]
    assert call["url"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    p = call["payload"]
    assert p["model"] == "openai/gpt-oss-120b" and p["max_tokens"] >= 4000 and "max_completion_tokens" not in p
    assert p["response_format"]["type"] == "json_schema" and p["response_format"]["json_schema"]["strict"] is True
    sent = json.dumps(p["messages"])
    assert "9876543210" not in sent and "asha@example.com" not in sent  # personal details removed


@pytest.mark.parametrize(
    "content",
    [
        "<think>The user has a slow drain…</think>" + json.dumps(GOOD_MODEL_OUTPUT),
        "```json\n" + json.dumps(GOOD_MODEL_OUTPUT) + "\n```",
        "Here is the assessment:\n" + json.dumps(GOOD_MODEL_OUTPUT),
    ],
)
def test_tolerates_wrapped_json(neb, content):
    c, fake = neb
    fake.queue.append(HttpResponse(200, nebius_body(content), {}))
    token = register(c)
    rid = create_request(c, auth(token)).json()["request_id"]
    assert diagnose(c, token, rid).status_code == 200


@pytest.mark.parametrize(
    "response, code",
    [
        (HttpResponse(200, nebius_body("I can't produce JSON, sorry."), {}), "ai_invalid_response"),
        (HttpResponse(200, nebius_body(json.dumps({"summary": "x"})), {}), "ai_invalid_response"),  # fails validation
        (HttpResponse(200, nebius_body("{", "length"), {}), "ai_invalid_response"),
        (HttpResponse(401, '{"detail":"Invalid API key"}', {}), "ai_provider_error"),
        (HttpResponse(404, '{"detail":"model not found"}', {}), "ai_provider_error"),
        (HttpResponse(429, '{"detail":"rate limit"}', {}), "ai_rate_limited"),
    ],
)
def test_failures_never_invent_a_result(neb, response, code):
    c, fake = neb
    fake.queue.append(response)
    token = register(c)
    rid = create_request(c, auth(token)).json()["request_id"]
    r = diagnose(c, token, rid)
    assert r.status_code >= 400 and r.json()["error"]["code"] == code, r.text
    assert c.get(f"/api/repair-requests/{rid}", headers=auth(token)).json()["diagnosis"] is None


def test_high_risk_never_reaches_nebius(neb):
    c, fake = neb
    token = register(c)
    rid = create_request(c, auth(token), trade_id="electrical", description="Sparks come out of the socket when I plug in the kettle.").json()["request_id"]
    assert diagnose(c, token, rid).status_code == 409
    assert fake.calls == []


@pytest.mark.parametrize("key", [None, "", "your-nebius-api-key-here"])
def test_missing_or_placeholder_key_means_not_configured(tmp_path, key):
    s = make_settings(tmp_path, ai_provider="nebius", nebius_api_key=key, anthropic_api_key=None)
    fake = FakeTransport()
    with TestClient(create_app(s, fake)) as c:
        assert c.get("/api/health").json()["ai_diagnosis"]["configured"] is False
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        assert diagnose(c, token, rid).json()["error"]["code"] == "ai_not_configured"
        assert fake.calls == []


def test_key_read_from_NEBIUS_API_KEY(tmp_path, monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("NEBIUS_API_KEY", KEY)
    s = Settings(_env_file=None, ai_provider="nebius", database_url=f"sqlite:///{tmp_path}/x.db")
    assert s.ai_api_key == KEY


def test_custom_model_and_base_url(tmp_path):
    fake = FakeTransport()
    fake.queue.append(HttpResponse(200, nebius_body(json.dumps(GOOD_MODEL_OUTPUT)), {}))
    s = nebius_settings(tmp_path, ai_model="Qwen/Qwen3-235B-A22B", ai_base_url="https://api.tokenfactory.nebius.com/v1/")
    with TestClient(create_app(s, fake)) as c:
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        assert diagnose(c, token, rid).json()["diagnosis"]["model"] == "Qwen/Qwen3-235B-A22B"
    assert fake.calls[0]["url"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"


# ---------- python -m app.cli check-ai ----------


def test_check_ai_success_and_never_prints_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("app.cli.get_settings", lambda: nebius_settings(tmp_path))
    fake = FakeTransport()
    fake.queue.append(HttpResponse(200, nebius_body(json.dumps(GOOD_MODEL_OUTPUT)), {}))
    assert check_ai(transport=fake) == 0
    out = capsys.readouterr()
    assert "Result: WORKING" in out.out and "openai/gpt-oss-120b" in out.out
    assert KEY not in out.out + out.err


def test_check_ai_reports_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("app.cli.get_settings", lambda: nebius_settings(tmp_path))
    fake = FakeTransport()
    fake.queue.append(HttpResponse(401, '{"detail":"Invalid API key"}', {}))
    assert check_ai(transport=fake) == 1
    out = capsys.readouterr()
    assert "Result: FAILED" in out.err and "rejected the API key" in out.err and KEY not in out.out + out.err


def test_check_ai_not_configured(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("app.cli.get_settings", lambda: make_settings(tmp_path, ai_provider="nebius", nebius_api_key=None))
    assert check_ai(transport=FakeTransport()) == 1
    assert "NOT CONFIGURED" in capsys.readouterr().err
