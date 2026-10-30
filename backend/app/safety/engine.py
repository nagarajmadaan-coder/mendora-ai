"""
The safety assessment engine.

    assess(SafetyInput) -> SafetyAssessmentOut

Deterministic: the same input always gives the same result, with no AI and no network.
It runs BEFORE any AI diagnosis, and its decision can't be overridden by the AI.

Steps
  1. Scan the user's own words (description + follow-up answers) with the rules in rules.py.
     - "no sparks", "there isn't any smoke" are ignored (negated)...
     - ...but "not sure if it's sparking" still counts (uncertain = treat as possible).
     - When a follow-up answer is a "yes", the question it answers is scanned too.
  2. Add conservative defaults: electrical jobs are MEDIUM unless clearly simple.
  3. Apply clarifying answers: "yes" can raise a medium hazard to HIGH; "no" to all of a
     hazard's questions clears it; "not sure" keeps it. HIGH hazards are never cleared.
  4. Decide the risk level and write plain-language advice.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..schemas import AnsweredQuestionOut, MatchedHazardOut, SafetyAssessmentOut, SafetyQuestionOut
from .rules import ELECTRICAL_SIMPLE, GUIDANCE, QUESTIONS, RULES, RULES_BY_ID, RULES_VERSION, UNSAFE_INSTRUCTION_PATTERNS, Rule

DISCLAIMER = (
    "This is an automatic, rule-based check of the words you used — not an inspection. It can miss things. "
    "If you are unsure, treat it as dangerous and contact a qualified professional."
)

PROFESSIONAL_BY_TRADE = {
    "plumbing": "a qualified plumber",
    "electrical": "a qualified electrician",
    "carpentry": "a qualified carpenter",
}
PROFESSIONAL_BY_CATEGORY = {
    "electrical": "a qualified electrician",
    "gas": "a registered gas engineer",
    "structural": "a structural engineer or qualified builder",
    "plumbing": "a qualified plumber",
    "carpentry": "a qualified carpenter",
}

ELECTRICAL_GENERAL = Rule(
    "electrical_work", "electrical", "medium", "Electrical work",
    (),
    guidance="electrical_contact",
    explanation="Most repairs involving sockets, switches, light fittings or wiring need a qualified electrician.",
    questions=("electrical_danger_signs", "electrical_opening"),
)

_FLAGS = re.IGNORECASE
_COMPILED = [(rule, [re.compile(p, _FLAGS) for p in rule.patterns]) for rule in RULES]
_SIMPLE_ELECTRICAL = [re.compile(p, _FLAGS) for p in ELECTRICAL_SIMPLE]
_UNSAFE = [re.compile(p, _FLAGS) for p in UNSAFE_INSTRUCTION_PATTERNS]

# A match is ignored when it is clearly negated just before it ("no smoke", "there isn't any sparking")...
_NEGATION = re.compile(
    r"\b(no|not|never|without|nor|isn'?t|aren'?t|wasn'?t|weren'?t|don'?t|doesn'?t|didn'?t|haven'?t|hasn'?t|cannot see|can'?t see)\s+(\w+\s+){0,2}$",
    _FLAGS,
)
# ...unless the person is unsure ("not sure if it's sparking") — then it still counts.
_UNCERTAIN = re.compile(r"\b(not sure|unsure|don'?t know|can'?t tell|no idea|not certain|might|maybe|possibly|i think|could be)\b", _FLAGS)
_AFFIRMATIVE = re.compile(
    r"^\W*(yes|yeah|yep|yup|ya|y|sometimes|a (little|bit)|slightly|i think so|probably|maybe|kind of|sort of|it does|it is|there is|there are|correct|true|definitely|often)\b",
    _FLAGS,
)


@dataclass(frozen=True)
class SafetyInput:
    trade_id: str
    description: str
    follow_up_answers: Sequence[tuple[str, str]] = ()
    clarifying_answers: Mapping[str, str] = field(default_factory=dict)  # question id -> yes | no | not_sure
    extra_hazards: Sequence[MatchedHazardOut] = ()  # e.g. a danger flagged later by the AI (always kept)


class SafetyBlockedError(Exception):
    """Raised if anything tries to produce repair guidance for a case the safety check blocked."""


def _is_negated(text: str, start: int) -> bool:
    before = text[max(0, start - 40) : start]
    if not _NEGATION.search(before):
        return False
    return not _UNCERTAIN.search(text[max(0, start - 60) : start])


def _first_match(patterns: list[re.Pattern], text: str) -> str | None:
    for pattern in patterns:
        for match in pattern.finditer(text):
            if not _is_negated(text, match.start()):
                return match.group(0).strip()[:80]
    return None


def _segments(data: SafetyInput) -> list[str]:
    """The texts we scan: the description and the user's answers (plus the question when they said yes)."""
    parts = [data.description]
    for question, answer in data.follow_up_answers:
        parts.append(answer)
        if _AFFIRMATIVE.search(answer):
            parts.append(question)
    return parts


def _scan(data: SafetyInput) -> list[tuple[Rule, str]]:
    segments = _segments(data)
    found: list[tuple[Rule, str]] = []
    for rule, patterns in _COMPILED:
        for segment in segments:
            hit = _first_match(patterns, segment)
            if hit:
                found.append((rule, hit))
                break
    return found


def _hazard(rule: Rule, risk: str, matched_text: str | None, *, id_suffix: str = "", label: str | None = None) -> MatchedHazardOut:
    return MatchedHazardOut(
        id=rule.id + id_suffix,
        category=rule.category,
        label=label or rule.label,
        risk=risk,  # type: ignore[arg-type]
        matched_text=matched_text,
        guidance=rule.guidance,
    )


_WARNING_BEFORE = re.compile(
    r"\b(don'?t|do not|never|avoid|without|no need to|shouldn'?t|should not|must not|mustn'?t|not safe to|unsafe to)\b[^.]{0,20}$",
    _FLAGS,
)


def find_unsafe_instruction(text: str) -> str | None:
    """
    Returns the matching text if `text` contains a dangerous do-it-yourself instruction.
    Warnings such as "don't touch the wires" or "never open the panel" are not instructions, so they pass.
    """
    for pattern in _UNSAFE:
        for match in pattern.finditer(text):
            if _WARNING_BEFORE.search(text[max(0, match.start() - 40) : match.start()]):
                continue
            return match.group(0)
    return None


def assess(data: SafetyInput) -> SafetyAssessmentOut:
    found = _scan(data)

    # Conservative default for electrical jobs with no specific hazard: not "safe" just because nothing matched.
    electrical_found = any(rule.category in ("electrical", "gas") for rule, _ in found)
    if data.trade_id == "electrical" and not electrical_found:
        simple = any(_first_match(_SIMPLE_ELECTRICAL, seg) for seg in _segments(data))
        if not simple:
            found.append((ELECTRICAL_GENERAL, None))  # type: ignore[arg-type]

    answers = {qid: ans for qid, ans in data.clarifying_answers.items() if qid in QUESTIONS}
    high: list[MatchedHazardOut] = [h for h in data.extra_hazards if h.risk == "high"]
    medium: list[tuple[Rule, MatchedHazardOut]] = []
    resolved: list[str] = []

    for rule, text in found:
        if rule.risk == "high":
            high.append(_hazard(rule, "high", text))
            continue
        effects = []
        for qid in rule.questions:
            answer = answers.get(qid)
            if answer is None or answer == "not_sure":
                effects.append("keep" if answer == "not_sure" else "unanswered")
            else:
                q = QUESTIONS[qid]
                effects.append(q.on_yes if answer == "yes" else q.on_no)
        if "escalate" in effects:
            qid = rule.questions[effects.index("escalate")]
            high.append(_hazard(rule, "high", f"You answered yes: “{QUESTIONS[qid].text}”", id_suffix="_confirmed"))
        elif rule.questions and all(e == "resolve" for e in effects):
            resolved.append(rule.label)
        else:
            medium.append((rule, _hazard(rule, "medium", text)))

    # Remove duplicates (same hazard id), keeping the first.
    seen: set[str] = set()
    high = [h for h in high if not (h.id in seen or seen.add(h.id))]

    now = datetime.now(timezone.utc)
    answered = [
        AnsweredQuestionOut(id=qid, text=QUESTIONS[qid].text, answer=ans)  # type: ignore[arg-type]
        for qid, ans in answers.items()
    ]
    trade_pro = PROFESSIONAL_BY_TRADE.get(data.trade_id, "a qualified professional")

    if high:
        primary = min(high, key=lambda h: GUIDANCE.get(h.guidance, GUIDANCE["general_danger"]).priority)
        guide = GUIDANCE.get(primary.guidance, GUIDANCE["general_danger"])
        others = [h.label for h in high if h.label != primary.label]
        message = f"{guide.explanation} For your safety, MENDORA won't give do-it-yourself repair steps for this."
        if others:
            message += f" We also noticed: {', '.join(others)}."
        return SafetyAssessmentOut(
            risk_level="high",
            matched_hazards=high + [h for _, h in medium],
            allow_diy=False,
            requires_professional=True,
            recommended_action=guide.action,
            safety_message=message,
            emergency=guide.leave_area,
            emergency_steps=list(guide.steps),
            clarifying_questions=[],
            answered_questions=answered,
            resolved_hazards=resolved,
            ai_diagnosis="blocked",
            professional=guide.professional,
            rules_version=RULES_VERSION,
            assessed_at=now,
            disclaimer=DISCLAIMER,
        )

    if medium:
        pending_ids: list[str] = []
        for rule, _ in medium:
            for qid in rule.questions:
                if qid not in answers and qid not in pending_ids:
                    pending_ids.append(qid)
        first_rule = medium[0][0]
        professional = PROFESSIONAL_BY_CATEGORY.get(first_rule.category, trade_pro)
        labels = ", ".join(h.label.lower() for _, h in medium)
        message = f"Some details could point to a safety risk ({labels}). {first_rule.explanation} Do-it-yourself repair steps are switched off for now."
        action = f"Don't attempt a repair yourself yet. Have {professional} check it"
        action += " — or answer the questions below so we can assess it better." if pending_ids else "."
        return SafetyAssessmentOut(
            risk_level="medium",
            matched_hazards=[h for _, h in medium],
            allow_diy=False,
            requires_professional=True,
            recommended_action=action,
            safety_message=message,
            emergency=False,
            emergency_steps=[],
            clarifying_questions=[SafetyQuestionOut(id=qid, text=QUESTIONS[qid].text) for qid in pending_ids],
            answered_questions=answered,
            resolved_hazards=resolved,
            ai_diagnosis="professional_only",
            professional=professional,
            rules_version=RULES_VERSION,
            assessed_at=now,
            disclaimer=DISCLAIMER,
        )

    return SafetyAssessmentOut(
        risk_level="low",
        matched_hazards=[],
        allow_diy=True,
        requires_professional=False,
        recommended_action=(
            "You can continue to the AI diagnosis. Stop and get help straight away if you notice sparks, smoke, "
            "a burning or gas smell, or water near electrics."
        ),
        safety_message="The automatic safety check didn't find signs of immediate danger in what you described.",
        emergency=False,
        emergency_steps=[],
        clarifying_questions=[],
        answered_questions=answered,
        resolved_hazards=resolved,
        ai_diagnosis="full",
        professional=trade_pro,
        rules_version=RULES_VERSION,
        assessed_at=now,
        disclaimer=DISCLAIMER,
    )


def rule_label(rule_id: str) -> str:
    rule = RULES_BY_ID.get(rule_id)
    return rule.label if rule else rule_id
