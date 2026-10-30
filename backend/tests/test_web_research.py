"""AI web research via Tavily — SIMULATED transport (no real Tavily call is made in tests)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.ai.http import HttpResponse
from app.cli import check_web_research
from app.main import create_app
from conftest import FakeTransport, auth, create_request, make_settings, register

KEY = "tvly-dev-test-key-0123456789"
LOW = "The kitchen sink drains very slowly and gurgles. Call me on 9876543210 or mail asha@example.com"
MEDIUM = "My water heater makes a loud banging noise when it heats up."
HIGH = "Sparks come out of the kitchen socket when I plug in the kettle."


def tavily_body(answer="A slow, gurgling sink is often a partial clog in the trap. Check whether other drains are slow too.", results=None):
    if results is None:
        results = [
            {"title": "Why your sink gurgles", "url": "https://www.example-plumbing.com/gurgle", "content": "Gurgling usually means air is trapped. A partial clog is common.", "score": 0.9},
            {"title": "Slow drains", "url": "https://diy.example.org/slow-drain", "content": "Remove standing water first.", "score": 0.8},
        ]
    return json.dumps({"query": "x", "answer": answer, "results": results, "response_time": 1.2})


@pytest.fixture
def web(tmp_path):
    fake = FakeTransport()
    with TestClient(create_app(make_settings(tmp_path, tavily_api_key=KEY), fake)) as c:
        yield c, fake


def run(c, token, rid):
    return c.post(f"/api/repair-requests/{rid}/web-research", headers=auth(token))


def test_health_reports_web_research(web):
    c, _ = web
    assert c.get("/api/health").json()["web_research"] == {"provider": "tavily", "configured": True}


def test_low_risk_returns_summary_and_sources(web):
    c, fake = web
    fake.queue.append(HttpResponse(200, tavily_body(), {}))
    token = register(c)
    rid = create_request(c, auth(token), description=LOW).json()["request_id"]
    r = run(c, token, rid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "tavily" and body["mode"] == "full"
    assert "partial clog" in body["answer"]
    assert [s["domain"] for s in body["sources"]] == ["example-plumbing.com", "diy.example.org"]
    assert "isn't a diagnosis" in body["disclaimer"]
    # what was sent: trade + description only, personal details removed, key in header
    call = fake.calls[0]
    assert call["url"] == "https://api.tavily.com/search"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["payload"]["include_answer"] is True and call["payload"]["max_results"] == 5
    assert "9876543210" not in call["payload"]["query"] and "asha@example.com" not in call["payload"]["query"]
    assert body["query_sent"] == call["payload"]["query"] and KEY not in r.text


def test_unsafe_sentences_are_removed(web):
    c, fake = web
    answer = "A slow drain is often a clog in the trap. Remove the cover plate and touch the live wires to test them. Ask a plumber if unsure."
    fake.queue.append(HttpResponse(200, tavily_body(answer=answer), {}))
    token = register(c)
    rid = create_request(c, auth(token), description=LOW).json()["request_id"]
    body = run(c, token, rid).json()
    assert "live wires" not in body["answer"] and "clog in the trap" in body["answer"]
    assert body["safety_filter_applied"] is True and "removed" in body["answer_note"]


def test_medium_risk_gets_links_only(web):
    c, fake = web
    fake.queue.append(HttpResponse(200, tavily_body(), {}))
    token = register(c)
    req = create_request(c, auth(token), description=MEDIUM).json()
    assert req["safety"]["risk_level"] == "medium"
    body = run(c, token, req["request_id"]).json()
    assert body["mode"] == "sources_only" and body["answer"] is None
    assert all(s["snippet"] is None for s in body["sources"]) and "only links" in body["answer_note"]
    assert fake.calls[0]["payload"]["include_answer"] is False


def test_high_risk_never_searches(web):
    c, fake = web
    token = register(c)
    rid = create_request(c, auth(token), trade_id="electrical", description=HIGH).json()["request_id"]
    r = run(c, token, rid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "blocked_by_safety"
    assert fake.calls == []


def test_bad_links_are_dropped(web):
    c, fake = web
    fake.queue.append(HttpResponse(200, tavily_body(results=[
        {"title": "evil", "url": "javascript:alert(1)", "content": "x"},
        {"title": "ok", "url": "https://good.example.com/a", "content": "fine"},
    ]), {}))
    token = register(c)
    rid = create_request(c, auth(token), description=LOW).json()["request_id"]
    assert [s["url"] for s in run(c, token, rid).json()["sources"]] == ["https://good.example.com/a"]


@pytest.mark.parametrize("status, code", [(401, "ai_provider_error"), (429, "ai_rate_limited"), (432, "ai_rate_limited"), (500, "ai_provider_error")])
def test_errors_are_reported_not_invented(web, status, code):
    c, fake = web
    fake.queue.extend([HttpResponse(status, '{"detail":{"error":"x"}}', {})] * 2)
    token = register(c)
    rid = create_request(c, auth(token), description=LOW).json()["request_id"]
    r = run(c, token, rid)
    assert r.status_code >= 400 and r.json()["error"]["code"] == code
    assert KEY not in r.text


def test_not_configured(tmp_path):
    fake = FakeTransport()
    with TestClient(create_app(make_settings(tmp_path, tavily_api_key=None), fake)) as c:
        assert c.get("/api/health").json()["web_research"]["configured"] is False
        token = register(c)
        rid = create_request(c, auth(token), description=LOW).json()["request_id"]
        r = run(c, token, rid)
        assert r.status_code == 503 and r.json()["error"]["code"] == "web_research_not_configured"
        assert fake.calls == []


def test_permissions(web):
    c, _ = web
    owner = register(c)
    rid = create_request(c, auth(owner), description=LOW).json()["request_id"]
    other = register(c, "other@example.com", "Other Person")
    assert run(c, other, rid).status_code == 404
    assert c.post(f"/api/repair-requests/{rid}/web-research").status_code == 401


def test_ai_diagnosis_unchanged_and_separate(tmp_path):
    """A Tavily key does not make the AI diagnosis 'configured' — they are different services."""
    with TestClient(create_app(make_settings(tmp_path, tavily_api_key=KEY, anthropic_api_key=None))) as c:
        h = c.get("/api/health").json()
        assert h["ai_diagnosis"]["configured"] is False and h["web_research"]["configured"] is True


def test_check_web_research_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("app.cli.get_settings", lambda: make_settings(tmp_path, tavily_api_key=KEY))
    fake = FakeTransport()
    fake.queue.append(HttpResponse(200, tavily_body(), {}))
    assert check_web_research(transport=fake) == 0
    out = capsys.readouterr()
    assert "Result: WORKING" in out.out and KEY not in out.out + out.err
    fake.queue.append(HttpResponse(401, '{"detail":"Unauthorized"}', {}))
    assert check_web_research(transport=fake) == 1
    assert "Result: FAILED" in capsys.readouterr().err


# ---------- separate test settings file (MENDORA_ENV_FILE) ----------


def test_env_file_switch(tmp_path, monkeypatch):
    from app.config import BACKEND_DIR, env_file_path, get_settings

    monkeypatch.delenv("MENDORA_ENV_FILE", raising=False)
    assert env_file_path() == BACKEND_DIR / ".env"
    test_file = tmp_path / ".env.tavily-test"
    test_file.write_text(f"MENDORA_AI_PROVIDER=none\nTAVILY_API_KEY={KEY}\nMENDORA_DATABASE_URL=sqlite:///{tmp_path}/t.db\n")
    monkeypatch.setenv("MENDORA_ENV_FILE", str(test_file))
    get_settings.cache_clear()
    s = get_settings()
    assert s.tavily_key == KEY and s.ai_provider == "none"
    monkeypatch.setenv("MENDORA_ENV_FILE", str(tmp_path / "missing.env"))
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="doesn't exist"):
        get_settings()
    get_settings.cache_clear()
