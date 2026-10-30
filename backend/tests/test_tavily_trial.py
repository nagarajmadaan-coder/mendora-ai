"""Tavily TRIAL diagnosis mode (MENDORA_AI_PROVIDER=tavily) — SIMULATED transport, no real Tavily call."""

import json

import pytest
from fastapi.testclient import TestClient

from app.ai.http import HttpResponse
from app.cli import check_ai
from app.config import get_settings
from app.main import create_app
from conftest import FakeTransport, auth, create_request, make_settings, register

KEY = "tvly-dev-test-key-0123456789"
LOW = "The kitchen sink drains very slowly and gurgles. Call me on 9876543210 or mail asha@example.com"
MEDIUM = "My water heater makes a loud banging noise when it heats up."
HIGH = "Sparks come out of the kitchen socket when I plug in the kettle."


def body(answer="A slow, gurgling sink is often a partial clog in the trap. It can also be a blocked vent.", results=None):
    if results is None:
        results = [
            {"title": "Why your sink gurgles", "url": "https://www.example-plumbing.com/gurgle", "content": "x"},
            {"title": "Bad", "url": "javascript:alert(1)", "content": "x"},
        ]
    return json.dumps({"answer": answer, "results": results})


def settings(tmp_path, **kw):
    return make_settings(tmp_path, ai_provider="tavily", anthropic_api_key=None, tavily_api_key=KEY, **kw)


@pytest.fixture
def trial(tmp_path):
    fake = FakeTransport()
    with TestClient(create_app(settings(tmp_path), fake)) as c:
        yield c, fake


def diagnose(c, token, rid):
    return c.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(token), json={})


def test_health_shows_trial_configured(trial):
    c, _ = trial
    ai = c.get("/api/health").json()["ai_diagnosis"]
    assert ai["provider"] == "tavily" and ai["configured"] is True


def test_low_risk_trial_diagnosis_is_labelled_and_has_no_invented_causes(trial):
    c, fake = trial
    fake.queue.append(HttpResponse(200, body(), {}))
    token = register(c)
    rid = create_request(c, auth(token), description=LOW).json()["request_id"]
    r = diagnose(c, token, rid)
    assert r.status_code == 200, r.text
    d = r.json()["diagnosis"]
    assert d["trial"] is True and d["provider"] == "tavily" and d["model"] == "tavily-search (trial)"
    assert "partial clog" in d["summary"]
    assert d["possible_causes"] == [] and d["follow_up_questions"] == []
    assert "TRIAL MODE" in d["disclaimer"]
    assert [s["domain"] for s in d["sources"]] == ["example-plumbing.com"]  # javascript: link dropped
    p = fake.calls[0]["payload"]
    assert "9876543210" not in p["query"] and "asha@example.com" not in p["query"]
    assert p["include_answer"] == "advanced"
    assert fake.calls[0]["headers"]["Authorization"] == f"Bearer {KEY}"


def test_unsafe_sentence_removed_from_trial_summary(trial):
    c, fake = trial
    fake.queue.append(HttpResponse(200, body("It may be a clog. Remove the cover plate and touch the live wire to test it."), {}))
    token = register(c)
    rid = create_request(c, auth(token), description=LOW).json()["request_id"]
    d = diagnose(c, token, rid).json()["diagnosis"]
    assert "live wire" not in d["summary"] and d["safety_filter_applied"] is True


def test_medium_risk_trial_shows_no_web_text(trial):
    c, fake = trial
    fake.queue.append(HttpResponse(200, body(answer=None), {}))
    token = register(c)
    rid = create_request(c, auth(token), description=MEDIUM).json()["request_id"]
    r = diagnose(c, token, rid)
    assert r.status_code == 200, r.text
    d = r.json()["diagnosis"]
    assert d["safety_mode"] == "professional_only" and d["professional_recommended"] is True
    assert "doesn't show any web text" in d["summary"]
    assert fake.calls[0]["payload"]["include_answer"] is False


def test_high_risk_never_calls_tavily(trial):
    c, fake = trial
    token = register(c)
    rid = create_request(c, auth(token), description=HIGH).json()["request_id"]
    assert diagnose(c, token, rid).status_code == 409
    assert fake.calls == []


def test_no_summary_is_an_error_not_a_made_up_answer(trial):
    c, fake = trial
    fake.queue.append(HttpResponse(200, body(answer=""), {}))
    token = register(c)
    rid = create_request(c, auth(token), description=LOW).json()["request_id"]
    r = diagnose(c, token, rid)
    assert r.status_code >= 500 and "diagnosis" not in r.json()


def test_no_tavily_key_is_not_configured(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, ai_provider="tavily", anthropic_api_key=None, tavily_api_key=None), FakeTransport())) as c:
        token = register(c)
        rid = create_request(c, auth(token), description=LOW).json()["request_id"]
        r = diagnose(c, token, rid)
        assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured"


def test_check_ai_reports_trial(tmp_path, monkeypatch, capsys):
    fake = FakeTransport()
    fake.queue.append(HttpResponse(200, body(), {}))
    monkeypatch.setattr("app.cli.get_settings", lambda: settings(tmp_path))
    assert check_ai(transport=fake) == 0
    out = capsys.readouterr().out
    assert "WORKING (TRIAL)" in out and KEY not in out
