"""
Knowledge base endpoints (Step 7).

Browsing (`/entries`) never returns repair steps. Steps are only returned by `/search`
(or a saved request's `/guidance`), AFTER the safety engine has assessed the problem.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...errors import ApiError
from ...knowledge.service import build_guidance, entries_by_id, to_detail, to_summary
from ...knowledge.store import get_knowledge
from ...safety.engine import SafetyInput, assess
from ...schemas import ErrorResponse, SafetyAssessRequest, answers_to_dict
from ...schemas_knowledge import KnowledgeEntryDetail, KnowledgeEntryList, KnowledgeGuidanceOut
from ..dependencies import get_db

router = APIRouter(prefix="/knowledge", tags=["Knowledge base"])


@router.get("/entries", response_model=KnowledgeEntryList, summary="Browse knowledge-base entries (no repair steps)")
def list_entries(trade: str | None = Query(None, pattern="^(plumbing|electrical|carpentry)$")) -> KnowledgeEntryList:
    kb = get_knowledge()
    entries = [e for e in kb.entries if trade is None or e.trade == trade]
    return KnowledgeEntryList(entries=[to_summary(e) for e in entries], total=len(entries), knowledge_version=kb.version)


@router.get(
    "/entries/{entry_id}",
    response_model=KnowledgeEntryDetail,
    summary="One entry's causes, questions and safety notes (no repair steps)",
    responses={404: {"model": ErrorResponse}},
)
def get_entry(entry_id: str) -> KnowledgeEntryDetail:
    entry = entries_by_id().get(entry_id)
    if entry is None:
        raise ApiError(404, "knowledge_entry_not_found", f"No knowledge entry with ID '{entry_id}'.")
    return to_detail(entry)


@router.post(
    "/search",
    response_model=KnowledgeGuidanceOut,
    summary="Find matching repair knowledge — after a safety check",
    description=(
        "Runs the Step 6 safety check first, then searches the knowledge base. **High risk** returns no content "
        "(`blocked_by_safety`); **medium** returns entries without steps; **low** returns entries with safe next steps. "
        "If nothing matches, `status` is `no_match` — no answer is invented. Nothing is saved."
    ),
    responses={422: {"model": ErrorResponse}},
)
def search(payload: SafetyAssessRequest, db: Session = Depends(get_db)) -> KnowledgeGuidanceOut:
    follow_ups = [(a.question, a.answer) for a in payload.follow_up_answers]
    safety = assess(
        SafetyInput(
            trade_id=payload.trade_id,
            description=payload.description,
            follow_up_answers=follow_ups,
            clarifying_answers=answers_to_dict(payload.clarifying_answers),
        )
    )
    text = " ".join([payload.description, *[a for _, a in follow_ups]])
    return build_guidance(trade_id=payload.trade_id, text=text, safety=safety, db=db)
