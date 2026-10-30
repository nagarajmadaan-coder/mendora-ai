"""
Repair-request endpoints (stored in the database).

Who can see what:
- A request created while signed in belongs to that customer. Only they (and admins) can read it,
  answer its safety questions or ask for a diagnosis. Anyone else gets 404.
- A request created without signing in can be read by anyone who has its unguessable ID,
  but cannot be diagnosed.

Safety (Step 6): every request is safety-checked on the server when it is created, when its safety
questions are answered, and again right before any diagnosis. High-risk requests can never reach the AI.
"""

import logging

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from ...ai.errors import AIError
from ...ai import web_research
from ...ai.service import diagnose
from ...config import Settings
from ...errors import ApiError
from ...models import RepairRequest, User
from ...repositories import repair_requests as repo
from ...safety.engine import SafetyBlockedError
from ...schemas import (
    EXAMPLE_REQUEST_ID,
    DiagnosisRequest,
    ErrorResponse,
    RepairRequestCreate,
    RepairRequestListResponse,
    RepairRequestResponse,
    SafetyAnswersRequest,
    answers_to_dict,
)
from ...knowledge.service import build_guidance
from ...schemas_knowledge import KnowledgeGuidanceOut
from ...services.repair_requests import to_response
from ...services.safety_workflow import ensure_safety, escalate, refresh_safety
from ...services.trades import get_trade
from ..dependencies import get_app_settings, get_current_user, get_db, get_optional_user

log = logging.getLogger("mendora.api")
router = APIRouter(prefix="/repair-requests", tags=["Repair requests"])


def _not_found(request_id: str) -> ApiError:
    return ApiError(404, "repair_request_not_found", f"No repair request found with ID '{request_id}'.")


def _can_read(record: RepairRequest, user: User | None) -> bool:
    if record.customer_id is None:
        return True  # anonymous request: readable by anyone who has the ID
    return user is not None and (user.id == record.customer_id or user.role == "admin")


def _blocked_error(professional: str, action: str) -> ApiError:
    return ApiError(
        409,
        "blocked_by_safety",
        f"For your safety, MENDORA won't generate a diagnosis or repair steps for this request. {action}",
    )


VALIDATION_ERROR_EXAMPLE = {
    "error": {
        "code": "validation_error",
        "message": "The request is invalid. See 'details' for each problem.",
        "details": [
            {"field": "trade_id", "message": "Unsupported trade_id 'roofing'. Supported values: plumbing, electrical, carpentry."},
            {"field": "description", "message": "Description must not be empty."},
        ],
    }
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RepairRequestResponse,
    summary="Submit a repair request (it is safety-checked immediately)",
    description=(
        "Saves the request and runs the safety check on the server; the result is in `safety`. "
        "With a valid `Authorization: Bearer` token the request is private to your account. "
        "No diagnosis is generated here — use `POST /api/repair-requests/{id}/diagnosis`."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "A token was sent but is invalid or expired"},
        422: {"model": ErrorResponse, "content": {"application/json": {"example": VALIDATION_ERROR_EXAMPLE}}},
    },
)
def create_repair_request(
    payload: RepairRequestCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> RepairRequestResponse:
    record = repo.create(
        db,
        trade=payload.trade_id,
        description=payload.description,
        customer_id=user.id if user else None,
        safety_answers=answers_to_dict(payload.clarifying_answers),
    )
    refresh_safety(db, record)
    response.headers["Location"] = f"/api/repair-requests/{record.id}"
    return to_response(record)


@router.get(
    "",
    response_model=RepairRequestListResponse,
    summary="List my repair requests (newest first)",
    description="Customers see only their own requests. Admins see everyone's. Requires sign-in.",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def list_my_repair_requests(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RepairRequestListResponse:
    if user.role == "admin":
        rows, total = repo.list_all(db, limit=limit, offset=offset)
    elif user.role == "customer":
        rows, total = repo.list_for_customer(db, user.id, limit=limit, offset=offset)
    else:
        raise ApiError(403, "forbidden", "Technicians can't view customer request history.")
    for row in rows:
        ensure_safety(db, row)
    return RepairRequestListResponse(items=[to_response(r) for r in rows], total=total)


@router.get(
    "/{request_id}",
    response_model=RepairRequestResponse,
    summary="Get a repair request by ID",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Not found, or it belongs to another customer",
            "content": {"application/json": {"example": {"error": {"code": "repair_request_not_found", "message": f"No repair request found with ID '{EXAMPLE_REQUEST_ID}'.", "details": []}}}},
        }
    },
)
def get_repair_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> RepairRequestResponse:
    record = repo.get(db, request_id)
    if record is None or not _can_read(record, user):
        raise _not_found(request_id)
    ensure_safety(db, record)
    return to_response(record)


@router.get(
    "/{request_id}/guidance",
    response_model=KnowledgeGuidanceOut,
    summary="Knowledge-base guidance for a saved request (safety-checked)",
    description=(
        "Re-runs the safety check on the server, then searches the knowledge base. High risk → `blocked_by_safety` "
        "with no content; medium → entries without steps; low → entries with safe next steps."
    ),
    responses={404: {"model": ErrorResponse}},
)
def get_guidance(
    request_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> KnowledgeGuidanceOut:
    record = repo.get(db, request_id)
    if record is None or not _can_read(record, user):
        raise _not_found(request_id)
    safety = refresh_safety(db, record)
    text = " ".join([record.description, *[a["answer"] for a in (record.follow_up_answers or [])]])
    return build_guidance(trade_id=record.trade, text=text, safety=safety, db=db)


@router.post(
    "/{request_id}/safety-answers",
    response_model=RepairRequestResponse,
    summary="Answer the request's safety questions",
    description=(
        "Answers (yes / no / not_sure) to the questions in `safety.clarifying_questions`. The safety check is re-run on "
        "the server. Answers can raise the risk to high or clear a medium concern; a high risk is never lowered."
    ),
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def answer_safety_questions(
    request_id: str,
    payload: SafetyAnswersRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> RepairRequestResponse:
    record = repo.get(db, request_id)
    if record is None or not _can_read(record, user):
        raise _not_found(request_id)
    record.safety_answers = {**(record.safety_answers or {}), **answers_to_dict(payload.answers)}
    refresh_safety(db, record)
    return to_response(record)


@router.post(
    "/{request_id}/diagnosis",
    response_model=RepairRequestResponse,
    summary="Run an AI diagnosis for a request (only after the safety check allows it)",
    description=(
        "The safety check is re-run on the server first, including any new follow-up answers.\n\n"
        "- **High risk** → `409 blocked_by_safety`. The AI is never called, whatever the client sends.\n"
        "- **Medium risk** → professional-only assessment: possible causes may be explained, but no DIY steps.\n"
        "- **Low risk** → normal assessment. Anything unsafe the AI suggests is removed.\n\n"
        "If the AI flags urgent danger, the request is escalated to high risk and no diagnosis is saved. "
        "If the AI isn't configured or fails, an error is returned and **no diagnosis is invented**. "
        "Requires sign-in; only the request's owner (or an admin) can do this."
    ),
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse, "description": "Anonymous request"},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "Blocked by the safety check (high risk)"},
        429: {"model": ErrorResponse, "description": "Too many diagnoses this hour"},
        502: {"model": ErrorResponse, "description": "AI provider error or unusable response"},
        503: {"model": ErrorResponse, "description": "AI not configured, or provider busy"},
        504: {"model": ErrorResponse, "description": "AI provider timed out"},
    },
)
def diagnose_repair_request(
    request_id: str,
    request: Request,
    payload: DiagnosisRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_app_settings),
) -> RepairRequestResponse:
    record = repo.get(db, request_id)
    if record is None or not _can_read(record, user):
        raise _not_found(request_id)
    if record.customer_id is None:
        raise ApiError(403, "sign_in_required", "AI diagnosis is only available for requests created while signed in.")

    # 1. Safety first: store the new answers, then re-run the safety check on the server.
    answers = (payload or DiagnosisRequest()).follow_up_answers
    if answers:
        repo.add_follow_up_answers(record, [a.model_dump() for a in answers])
    safety = refresh_safety(db, record)
    if safety.risk_level == "high":
        raise _blocked_error(safety.professional, safety.recommended_action)

    # 2. Rate limit (counted only for calls that may actually reach the AI).
    limiter = request.app.state.diagnosis_limiter
    if limiter.is_limited(user.id):
        raise ApiError(
            429,
            "too_many_requests",
            "You've requested many diagnoses recently. Please wait a while and try again.",
            headers={"Retry-After": str(limiter.retry_after(user.id))},
        )
    limiter.hit(user.id)

    # 3. AI diagnosis, under the safety decision.
    trade = get_trade(record.trade)
    try:
        outcome = diagnose(
            trade_id=record.trade,
            trade_name=trade.name if trade else record.trade,
            description=record.description,
            follow_up_answers=[(a["question"], a["answer"]) for a in (record.follow_up_answers or [])],
            safety=safety,
            settings=settings,
            transport=request.app.state.ai_transport,
        )
    except SafetyBlockedError as exc:  # defence in depth; the check above should already have stopped this
        raise _blocked_error(safety.professional, safety.recommended_action) from exc
    except AIError as exc:
        log.warning("Diagnosis failed for %s: %s (%s)", record.id, exc.code, exc.internal_detail)
        repo.mark_diagnosis_failed(db, record, error_code=exc.code)
        raise ApiError(exc.status_code, exc.code, exc.public_message) from exc

    if outcome.escalation is not None:
        escalate(db, record, outcome.escalation)
        return to_response(record)  # now high risk: no diagnosis, safety advice instead

    record = repo.save_diagnosis(db, record, diagnosis=outcome.diagnosis)  # type: ignore[arg-type]
    return to_response(record)


_WEB_MESSAGES = {
    "web_research_not_configured": "AI web research isn't set up on this server (no Tavily API key). Nothing was searched.",
    "ai_timeout": "The web research service took too long to respond. Please try again.",
    "ai_rate_limited": "The web research service is busy or its usage limit was reached. Please try again later.",
    "ai_provider_error": "The web research service returned an error (check the Tavily API key). Nothing was shown.",
}


@router.post(
    "/{request_id}/web-research",
    response_model=web_research.WebResearchOut,
    summary="AI web research (Tavily): an AI summary of public web pages + sources",
    description=(
        "Separate from the AI diagnosis. The safety check is re-run first:\n\n"
        "- **High risk** → `409 blocked_by_safety`; nothing is searched.\n"
        "- **Medium risk** → source links only (no summary, no how-to text).\n"
        "- **Low risk** → Tavily's AI summary and short snippets, screened sentence by sentence.\n\n"
        "Only the trade and the description (emails/phone numbers removed) are sent. Owner or admin only."
    ),
    responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def web_research_for_request(
    request_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_app_settings),
) -> web_research.WebResearchOut:
    record = repo.get(db, request_id)
    if record is None or not _can_read(record, user):
        raise _not_found(request_id)
    if record.customer_id is None:
        raise ApiError(403, "sign_in_required", "AI web research is only available for requests created while signed in.")
    safety = refresh_safety(db, record)
    if safety.risk_level == "high":
        raise _blocked_error(safety.professional, safety.recommended_action)

    limiter = request.app.state.diagnosis_limiter
    key = f"web:{user.id}"
    if limiter.is_limited(key):
        raise ApiError(429, "too_many_requests", "You've run many web searches recently. Please wait a while and try again.",
                       headers={"Retry-After": str(limiter.retry_after(key))})
    limiter.hit(key)

    trade = get_trade(record.trade)
    try:
        return web_research.research(
            trade_name=trade.name if trade else record.trade,
            description=record.description,
            safety=safety,
            settings=settings,
            transport=request.app.state.ai_transport,
        )
    except SafetyBlockedError as exc:
        raise _blocked_error(safety.professional, safety.recommended_action) from exc
    except AIError as exc:
        log.warning("Web research failed for %s: %s (%s)", record.id, exc.code, exc.internal_detail)
        raise ApiError(exc.status_code, exc.code, _WEB_MESSAGES.get(exc.code, "The web research service failed. Nothing was shown.")) from exc
