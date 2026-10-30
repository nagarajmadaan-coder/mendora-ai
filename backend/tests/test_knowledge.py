"""Step 7 — knowledge base, retrieval, case memory, and safety override."""

import json

import pytest

from app.knowledge.retrieval import KeywordRetriever, get_retriever, tokenize
from app.knowledge.store import DATA_FILE, KnowledgeFile, load_knowledge
from app.safety.engine import find_unsafe_instruction
from conftest import auth, create_request, register

LOW_DRAIN = "The kitchen sink drains very slowly and gurgles. It started two days ago."


def search(client, trade, text, **extra):
    return client.post("/api/knowledge/search", json={"trade_id": trade, "description": text, **extra})


# ---------- The knowledge file itself ----------


def test_knowledge_file_loads_and_is_honest():
    kb = load_knowledge()
    assert len(kb.entries) >= 15
    assert {e.trade for e in kb.entries} == {"plumbing", "electrical", "carpentry"}
    for e in kb.entries:
        assert e.source.verification_status == "unverified"  # nothing claims professional review
        assert "Not reviewed" in e.source.note
        for step in e.next_steps + e.safety_restrictions:
            assert find_unsafe_instruction(step) is None, (e.id, step)


def test_loader_rejects_unsafe_entry(tmp_path):
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    data["entries"][0]["next_steps"] = ["Remove the faceplate of the socket and tighten the wires."]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe instruction"):
        load_knowledge(bad)


def test_loader_rejects_fake_professional_review(tmp_path):
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    data["entries"][0]["source"] = {"type": "professional_review", "verification_status": "professionally_reviewed", "note": "Looks great to us."}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="reviewed_by"):
        load_knowledge(bad)


def test_loader_rejects_duplicate_ids():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    data["entries"].append(data["entries"][0])
    with pytest.raises(ValueError, match="duplicate"):
        KnowledgeFile.model_validate(data)


# ---------- Retrieval ----------


@pytest.mark.parametrize(
    "trade,text,expected",
    [
        ("plumbing", LOW_DRAIN, "plb-slow-drain"),
        ("plumbing", "The bathroom tap drips constantly even when it is closed tightly.", "plb-dripping-tap"),
        ("plumbing", "Toilet keeps running after flushing for a long time.", "plb-running-toilet"),
        ("electrical", "The bulb in my bedroom lamp stopped working and needs replacing.", "ele-bulb-not-working"),
        ("carpentry", "The wardrobe door hinge is loose and the door sags a little.", "car-loose-hinge"),
        ("carpentry", "The bedroom door sticks and rubs on the frame when closing.", "car-sticking-door"),
        ("carpentry", "My dining chair wobbles because one leg is shorter.", "car-wobbly-chair-table"),
    ],
)
def test_matching_search(trade, text, expected):
    hits = get_retriever(load_knowledge().entries).search(text, trade=trade)
    assert hits and hits[0].id == expected
    assert 0 < hits[0].score <= 1 and len(hits[0].matched_terms) >= 2


@pytest.mark.parametrize(
    "text",
    ["My garden hose reel is cracked and the paint is peeling off.", "I want to build a new treehouse this summer.", "It stopped working suddenly."],
)
def test_no_match(text):
    assert get_retriever(load_knowledge().entries).search(text, trade=None) == []


def test_trade_filter():
    r = get_retriever(load_knowledge().entries)
    assert r.search("sink drains slowly", trade="carpentry") == []
    assert all(h.id.startswith("plb-") for h in r.search("sink drains slowly", trade="plumbing"))
    assert r.search("door sticks and rubs on the frame", trade="plumbing") == []


def test_tokenizer_handles_synonyms_and_endings():
    assert tokenize("faucet") == tokenize("tap") == ["tap"]
    assert tokenize("geyser") == tokenize("heater")
    assert tokenize("replace") == tokenize("replacing")
    assert tokenize("the and of it") == []


def test_retriever_interface_is_pluggable():
    with pytest.raises(ValueError, match="embedding retriever can be added later"):
        get_retriever([], kind="embedding")
    assert KeywordRetriever([]).search("anything") == []


# ---------- Safety gating (safety overrides retrieved content) ----------


def test_low_risk_returns_entry_with_steps(client):
    g = search(client, "plumbing", LOW_DRAIN).json()
    assert g["status"] == "matched" and g["mode"] == "full" and g["safety"]["risk_level"] == "low"
    top = g["matches"][0]
    assert top["entry"]["id"] == "plb-slow-drain" and top["entry"]["steps_shown"] is True
    assert top["entry"]["next_steps"] and top["relevance"] > 0.5 and "sink" in top["matched_terms"]
    assert all(c["is_possibility"] for c in top["entry"]["possible_causes"])
    assert top["entry"]["source"]["verification_status"] == "unverified"
    assert "NOT been reviewed by a licensed professional" in g["disclaimer"]


def test_high_risk_blocks_knowledge_even_when_an_entry_matches(client):
    # Same slow-drain words that match an entry — plus a gas smell.
    g = search(client, "plumbing", LOW_DRAIN + " I can also smell gas near the sink.").json()
    assert g["status"] == "blocked_by_safety" and g["mode"] == "blocked"
    assert g["matches"] == [] and g["similar_verified_cases"] == []
    assert g["safety"]["risk_level"] == "high"
    assert "repair guidance isn't shown" in g["message"]


def test_medium_risk_hides_steps(client):
    g = search(client, "electrical", "The breaker keeps tripping when I use the microwave in the kitchen.").json()
    assert g["safety"]["risk_level"] == "medium" and g["mode"] == "professional_only"
    entry = g["matches"][0]["entry"]
    assert entry["id"] == "ele-tripped-breaker"
    assert entry["next_steps"] == [] and entry["steps_shown"] is False and entry["professional_recommended"] is True
    assert "hidden because the safety check found a possible risk" in entry["steps_note"]


def test_medium_becomes_low_after_safe_answers_then_steps_show(client):
    text = "The breaker keeps tripping when I use the microwave in the kitchen."
    answers = [{"question_id": "electrical_danger_signs", "answer": "no"}, {"question_id": "breaker_repeats", "answer": "no"}]
    g = search(client, "electrical", text, clarifying_answers=answers).json()
    assert g["safety"]["risk_level"] == "low" and g["matches"][0]["entry"]["steps_shown"] is True


def test_professional_only_entry_marks_steps_as_safe_checks(client):
    g = search(client, "plumbing", "Water heater switch is on but no hot water comes out of the tap.").json()
    entry = next(m["entry"] for m in g["matches"] if m["entry"]["id"] == "plb-no-hot-water")
    assert entry["professional_recommended"] is True
    assert "safe checks only" in entry["steps_note"]


def test_no_match_result_is_honest(client):
    g = search(client, "plumbing", "My garden hose reel is cracked and the paint is peeling off.").json()
    assert g["status"] == "no_match" and g["matches"] == []
    assert "don't have a knowledge-base entry" in g["message"]


def test_browsing_never_returns_steps(client):
    listing = client.get("/api/knowledge/entries?trade=plumbing").json()
    assert listing["total"] >= 5 and all(e["trade"] == "plumbing" for e in listing["entries"])
    assert "next_steps" not in json.dumps(listing)
    detail = client.get("/api/knowledge/entries/plb-slow-drain").json()
    assert "next_steps" not in detail and detail["possible_causes"]
    assert client.get("/api/knowledge/entries/nope").status_code == 404
    assert client.get("/api/knowledge/entries?trade=roofing").status_code == 422


def test_search_validation(client):
    assert search(client, "roofing", LOW_DRAIN).status_code == 422
    assert search(client, "plumbing", "").status_code == 422


def test_saved_request_guidance_uses_server_safety(client):
    token = register(client)
    low = create_request(client, auth(token), description=LOW_DRAIN).json()["request_id"]
    g = client.get(f"/api/repair-requests/{low}/guidance", headers=auth(token)).json()
    assert g["status"] == "matched" and g["matches"][0]["entry"]["steps_shown"]
    high = create_request(client, auth(token), trade_id="electrical", description="Sparks come out of the kitchen socket when I plug in the kettle.").json()["request_id"]
    g = client.get(f"/api/repair-requests/{high}/guidance", headers=auth(token)).json()
    assert g["status"] == "blocked_by_safety" and g["matches"] == []
    other = register(client, "other@example.com", "Other")
    assert client.get(f"/api/repair-requests/{low}/guidance", headers=auth(other)).status_code == 404


# ---------- Verified-case memory ----------


def _case(**over):
    body = {
        "trade": "plumbing",
        "category": "Drains",
        "symptoms": "Kitchen sink draining slowly with gurgling. Call me on +91 98765 43210.",
        "confirmed_cause": "Grease build-up in the trap",
        "cause_source": "technician_confirmed",
        "parts_used": ["none"],
        "completion_minutes": 30,
        "cost_amount": 400,
    }
    body.update(over)
    return body


def test_case_lifecycle_and_privacy(client, make_staff):
    admin = make_staff("admin", "admin@example.com")
    r = client.post("/api/admin/cases", json=_case(), headers=auth(admin))
    assert r.status_code == 201
    case = r.json()
    assert case["verification_status"] == "unverified"
    assert "98765" not in case["symptoms"] and "[phone removed]" in case["symptoms"]

    # Unverified cases are not used in retrieval
    assert search(client, "plumbing", LOW_DRAIN).json()["similar_verified_cases"] == []

    assert client.post(f"/api/admin/cases/{case['id']}/verify", json={"basis": "short"}, headers=auth(admin)).status_code == 422
    v = client.post(f"/api/admin/cases/{case['id']}/verify", json={"basis": "Technician completion report with photo of cleared trap."}, headers=auth(admin))
    assert v.status_code == 200 and v.json()["verification_status"] == "verified"

    similar = search(client, "plumbing", LOW_DRAIN).json()["similar_verified_cases"]
    assert len(similar) == 1 and similar[0]["confirmed_cause"] == "Grease build-up in the trap"
    assert set(similar[0]) == {"case_id", "trade", "category", "symptoms_summary", "confirmed_cause", "parts_used", "completion_minutes", "cost_amount", "currency", "relevance"}

    # Verified cases are still never shown for high-risk reports
    g = search(client, "plumbing", LOW_DRAIN + " There is also smoke coming from the socket.").json()
    assert g["similar_verified_cases"] == [] and g["status"] == "blocked_by_safety"

    assert client.post(f"/api/admin/cases/{case['id']}/verify", json={"basis": "Again, but it is already verified."}, headers=auth(admin)).status_code == 409


@pytest.mark.parametrize(
    "over,message",
    [({"cause_source": "ai_suggestion"}, "AI suggestion"), ({"cause_source": "customer_reported"}, "customer"), ({"confirmed_cause": None}, "confirmed cause")],
)
def test_ai_guess_or_unconfirmed_cause_cannot_be_verified(client, make_staff, over, message):
    admin = make_staff("admin", "admin@example.com")
    case = client.post("/api/admin/cases", json=_case(**over), headers=auth(admin)).json()
    r = client.post(f"/api/admin/cases/{case['id']}/verify", json={"basis": "We think this is probably correct."}, headers=auth(admin))
    assert r.status_code == 422 and message in r.json()["error"]["message"]


def test_rejected_case_not_used(client, make_staff):
    admin = make_staff("admin", "admin@example.com")
    case = client.post("/api/admin/cases", json=_case(), headers=auth(admin)).json()
    assert client.post(f"/api/admin/cases/{case['id']}/reject", json={"reason": "No evidence"}, headers=auth(admin)).json()["verification_status"] == "rejected"
    assert client.post(f"/api/admin/cases/{case['id']}/verify", json={"basis": "Trying to verify a rejected case."}, headers=auth(admin)).status_code == 409
    assert search(client, "plumbing", LOW_DRAIN).json()["similar_verified_cases"] == []


def test_case_endpoints_admin_only(client, make_staff):
    customer = register(client)
    tech = make_staff("technician", "tech@example.com")
    for headers in ({}, auth(customer), auth(tech)):
        assert client.get("/api/admin/cases", headers=headers).status_code in (401, 403)
        assert client.post("/api/admin/cases", json=_case(), headers=headers).status_code in (401, 403)


def test_case_validation(client, make_staff):
    admin = make_staff("admin", "admin@example.com")
    assert client.post("/api/admin/cases", json=_case(cause_source="guess"), headers=auth(admin)).status_code == 422
    assert client.post("/api/admin/cases", json=_case(symptoms="short"), headers=auth(admin)).status_code == 422
    assert client.post("/api/admin/cases", json=_case(cost_amount=-5), headers=auth(admin)).status_code == 422
    assert client.post("/api/admin/cases", json=_case(repair_request_id="missing"), headers=auth(admin)).status_code == 404
