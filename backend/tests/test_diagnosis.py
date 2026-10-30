"""
AI diagnosis tests. The provider is simulated with FakeTransport (real response formats),
so these tests prove our handling logic — they do NOT prove a live API key works.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.ai.errors import AITimeout
from app.ai.privacy import redact
from app.main import create_app
from conftest import GOOD_MODEL_OUTPUT, anthropic_body, auth, create_request, make_settings, register


@pytest.fixture
def owned(client):
    """A signed-in customer with one saved request."""
    token = register(client)
    rid = create_request(client, auth(token)).json()["request_id"]
    return token, rid


def diagnose(client, token, rid, answers=None):
    body = {"follow_up_answers": answers} if answers is not None else None
    return client.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(token), json=body)


# ---------- Success ----------


def test_successful_diagnosis_is_returned_and_saved(client, fake_ai, owned):
    token, rid = owned
    fake_ai.add(200, anthropic_body())
    r = diagnose(client, token, rid)
    assert r.status_code == 200, r.text
    body = r.json()
    d = body["diagnosis"]
    assert body["status"] == "diagnosed" and body["diagnosis_status"] == "completed"
    assert d["source"] == "ai"
    assert d["summary"] == GOOD_MODEL_OUTPUT["summary"]
    assert [c["title"] for c in d["possible_causes"]] == ["Partial clog in the trap", "Blocked vent pipe"]
    assert d["follow_up_questions"] == ["Are other drains in the house also slow?"]
    assert d["recommended_next_step"].startswith("Check whether other sinks")
    assert d["professional_recommended"] is False
    assert d["safety_mode"] == "full" and d["safety_filter_applied"] is False
    assert body["safety"]["risk_level"] == "low"
    assert "possibilities, not a confirmed diagnosis" in d["disclaimer"]
    assert d["provider"] == "anthropic" and d["model"] == "claude-sonnet-5-5"

    # Saved: a later GET returns the same diagnosis
    again = client.get(f"/api/repair-requests/{rid}", headers=auth(token)).json()
    assert again["diagnosis"] == d and again["diagnosed_at"] is not None


def test_diagnosis_survives_restart(tmp_path, fake_ai):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, fake_ai)) as c1:
        token = register(c1)
        rid = create_request(c1, auth(token)).json()["request_id"]
        fake_ai.add(200, anthropic_body())
        assert diagnose(c1, token, rid).status_code == 200
    with TestClient(create_app(settings, fake_ai)) as c2:
        body = c2.get(f"/api/repair-requests/{rid}", headers=auth(token)).json()
    assert body["diagnosis"]["source"] == "ai" and body["diagnosis_status"] == "completed"


def test_request_sent_to_anthropic_is_correct_and_minimal(client, fake_ai):
    token = register(client, email="private.person@example.com", name="Private Person")
    desc = "Tap drips all night. Call me on +91 98765 43210 or mail me at me@home.example if needed."
    rid = create_request(client, auth(token), description=desc).json()["request_id"]
    fake_ai.add(200, anthropic_body())
    diagnose(client, token, rid)

    call = fake_ai.calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == "test-key-not-real"
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    p = call["payload"]
    assert p["model"] == "claude-sonnet-5-5"
    assert p["tool_choice"] == {"type": "tool", "name": "submit_diagnosis"}
    assert p["tools"][0]["input_schema"]["required"]
    sent = json.dumps(p)
    # Trade + description are sent...
    assert "<trade>Plumbing</trade>" in sent and "Tap drips all night" in sent
    # ...but no personal data: no name, account email, IDs, or the contact details typed in the description
    for secret in ["Private Person", "private.person@example.com", rid, token["user"]["id"], "98765", "me@home.example"]:
        assert secret not in sent
    assert "[phone removed]" in sent and "[email removed]" in sent


def test_follow_up_answers_sent_and_stored(client, fake_ai, owned):
    token, rid = owned
    fake_ai.add(200, anthropic_body()).add(200, anthropic_body({**GOOD_MODEL_OUTPUT, "follow_up_questions": []}))
    diagnose(client, token, rid)
    answers = [{"question": "Are other drains in the house also slow?", "answer": "No, only the kitchen sink."}]
    r = diagnose(client, token, rid, answers)
    assert r.status_code == 200
    assert "Q: Are other drains in the house also slow?\\nA: No, only the kitchen sink." in json.dumps(fake_ai.calls[1]["payload"])
    with client.app.state.session_factory() as db:
        from app.models import RepairRequest

        assert db.get(RepairRequest, rid).follow_up_answers == answers


@pytest.mark.parametrize(
    "answers",
    [
        [{"question": "", "answer": "x"}],
        [{"question": "q", "answer": "   "}],
        [{"question": "q", "answer": "a" * 501}],
        [{"question": "q", "answer": "a"}] * 6,
        [{"question": "q", "answer": "a", "extra": 1}],
    ],
)
def test_follow_up_validation(client, fake_ai, owned, answers):
    token, rid = owned
    assert diagnose(client, token, rid, answers).status_code == 422
    assert fake_ai.calls == []


def test_model_urgent_flag_escalates_to_high_and_keeps_nothing(client, fake_ai, owned):
    token, rid = owned
    risky = {**GOOD_MODEL_OUTPUT, "urgent_danger": True, "recommended_next_step": "Open the panel and tighten the wire."}
    fake_ai.add(200, anthropic_body(risky))
    body = diagnose(client, token, rid).json()
    assert body["diagnosis"] is None and body["diagnosis_status"] == "blocked_by_safety"
    assert body["safety"]["risk_level"] == "high"
    assert "ai_flagged_danger" in [h["id"] for h in body["safety"]["matched_hazards"]]
    assert "tighten" not in json.dumps(body)
    # Sticky: further attempts are blocked without calling the AI again
    calls = len(fake_ai.calls)
    assert diagnose(client, token, rid).status_code == 409
    assert len(fake_ai.calls) == calls


# ---------- Failures: never a fabricated diagnosis ----------


def _assert_no_diagnosis_saved(client, token, rid, code):
    body = client.get(f"/api/repair-requests/{rid}", headers=auth(token)).json()
    assert body["diagnosis"] is None
    assert body["diagnosis_status"] == "failed"
    assert body["last_diagnosis_error"] == code


def test_missing_api_key(tmp_path, fake_ai):
    settings = make_settings(tmp_path, anthropic_api_key=None)
    with TestClient(create_app(settings, fake_ai)) as c:
        assert c.get("/api/health").json()["ai_diagnosis"]["configured"] is False
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        r = diagnose(c, token, rid)
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "ai_not_configured"
        assert "Your request has been saved" in r.json()["error"]["message"]
        assert fake_ai.calls == []
        _assert_no_diagnosis_saved(c, token, rid, "ai_not_configured")


def test_provider_none(tmp_path, fake_ai):
    with TestClient(create_app(make_settings(tmp_path, ai_provider="none"), fake_ai)) as c:
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        assert diagnose(c, token, rid).json()["error"]["code"] == "ai_not_configured"


def test_openai_without_model_is_not_configured(tmp_path, fake_ai):
    with TestClient(create_app(make_settings(tmp_path, ai_provider="openai", openai_api_key="sk-test"), fake_ai)) as c:
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        assert diagnose(c, token, rid).json()["error"]["code"] == "ai_not_configured"


@pytest.mark.parametrize(
    "responses,status,code",
    [
        ([(429, '{"type":"error","error":{"type":"rate_limit_error"}}')], 503, "ai_rate_limited"),
        ([(401, '{"type":"error","error":{"type":"authentication_error"}}')], 502, "ai_provider_error"),
        ([(400, '{"type":"error","error":{"type":"invalid_request_error"}}')], 502, "ai_provider_error"),
        ([(529, "{}"), (529, "{}")], 502, "ai_provider_error"),
        ([(504, ""), (504, "")], 504, "ai_timeout"),  # retried once, then gives up
        ([(200, "<html>not json</html>")], 502, "ai_invalid_response"),
        ([(200, anthropic_body(content=[{"type": "text", "text": "Here is my diagnosis: it's a clog"}]))], 502, "ai_invalid_response"),
        ([(200, anthropic_body(stop_reason="max_tokens"))], 502, "ai_invalid_response"),
        ([(200, anthropic_body({**GOOD_MODEL_OUTPUT, "summary": ""}))], 502, "ai_invalid_response"),
        ([(200, anthropic_body({**GOOD_MODEL_OUTPUT, "professional_recommended": "maybe"}))], 502, "ai_invalid_response"),
        ([(200, anthropic_body({k: v for k, v in GOOD_MODEL_OUTPUT.items() if k != "urgent_danger"}))], 502, "ai_invalid_response"),
        ([(200, anthropic_body({**GOOD_MODEL_OUTPUT, "possible_causes": [{"title": "x"}]}))], 502, "ai_invalid_response"),
    ],
)
def test_provider_failures_return_errors_not_fake_results(client, fake_ai, owned, responses, status, code):
    token, rid = owned
    for s, b in responses:
        fake_ai.add(s, b)
    r = diagnose(client, token, rid)
    assert r.status_code == status, r.text
    err = r.json()["error"]
    assert err["code"] == code
    assert "No diagnosis was generated" in err["message"]
    # Internal details (API key, provider error body) are not leaked to the client
    assert "test-key" not in r.text and "authentication_error" not in r.text
    _assert_no_diagnosis_saved(client, token, rid, code)


def test_retry_once_on_temporary_error_then_success(client, fake_ai, owned):
    token, rid = owned
    fake_ai.add(529, '{"type":"error","error":{"type":"overloaded_error"}}').add(200, anthropic_body())
    assert diagnose(client, token, rid).status_code == 200
    assert len(fake_ai.calls) == 2


def test_network_timeout(client, fake_ai, owned):
    token, rid = owned
    fake_ai.add_error(AITimeout("simulated timeout"))
    r = diagnose(client, token, rid)
    assert r.status_code == 504 and r.json()["error"]["code"] == "ai_timeout"


def test_failure_keeps_earlier_successful_diagnosis(client, fake_ai, owned):
    token, rid = owned
    fake_ai.add(200, anthropic_body()).add(429, "{}")
    first = diagnose(client, token, rid).json()["diagnosis"]
    assert diagnose(client, token, rid).status_code == 503
    body = client.get(f"/api/repair-requests/{rid}", headers=auth(token)).json()
    assert body["diagnosis"] == first and body["diagnosis_status"] == "completed"
    assert body["last_diagnosis_error"] == "ai_rate_limited"


# ---------- Access rules ----------


def test_diagnosis_requires_sign_in(client, owned):
    _, rid = owned
    assert client.post(f"/api/repair-requests/{rid}/diagnosis").status_code == 401


def test_anonymous_request_cannot_be_diagnosed(client, fake_ai):
    rid = create_request(client).json()["request_id"]
    token = register(client)
    r = diagnose(client, token, rid)
    assert r.status_code == 403 and r.json()["error"]["code"] == "sign_in_required"
    assert fake_ai.calls == []


def test_unknown_request(client):
    token = register(client)
    assert diagnose(client, token, "00000000-0000-0000-0000-000000000000").status_code == 404


def test_admin_can_diagnose_any_request(client, fake_ai, owned, make_staff):
    _, rid = owned
    admin = make_staff("admin", "admin@example.com")
    fake_ai.add(200, anthropic_body())
    assert diagnose(client, admin, rid).status_code == 200


def test_per_user_diagnosis_rate_limit(tmp_path, fake_ai):
    with TestClient(create_app(make_settings(tmp_path, diagnoses_per_user_per_hour=2), fake_ai)) as c:
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        fake_ai.add(200, anthropic_body()).add(200, anthropic_body())
        assert diagnose(c, token, rid).status_code == 200
        assert diagnose(c, token, rid).status_code == 200
        r = diagnose(c, token, rid)
        assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_requests"
        assert len(fake_ai.calls) == 2


# ---------- OpenAI-compatible provider ----------


def _openai_body(content: dict | str, finish_reason: str = "stop", refusal: str | None = None) -> str:
    message = {"role": "assistant", "content": content if isinstance(content, str) else json.dumps(content), "refusal": refusal}
    return json.dumps({"id": "chatcmpl-test", "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}]})


@pytest.fixture
def openai_client(tmp_path, fake_ai):
    settings = make_settings(tmp_path, ai_provider="openai", openai_api_key="sk-test-not-real", ai_model="test-model", anthropic_api_key=None)
    with TestClient(create_app(settings, fake_ai)) as c:
        yield c


def test_openai_success(openai_client, fake_ai):
    token = register(openai_client)
    rid = create_request(openai_client, auth(token)).json()["request_id"]
    fake_ai.add(200, _openai_body(GOOD_MODEL_OUTPUT))
    d = diagnose(openai_client, token, rid).json()["diagnosis"]
    assert d["provider"] == "openai" and d["model"] == "test-model" and d["source"] == "ai"
    call = fake_ai.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-test-not-real"
    assert call["payload"]["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize(
    "body",
    [_openai_body("not json"), _openai_body(GOOD_MODEL_OUTPUT, refusal="I can't help"), _openai_body(GOOD_MODEL_OUTPUT, finish_reason="length"), json.dumps({"choices": []})],
)
def test_openai_bad_responses(openai_client, fake_ai, body):
    token = register(openai_client)
    rid = create_request(openai_client, auth(token)).json()["request_id"]
    fake_ai.add(200, body)
    assert diagnose(openai_client, token, rid).json()["error"]["code"] == "ai_invalid_response"


# ---------- Privacy helper ----------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("mail me at asha.k+home@gmail.com", "mail me at [email removed]"),
        ("call +91 98765 43210 now", "call [phone removed] now"),
        ("call (044) 2345-6789", "call [phone removed]"),
        ("the 2 taps and 15 mm pipe from 2019", "the 2 taps and 15 mm pipe from 2019"),
    ],
)
def test_redaction(text, expected):
    assert redact(text) == expected
