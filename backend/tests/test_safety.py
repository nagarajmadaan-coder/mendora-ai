"""
Step 6 — safety assessment engine tests.

The ten required scenarios are marked REQUIRED 1–10. No real AI is called anywhere:
the AI provider is the FakeTransport from conftest (it records every call, so we can prove
the AI was NOT called for high-risk cases).
"""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.ai.errors import AITimeout
from app.ai.service import diagnose as ai_diagnose
from app.main import create_app
from app.safety.engine import SafetyBlockedError, SafetyInput, assess, find_unsafe_instruction
from app.safety.rules import GUIDANCE, QUESTIONS, RULES
from conftest import GOOD_MODEL_OUTPUT, anthropic_body, auth, create_request, make_settings, register

LOW_TEXT = "The kitchen sink drains very slowly and gurgles. It started two days ago."
SPARK_TEXT = "Sparks come out of the kitchen socket when I plug in the kettle."
SMOKE_TEXT = "There is smoke and a burning smell coming from the switch board in the hall."
GAS_TEXT = "I can smell gas near the cooker in the kitchen since this morning."
STRUCT_TEXT = "The ceiling is sagging badly above the living room sofa and plaster is falling."
FLOOD_TEXT = "The basement is flooded and the water is up to the sockets on the wall."
AMBIGUOUS_TEXT = "I'm not sure if it's safe, there is a strange noise coming from inside the wall."


def check(trade: str, text: str, **kw):
    return assess(SafetyInput(trade, text, **kw))


def post_assess(client, trade, text, **extra):
    return client.post("/api/safety/assess", json={"trade_id": trade, "description": text, **extra})


# =====================================================================
# REQUIRED 1–7: classification through the public API
# =====================================================================


def test_required_1_clearly_low_risk(client):
    r = post_assess(client, "plumbing", LOW_TEXT)
    assert r.status_code == 200
    s = r.json()
    assert s["risk_level"] == "low"
    assert s["allow_diy"] is True and s["requires_professional"] is False
    assert s["ai_diagnosis"] == "full"
    assert s["matched_hazards"] == [] and s["clarifying_questions"] == []
    assert "didn't find signs of immediate danger" in s["safety_message"]
    assert "rule-based" in s["disclaimer"]


def _assert_high(s: dict, hazard_id: str, category: str):
    assert s["risk_level"] == "high"
    assert s["allow_diy"] is False and s["requires_professional"] is True
    assert s["ai_diagnosis"] == "blocked"
    assert hazard_id in [h["id"] for h in s["matched_hazards"]]
    assert category in [h["category"] for h in s["matched_hazards"]]
    assert s["emergency_steps"], "high risk must include clear safety steps"
    assert "won't give do-it-yourself repair steps" in s["safety_message"]


def test_required_2_electrical_sparking(client):
    s = post_assess(client, "electrical", SPARK_TEXT).json()
    _assert_high(s, "electrical_sparking", "electrical")
    assert [h["matched_text"] for h in s["matched_hazards"] if h["id"] == "electrical_sparking"] == ["Sparks"]
    assert "Never use water on an electrical fire." in s["emergency_steps"]


def test_required_3_smoke_or_burning_near_electrics(client):
    s = post_assess(client, "electrical", SMOKE_TEXT).json()
    _assert_high(s, "electrical_smoke_burning", "electrical")
    assert s["emergency"] is True


def test_required_4_suspected_gas_leak(client):
    s = post_assess(client, "plumbing", GAS_TEXT).json()
    _assert_high(s, "gas_leak", "gas")
    assert s["emergency"] is True
    steps = " ".join(s["emergency_steps"]).lower()
    # leave the area, avoid flames and switches, call from a safe place
    assert "get everyone" in steps and "out of the area" in steps
    assert "don't use flames" in steps and "don't switch lights" in steps
    assert "once you are outside" in steps
    # never leak-finding or repair instructions
    assert "don't try to find the leak or repair anything" in steps
    assert find_unsafe_instruction(" ".join(s["emergency_steps"]).replace("Don't try to find the leak", "")) is None


def test_required_5_major_structural_instability(client):
    s = post_assess(client, "carpentry", STRUCT_TEXT).json()
    _assert_high(s, "structural_instability", "structural")
    assert "Move everyone" in s["emergency_steps"][0]
    assert "structural engineer" in s["recommended_action"]


def test_required_6_flooding_near_electrics(client):
    s = post_assess(client, "plumbing", FLOOD_TEXT).json()
    _assert_high(s, "water_near_electrics", "electrical")
    # The electrical-water danger is the main advice (it outranks the leak itself)
    assert "Don't walk through the water" in s["emergency_steps"][0]


def test_required_7_ambiguous_possibly_dangerous(client):
    s = post_assess(client, "plumbing", AMBIGUOUS_TEXT).json()
    assert s["risk_level"] == "medium"
    assert s["allow_diy"] is False and s["requires_professional"] is True
    assert s["ai_diagnosis"] == "professional_only"
    assert [q["id"] for q in s["clarifying_questions"]] == ["general_danger"]
    assert s["clarifying_questions"][0]["options"] == ["yes", "no", "not_sure"]


# =====================================================================
# REQUIRED 8: missing or invalid input
# =====================================================================


@pytest.mark.parametrize(
    "body,field",
    [
        ({}, "trade_id"),
        ({"trade_id": "plumbing"}, "description"),
        ({"trade_id": "roofing", "description": LOW_TEXT}, "trade_id"),
        ({"trade_id": "plumbing", "description": ""}, "description"),
        ({"trade_id": "plumbing", "description": "    "}, "description"),
        ({"trade_id": "plumbing", "description": "leak"}, "description"),
        ({"trade_id": "plumbing", "description": "x" * 1001}, "description"),
        ({"trade_id": 5, "description": LOW_TEXT}, "trade_id"),
        ({"trade_id": "plumbing", "description": LOW_TEXT, "clarifying_answers": [{"question_id": "made_up", "answer": "no"}]}, "clarifying_answers.0.question_id"),
        ({"trade_id": "plumbing", "description": LOW_TEXT, "clarifying_answers": [{"question_id": "crack_signs", "answer": "perhaps"}]}, "clarifying_answers.0.answer"),
        ({"trade_id": "plumbing", "description": LOW_TEXT, "follow_up_answers": [{"question": "q", "answer": ""}]}, "follow_up_answers.0.answer"),
        ({"trade_id": "plumbing", "description": LOW_TEXT, "risk_level": "low"}, "risk_level"),
    ],
)
def test_required_8_missing_or_invalid_input(client, body, field):
    r = client.post("/api/safety/assess", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert field in [d["field"] for d in r.json()["error"]["details"]]


def test_required_8_invalid_json(client):
    r = client.post("/api/safety/assess", content="{nope", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_required_8_invalid_safety_answers_on_request(client):
    token = register(client)
    rid = create_request(client, auth(token), trade_id="carpentry", description="There is a crack in the bedroom wall above the door frame.").json()["request_id"]
    assert client.post(f"/api/repair-requests/{rid}/safety-answers", json={"answers": []}, headers=auth(token)).status_code == 422
    assert client.post(f"/api/repair-requests/{rid}/safety-answers", json={"answers": [{"question_id": "x", "answer": "no"}]}, headers=auth(token)).status_code == 422


# =====================================================================
# REQUIRED 9: high-risk cases can't reach DIY guidance — even directly through the API
# =====================================================================


@pytest.mark.parametrize("trade,text", [("electrical", SPARK_TEXT), ("plumbing", GAS_TEXT), ("carpentry", STRUCT_TEXT), ("plumbing", FLOOD_TEXT)])
def test_required_9_direct_api_diagnosis_blocked_for_high_risk(client, fake_ai, trade, text):
    token = register(client)
    created = create_request(client, auth(token), trade_id=trade, description=text).json()
    assert created["safety"]["risk_level"] == "high"
    assert created["diagnosis_status"] == "blocked_by_safety"
    fake_ai.add(200, anthropic_body())  # even if the AI were available...
    r = client.post(f"/api/repair-requests/{created['request_id']}/diagnosis", headers=auth(token))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "blocked_by_safety"
    assert fake_ai.calls == []  # ...it is never called
    stored = client.get(f"/api/repair-requests/{created['request_id']}", headers=auth(token)).json()
    assert stored["diagnosis"] is None and stored["safety"]["risk_level"] == "high"


def test_required_9_client_cannot_send_its_own_risk_level(client, fake_ai):
    """The server ignores any risk the client claims; it decides from the description."""
    token = register(client)
    r = client.post("/api/repair-requests", json={"trade_id": "electrical", "description": SPARK_TEXT, "risk_level": "low"}, headers=auth(token))
    assert r.status_code == 422  # unknown fields are rejected outright
    r = client.post(
        "/api/repair-requests",
        json={"trade_id": "electrical", "description": SPARK_TEXT, "clarifying_answers": [{"question_id": "electrical_danger_signs", "answer": "no"}]},
        headers=auth(token),
    )
    assert r.json()["safety"]["risk_level"] == "high"  # answers can't clear a high hazard


def test_required_9_answers_cannot_lower_high_risk(client, fake_ai):
    token = register(client)
    rid = create_request(client, auth(token), trade_id="electrical", description=SPARK_TEXT).json()["request_id"]
    all_no = [{"question_id": q, "answer": "no"} for q in QUESTIONS]
    r = client.post(f"/api/repair-requests/{rid}/safety-answers", json={"answers": all_no}, headers=auth(token))
    assert r.json()["safety"]["risk_level"] == "high"
    assert client.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(token)).status_code == 409
    assert fake_ai.calls == []


def test_required_9_dangerous_follow_up_answer_blocks_and_sticks(client, fake_ai):
    token = register(client)
    rid = create_request(client, auth(token), description=LOW_TEXT).json()["request_id"]
    answers = [{"question": "Anything else?", "answer": "Yes, I also smell gas near the boiler."}]
    r = client.post(f"/api/repair-requests/{rid}/diagnosis", json={"follow_up_answers": answers}, headers=auth(token))
    assert r.status_code == 409 and fake_ai.calls == []
    # Retrying WITHOUT the dangerous answer doesn't help: it was stored and the hazard is sticky.
    fake_ai.add(200, anthropic_body())
    assert client.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(token)).status_code == 409
    assert fake_ai.calls == []


def test_required_9_yes_to_dangerous_ai_question_blocks(client, fake_ai):
    token = register(client)
    rid = create_request(client, auth(token), description=LOW_TEXT).json()["request_id"]
    answers = [{"question": "Do you notice a burning smell near the sink?", "answer": "Yes"}]
    r = client.post(f"/api/repair-requests/{rid}/diagnosis", json={"follow_up_answers": answers}, headers=auth(token))
    assert r.status_code == 409 and fake_ai.calls == []


def test_required_9_high_risk_hides_old_diagnosis(client, fake_ai):
    """A request diagnosed while low risk, then found to be high risk, no longer shows the diagnosis."""
    token = register(client)
    rid = create_request(client, auth(token), trade_id="carpentry", description="There is a crack in the bedroom wall above the door frame.").json()["request_id"]
    client.post(f"/api/repair-requests/{rid}/safety-answers", json={"answers": [{"question_id": "crack_signs", "answer": "no"}]}, headers=auth(token))
    fake_ai.add(200, anthropic_body())
    assert client.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(token)).json()["diagnosis"] is not None
    r = client.post(f"/api/repair-requests/{rid}/safety-answers", json={"answers": [{"question_id": "crack_signs", "answer": "yes"}]}, headers=auth(token))
    body = r.json()
    assert body["safety"]["risk_level"] == "high"
    assert body["diagnosis"] is None and body["diagnosis_status"] == "blocked_by_safety"
    assert client.get("/api/repair-requests", headers=auth(token)).json()["items"][0]["diagnosis"] is None


def test_required_9_ai_service_refuses_high_risk_even_if_called_directly(settings, fake_ai):
    """Defence in depth: the AI service itself refuses, even if some future route forgot the check."""
    safety = check("electrical", SPARK_TEXT)
    fake_ai.add(200, anthropic_body())
    with pytest.raises(SafetyBlockedError):
        ai_diagnose(trade_id="electrical", trade_name="Electrical", description=SPARK_TEXT, follow_up_answers=[], safety=safety, settings=settings, transport=fake_ai)
    assert fake_ai.calls == []


def test_required_9_no_other_endpoint_returns_diy_for_high_risk(client, fake_ai, make_staff):
    token = register(client)
    rid = create_request(client, auth(token), trade_id="electrical", description=SPARK_TEXT).json()["request_id"]
    admin = make_staff("admin", "admin@example.com")
    admin_list = client.get("/api/admin/repair-requests", headers=auth(admin)).json()["items"]
    assert admin_list[0]["diagnosis"] is None and admin_list[0]["safety"]["risk_level"] == "high"
    assert client.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(admin)).status_code == 409
    assert fake_ai.calls == []


# =====================================================================
# REQUIRED 10: AI or downstream failure must not bypass the safety decision
# =====================================================================


MEDIUM_TEXT = "The breaker keeps tripping when I use the microwave in the kitchen."


@pytest.mark.parametrize(
    "fail",
    [
        lambda f: f.add(429, "{}"),
        lambda f: f.add(500, "{}").add(500, "{}"),
        lambda f: f.add(200, "not json"),
        lambda f: f.add(200, anthropic_body({**GOOD_MODEL_OUTPUT, "summary": ""})),
        lambda f: f.add_error(AITimeout("simulated")),
    ],
)
def test_required_10_ai_failure_keeps_safety_decision(client, fake_ai, fail):
    token = register(client)
    created = create_request(client, auth(token), trade_id="electrical", description=MEDIUM_TEXT).json()
    assert created["safety"]["risk_level"] == "medium"
    fail(fake_ai)
    r = client.post(f"/api/repair-requests/{created['request_id']}/diagnosis", headers=auth(token))
    assert r.status_code in (502, 503, 504)
    assert "No diagnosis was generated" in r.json()["error"]["message"]
    after = client.get(f"/api/repair-requests/{created['request_id']}", headers=auth(token)).json()
    assert after["diagnosis"] is None
    assert after["safety"]["risk_level"] == "medium" and after["safety"]["allow_diy"] is False


def test_required_10_ai_not_configured_still_returns_safety(tmp_path, fake_ai):
    with TestClient(create_app(make_settings(tmp_path, anthropic_api_key=None), fake_ai)) as c:
        token = register(c)
        created = create_request(c, auth(token), trade_id="electrical", description=SPARK_TEXT).json()
        # Safety works with no AI key at all
        assert created["safety"]["risk_level"] == "high"
        assert c.post(f"/api/repair-requests/{created['request_id']}/diagnosis", headers=auth(token)).json()["error"]["code"] == "blocked_by_safety"
        assert post_assess(c, "plumbing", GAS_TEXT).json()["risk_level"] == "high"


def test_required_10_unsafe_ai_suggestion_is_removed_low_risk(client, fake_ai):
    token = register(client)
    rid = create_request(client, auth(token), description=LOW_TEXT).json()["request_id"]
    unsafe = {
        **GOOD_MODEL_OUTPUT,
        "possible_causes": [
            {"title": "Clog in the trap", "explanation": "Food can build up in the U-bend."},
            {"title": "Faulty disposal wiring", "explanation": "Open the panel and reconnect the loose wire to the disposal."},
        ],
        "follow_up_questions": ["Can you remove the socket cover and look inside?", "Are other drains slow?"],
        "recommended_next_step": "Switch off the breaker, unscrew the socket faceplate and tighten the wires.",
    }
    fake_ai.add(200, anthropic_body(unsafe))
    d = client.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(token)).json()["diagnosis"]
    text = json.dumps(d).lower()
    assert "faceplate" not in text and "reconnect the loose wire" not in text and "socket cover" not in text
    assert [c["title"] for c in d["possible_causes"]] == ["Clog in the trap"]
    assert d["follow_up_questions"] == ["Are other drains slow?"]
    assert d["safety_filter_applied"] is True and d["professional_recommended"] is True


def test_required_10_medium_risk_gets_professional_only_assessment(client, fake_ai):
    token = register(client)
    rid = create_request(client, auth(token), trade_id="electrical", description=MEDIUM_TEXT).json()["request_id"]
    diy = {**GOOD_MODEL_OUTPUT, "recommended_next_step": "Try a different microwave plug.", "professional_recommended": False}
    fake_ai.add(200, anthropic_body(diy))
    body = client.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(token)).json()
    d = body["diagnosis"]
    assert d["safety_mode"] == "professional_only"
    assert d["recommended_next_step"] == "Don't try to repair this yourself. Have a qualified electrician check it."
    assert d["professional_recommended"] is True
    # The AI was told DIY isn't allowed
    sent = json.dumps(fake_ai.calls[0]["payload"])
    assert "DIY is NOT allowed" in sent and "Breaker or fuse keeps tripping" in sent


# =====================================================================
# Clarifying questions (medium → low / high)
# =====================================================================


def test_clarifying_answers_can_clear_or_escalate(client):
    crack = "There is a crack in the bedroom wall above the door frame."
    assert post_assess(client, "carpentry", crack).json()["risk_level"] == "medium"
    no = post_assess(client, "carpentry", crack, clarifying_answers=[{"question_id": "crack_signs", "answer": "no"}]).json()
    assert no["risk_level"] == "low" and no["resolved_hazards"] == ["Crack in a wall, ceiling or floor"]
    yes = post_assess(client, "carpentry", crack, clarifying_answers=[{"question_id": "crack_signs", "answer": "yes"}]).json()
    assert yes["risk_level"] == "high" and yes["matched_hazards"][0]["id"] == "structural_crack_confirmed"
    unsure = post_assess(client, "carpentry", crack, clarifying_answers=[{"question_id": "crack_signs", "answer": "not_sure"}]).json()
    assert unsure["risk_level"] == "medium" and unsure["clarifying_questions"] == []  # stays cautious; no re-asking


def test_saved_request_safety_answers_flow(client, fake_ai):
    token = register(client)
    created = create_request(client, auth(token), trade_id="electrical", description="The light switch in the hall stopped working last week.").json()
    assert created["safety"]["risk_level"] == "medium"
    assert [q["id"] for q in created["safety"]["clarifying_questions"]] == ["electrical_danger_signs", "electrical_opening"]
    r = client.post(
        f"/api/repair-requests/{created['request_id']}/safety-answers",
        json={"answers": [{"question_id": "electrical_danger_signs", "answer": "no"}, {"question_id": "electrical_opening", "answer": "yes"}]},
        headers=auth(token),
    )
    s = r.json()["safety"]
    assert s["risk_level"] == "medium" and s["clarifying_questions"] == []  # opening a switch = electrician
    assert {a["id"]: a["answer"] for a in s["answered_questions"]} == {"electrical_danger_signs": "no", "electrical_opening": "yes"}


def test_safety_answers_privacy(client):
    asha = register(client, "asha@example.com")
    ravi = register(client, "ravi@example.com", "Ravi")
    rid = create_request(client, auth(asha), trade_id="carpentry", description="There is a crack in the bedroom wall above the door frame.").json()["request_id"]
    body = {"answers": [{"question_id": "crack_signs", "answer": "no"}]}
    assert client.post(f"/api/repair-requests/{rid}/safety-answers", json=body, headers=auth(ravi)).status_code == 404
    assert client.post(f"/api/repair-requests/{rid}/safety-answers", json=body).status_code == 404


# =====================================================================
# Rule coverage — every category, minor vs. serious, false-alarm checks
# =====================================================================


@pytest.mark.parametrize(
    "trade,text,expected,hazard",
    [
        # electrical
        ("electrical", "Some wires are exposed behind the TV unit where the cover broke.", "high", "electrical_exposed_wires"),
        ("plumbing", "I got a shock when I touched the metal tap in the bathroom.", "high", "electrical_shock"),
        ("electrical", "The plug on the heater is very hot and has brown marks.", "high", "electrical_overheating"),
        ("electrical", "There is a fishy smell coming from the socket behind the bed.", "high", "electrical_smoke_burning"),
        ("electrical", "The switch makes a crackling sound when I turn it on.", "medium", "electrical_buzzing"),
        ("electrical", "The light switch in the hall stopped working last week.", "medium", "electrical_work"),
        ("electrical", "The bulb in my bedroom lamp stopped working and needs replacing.", "low", None),
        # gas
        ("plumbing", "The carbon monoxide alarm keeps going off near the boiler.", "high", "carbon_monoxide"),
        ("plumbing", "There is a hissing sound near the gas cylinder regulator.", "high", "gas_leak"),
        ("plumbing", "It smells like rotten eggs in the kitchen near the stove.", "high", "gas_leak"),
        ("plumbing", "The gas geyser takes a long time to heat the water now.", "medium", "gas_appliance"),
        # structural
        ("carpentry", "The crack in the bedroom wall is getting wider every week.", "high", "structural_instability"),
        ("carpentry", "There is a crack in the bedroom wall above the door frame.", "medium", "structural_crack"),
        # plumbing
        ("plumbing", "A pipe burst under the sink and water is pouring everywhere.", "high", "plumbing_major_leak"),
        ("plumbing", "Sewage is backing up into the shower and onto the bathroom floor.", "high", "plumbing_sewage"),
        ("plumbing", "The tap water looks brown and smells strange this week.", "medium", "plumbing_water_quality"),
        ("plumbing", "There is a water stain on the ceiling below the bathroom.", "medium", "plumbing_ceiling_leak"),
        ("plumbing", "The geyser makes loud banging noises when it heats up.", "medium", "plumbing_water_heater"),
        ("plumbing", "The bathroom tap drips constantly even when it is closed tightly.", "low", None),
        # carpentry
        ("carpentry", "The tall bookshelf is leaning forward and about to fall.", "high", "carpentry_tipping"),
        ("carpentry", "The ceiling fan is hanging down and swinging when it runs.", "high", "carpentry_overhead"),
        ("carpentry", "The kitchen cabinet is coming away from the wall above the stove.", "high", "carpentry_overhead"),
        ("carpentry", "The staircase railing is loose and wobbly when you hold it.", "high", "carpentry_fall_hazard"),
        ("carpentry", "The wardrobe is wobbly and not fixed to the wall at all.", "medium", "carpentry_unstable_furniture"),
        ("carpentry", "The glass panel in the cabinet door is broken.", "medium", "carpentry_broken_glass"),
        ("carpentry", "The wardrobe door hinge is loose and the door sags a little.", "low", None),
        ("carpentry", "My dining chair wobbles because one leg is shorter.", "low", None),
    ],
)
def test_rule_coverage(trade, text, expected, hazard):
    result = check(trade, text)
    assert result.risk_level == expected, [h.id for h in result.matched_hazards]
    if hazard:
        assert hazard in [h.id for h in result.matched_hazards]


@pytest.mark.parametrize(
    "trade,text",
    [
        ("plumbing", "Water heater switch is on but no hot water comes out of the tap."),
        ("plumbing", "Water won't drain past the sink plug in the bathroom."),
        ("plumbing", "I switch on the water pump but the tank fills very slowly."),
        ("carpentry", "The smoke detector keeps chirping every minute near the door."),
        ("electrical", "The smoke detector keeps chirping, I think it needs a new battery."),
        ("carpentry", "The kitchen drawer sticks and is hard to open and close."),
        ("plumbing", "The toilet keeps running after flushing for a long time."),
    ],
)
def test_common_minor_reports_are_not_over_flagged(trade, text):
    assert check(trade, text).risk_level == "low"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("There is no smoke and no sparks, the pipe just drips slowly.", "low"),  # clearly negated
        ("I'm not sure if it's sparking but there is a clicking noise in the socket.", "high"),  # uncertain = counts
        ("It sparked once yesterday but there are no sparks now.", "high"),  # past sparking still counts
        ("There isn't any gas smell but the drain gurgles loudly.", "low"),
    ],
)
def test_negation_and_uncertainty(text, expected):
    assert check("plumbing", text).risk_level == expected


def test_no_keyword_is_not_automatically_safe_for_electrical_work():
    result = check("electrical", "My kitchen extractor fan stopped working this morning.")
    assert result.risk_level == "medium" and result.matched_hazards[0].id == "electrical_work"


def test_priority_gas_advice_first_when_several_dangers():
    s = check("plumbing", "I smell gas and there are sparks from the socket near the cooker.")
    assert s.risk_level == "high"
    assert {h.id for h in s.matched_hazards} >= {"gas_leak", "electrical_sparking"}
    assert s.recommended_action.startswith("Leave the area now")
    assert "We also noticed: Sparking or arcing" in s.safety_message


def test_rules_are_well_formed():
    for rule in RULES:
        assert rule.guidance in GUIDANCE, rule.id
        assert rule.patterns, rule.id
        if rule.risk == "medium":
            assert rule.questions and rule.explanation, rule.id
        for qid in rule.questions:
            assert qid in QUESTIONS, (rule.id, qid)
    for g in GUIDANCE.values():
        for step in g.steps:
            assert find_unsafe_instruction(step.replace("Don't try to find the leak", "")) is None, step


@pytest.mark.parametrize(
    "text",
    [
        "Remove the faceplate of the socket and check the wires.",
        "Use soapy water to find the gas leak.",
        "Tighten the gas pipe fitting with a spanner.",
        "Relight the pilot light on the boiler.",
        "Tape down the breaker so it stops tripping.",
        "Prop up the sagging beam with a wooden post.",
        "Strip the wire ends and reconnect them.",
    ],
)
def test_unsafe_instructions_detected(text):
    assert find_unsafe_instruction(text)


@pytest.mark.parametrize(
    "text",
    [
        "Use a plunger on the sink.",
        "Check whether other drains are slow too.",
        "Tighten the hinge screws with a screwdriver.",
        "Replace the light bulb with one of the same type.",
    ],
)
def test_safe_suggestions_not_flagged(text):
    assert find_unsafe_instruction(text) is None


@pytest.mark.parametrize("text", ["Don't touch the wires.", "Never open the fuse box yourself.", "Avoid removing the socket cover."])
def test_warnings_are_not_instructions(text):
    assert find_unsafe_instruction(text) is None


def test_engine_is_deterministic():
    a, b = check("plumbing", FLOOD_TEXT), check("plumbing", FLOOD_TEXT)
    assert a.model_dump(exclude={"assessed_at"}) == b.model_dump(exclude={"assessed_at"})


def test_assess_endpoint_saves_nothing(client):
    from app.models import RepairRequest

    post_assess(client, "electrical", SPARK_TEXT)
    with client.app.state.session_factory() as db:
        assert db.query(RepairRequest).count() == 0


def test_health_reports_safety_engine(client):
    s = client.get("/api/health").json()["safety_engine"]
    assert s["enabled"] is True and s["needs_ai_key"] is False


# =====================================================================
# Safety stored with the request; old databases upgraded
# =====================================================================


def test_safety_stored_with_request_and_survives_restart(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as c1:
        token = register(c1)
        rid = create_request(c1, auth(token), trade_id="plumbing", description=GAS_TEXT).json()["request_id"]
    with TestClient(create_app(settings)) as c2:
        with c2.app.state.session_factory() as db:
            from app.models import RepairRequest

            row = db.get(RepairRequest, rid)
            assert row.risk_level == "high" and row.safety_assessment["risk_level"] == "high"
            assert [h["id"] for h in row.safety_escalations] == ["gas_leak"]


def test_old_database_is_upgraded_and_old_rows_get_assessed(tmp_path):
    """A Step 4/5 database (no safety columns, an old 'safety_screen' result) keeps working."""
    db_file = tmp_path / "test.db"
    con = sqlite3.connect(db_file)
    con.executescript(
        """
        CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(254) UNIQUE, full_name VARCHAR(100),
            password_hash VARCHAR(255), role VARCHAR(20), is_active BOOLEAN, created_at DATETIME);
        CREATE TABLE repair_requests (id VARCHAR(36) PRIMARY KEY, customer_id VARCHAR(36), trade VARCHAR(20),
            description TEXT, status VARCHAR(20), created_at DATETIME, updated_at DATETIME,
            diagnosis_status VARCHAR(20), diagnosis JSON, diagnosed_at DATETIME, follow_up_answers JSON,
            last_diagnosis_error VARCHAR(50));
        """
    )
    legacy = json.dumps({"source": "safety_screen", "summary": "old warning", "recommended_next_step": "x", "disclaimer": "x",
                         "professional_recommended": True, "generated_at": "2026-10-25T10:00:00Z"})
    con.execute(
        "INSERT INTO repair_requests VALUES ('old-1', NULL, 'electrical', ?, 'diagnosed', '2026-10-25 10:00:00', '2026-10-25 10:00:00', 'completed', ?, '2026-10-25 10:00:00', NULL, NULL)",
        (SPARK_TEXT, legacy),
    )
    con.execute(
        "INSERT INTO repair_requests VALUES ('old-2', NULL, 'plumbing', ?, 'accepted', '2026-10-25 10:00:00', '2026-10-25 10:00:00', 'not_started', NULL, NULL, NULL, NULL)",
        (LOW_TEXT,),
    )
    con.commit()
    con.close()

    with TestClient(create_app(make_settings(tmp_path))) as c:
        old1 = c.get("/api/repair-requests/old-1").json()
        old2 = c.get("/api/repair-requests/old-2").json()
    assert old1["safety"]["risk_level"] == "high" and old1["diagnosis"] is None  # legacy result not shown as a diagnosis
    assert old2["safety"]["risk_level"] == "low"
    columns = {row[1] for row in sqlite3.connect(db_file).execute("PRAGMA table_info(repair_requests)")}
    assert {"risk_level", "safety_assessment", "safety_answers", "safety_escalations"} <= columns
