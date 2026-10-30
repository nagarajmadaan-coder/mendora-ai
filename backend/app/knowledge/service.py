"""
Safety-gated repair guidance from the knowledge base.

    build_guidance(trade_id, text, safety, db) -> KnowledgeGuidanceOut

The Step 6 safety assessment MUST be computed first and passed in. It always wins:
  high   → nothing from the knowledge base is shown (status "blocked_by_safety")
  medium → matching entries are shown WITHOUT any steps (causes, questions, "see a professional")
  low    → entries with their safe next steps
Retrieved content can never lower the risk, and every step is re-screened for unsafe wording.
"""

from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RepairCase
from ..safety.engine import find_unsafe_instruction
from ..schemas import SafetyAssessmentOut
from ..schemas_knowledge import (
    GuidanceEntryOut,
    KnowledgeCauseOut,
    KnowledgeEntryDetail,
    KnowledgeEntrySummary,
    KnowledgeGuidanceOut,
    KnowledgeMatchOut,
    KnowledgeSourceOut,
    SimilarCaseOut,
)
from .retrieval import Document, KeywordRetriever, Retriever, get_retriever
from .store import KnowledgeEntry, get_knowledge

DISCLAIMER = (
    "Knowledge-base entries are written by the MENDORA team from general home-maintenance knowledge and have NOT been "
    "reviewed by a licensed professional. Causes are possibilities, not a diagnosis. Stop and get help if anything seems unsafe."
)


@lru_cache
def get_kb_retriever() -> Retriever:
    return get_retriever(get_knowledge().entries)


def entries_by_id() -> dict[str, KnowledgeEntry]:
    return {e.id: e for e in get_knowledge().entries}


def _source(entry: KnowledgeEntry) -> KnowledgeSourceOut:
    src = entry.source
    assert src is not None
    return KnowledgeSourceOut(type=src.type, verification_status=src.verification_status, note=src.note)


def to_summary(entry: KnowledgeEntry) -> KnowledgeEntrySummary:
    return KnowledgeEntrySummary(
        id=entry.id,
        trade=entry.trade,
        category=entry.category,
        title=entry.title,
        symptoms=entry.symptoms,
        professional_recommended=entry.professional_recommended,
        source=_source(entry),
    )


def to_detail(entry: KnowledgeEntry) -> KnowledgeEntryDetail:
    return KnowledgeEntryDetail(
        **to_summary(entry).model_dump(),
        clarifying_questions=entry.clarifying_questions,
        possible_causes=[KnowledgeCauseOut(title=c.title, explanation=c.explanation) for c in entry.possible_causes],
        professional_reason=entry.professional_reason,
        safety_restrictions=entry.safety_restrictions,
        hazard_categories=list(entry.hazard_categories),
    )


def _gated_entry(entry: KnowledgeEntry, safety: SafetyAssessmentOut) -> GuidanceEntryOut:
    detail = to_detail(entry).model_dump()
    if safety.risk_level != "low" or not safety.allow_diy:
        detail["professional_recommended"] = True
        detail["professional_reason"] = detail["professional_reason"] or "The safety check found a possible risk."
        return GuidanceEntryOut(
            **detail,
            next_steps=[],
            steps_shown=False,
            steps_note=f"Step-by-step guidance is hidden because the safety check found a possible risk. Have {safety.professional} check it.",
        )
    steps = [s for s in entry.next_steps if not find_unsafe_instruction(s)]  # defence in depth
    note = None
    if entry.diy_level == "none":
        note = f"These are safe checks only. The repair itself should be done by {safety.professional}."
    return GuidanceEntryOut(**detail, next_steps=steps, steps_shown=True, steps_note=note)


def _similar_cases(db: Session | None, trade_id: str, text: str, limit: int = 2) -> list[SimilarCaseOut]:
    if db is None:
        return []
    cases = db.scalars(
        select(RepairCase).where(RepairCase.verification_status == "verified", RepairCase.trade == trade_id)
    ).all()
    if not cases:
        return []
    docs = [
        Document(
            id=c.id,
            trade=c.trade,
            text_fields={"symptoms": c.symptoms, "category": c.category or "", "cause": c.confirmed_cause or ""},
            weights={"symptoms": 1.2, "category": 0.8, "cause": 1.0},
        )
        for c in cases
    ]
    hits = KeywordRetriever(docs, min_score=0.25).search(text, trade=trade_id, limit=limit)
    by_id = {c.id: c for c in cases}
    out = []
    for hit in hits:
        c = by_id[hit.id]
        out.append(
            SimilarCaseOut(
                case_id=c.id,
                trade=c.trade,  # type: ignore[arg-type]
                category=c.category,
                symptoms_summary=c.symptoms[:300],
                confirmed_cause=c.confirmed_cause or "",
                parts_used=list(c.parts_used or []),
                completion_minutes=c.completion_minutes,
                cost_amount=c.cost_amount,
                currency=c.currency,
                relevance=hit.score,
            )
        )
    return out


def build_guidance(*, trade_id: str, text: str, safety: SafetyAssessmentOut, db: Session | None = None, limit: int = 3) -> KnowledgeGuidanceOut:
    kb = get_knowledge()
    retriever = get_kb_retriever()
    common = {"safety": safety, "retriever": retriever.name, "knowledge_version": kb.version, "disclaimer": DISCLAIMER}

    if safety.risk_level == "high":
        return KnowledgeGuidanceOut(
            status="blocked_by_safety",
            mode="blocked",
            message=f"For your safety, repair guidance isn't shown for this problem. {safety.recommended_action}",
            matches=[],
            similar_verified_cases=[],
            **common,
        )

    mode = "full" if safety.risk_level == "low" and safety.allow_diy else "professional_only"
    hits = retriever.search(text, trade=trade_id, limit=limit)
    entries = entries_by_id()
    matches = [
        KnowledgeMatchOut(entry=_gated_entry(entries[h.id], safety), relevance=h.score, matched_terms=list(h.matched_terms))
        for h in hits
        if h.id in entries
    ]
    cases = _similar_cases(db, trade_id, text)

    if not matches:
        follow = (
            f"You can still try the AI diagnosis, or contact {safety.professional}."
            if mode == "full"
            else f"Please follow the safety advice and have {safety.professional} check it."
        )
        return KnowledgeGuidanceOut(
            status="no_match",
            mode=mode,  # type: ignore[arg-type]
            message=f"We don't have a knowledge-base entry that matches this problem yet. {follow}",
            matches=[],
            similar_verified_cases=cases,
            **common,
        )

    message = (
        "These entries may match your problem. Check the possible causes and safe next steps."
        if mode == "full"
        else f"These entries may explain the problem, but steps are hidden because of a possible risk. Have {safety.professional} check it."
    )
    return KnowledgeGuidanceOut(status="matched", mode=mode, message=message, matches=matches, similar_verified_cases=cases, **common)  # type: ignore[arg-type]
