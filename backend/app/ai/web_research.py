"""
AI web research (Tavily).

Tavily searches the web and writes a short AI summary of what it found, with the source pages.
It is NOT the AI diagnosis: it reads public web pages, not your situation, so it can be wrong or
out of date. MENDORA labels it that way everywhere.

Safety (the rule engine stays in charge):
  * high risk   → never called (409 blocked_by_safety)
  * medium risk → links to sources only; no summary and no snippets, because they may contain DIY steps
  * low risk    → summary + snippets, each sentence screened; anything unsafe is removed
Privacy: only the trade and the problem description are sent, with emails / phone numbers removed.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from ..config import Settings
from ..safety.engine import SafetyBlockedError, find_unsafe_instruction
from ..schemas import SafetyAssessmentOut
from .errors import AIError, AINotConfigured, AIProviderError, AIRateLimited
from .http import Transport, urllib_transport
from .privacy import redact
from .providers import _post_with_retry

log = logging.getLogger("mendora.web_research")

TAVILY_URL = "https://api.tavily.com/search"
DISCLAIMER = (
    "AI web research summarises public web pages found by Tavily. It isn't a diagnosis of your problem, "
    "can be wrong or out of date, and hasn't been checked by a professional. The safety advice above always comes first."
)


class WebSource(BaseModel):
    title: str
    url: str
    domain: str
    snippet: str | None = None


class WebResearchOut(BaseModel):
    provider: Literal["tavily"] = "tavily"
    mode: Literal["full", "sources_only"] = Field(description="full = low risk; sources_only = medium risk (no summary)")
    query_sent: str = Field(description="Exactly what was sent to the search service (personal details removed)")
    answer: str | None = Field(description="Tavily's AI summary of the web pages (low risk only, safety-screened)")
    answer_note: str | None = None
    sources: list[WebSource]
    safety_filter_applied: bool
    disclaimer: str = DISCLAIMER
    generated_at: datetime


class WebResearchNotConfigured(AINotConfigured):
    code = "web_research_not_configured"
    public_message = "AI web research isn't set up on this server (no Tavily API key). Nothing was searched."


def status(settings: Settings) -> dict:
    return {"provider": "tavily", "configured": bool(settings.tavily_key)}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _screen(text: str) -> tuple[str, bool]:
    """Keep only sentences the safety screen accepts. Returns (text, something_removed)."""
    kept, removed = [], False
    for sentence in _sentences(text):
        if find_unsafe_instruction(sentence):
            removed = True
        else:
            kept.append(sentence)
    return " ".join(kept), removed


def build_query(trade_name: str, description: str) -> str:
    clean = " ".join(redact(description).split())[:300]
    return f"{trade_name} home repair: {clean} — likely causes and safe first checks"


def research(
    *,
    trade_name: str,
    description: str,
    safety: SafetyAssessmentOut,
    settings: Settings,
    transport: Transport | None = None,
) -> WebResearchOut:
    if safety.risk_level == "high" or safety.ai_diagnosis == "blocked":
        raise SafetyBlockedError("High-risk case: web research is not allowed.")
    key = settings.tavily_key
    if not key:
        raise WebResearchNotConfigured("TAVILY_API_KEY not set")

    mode = "full" if safety.risk_level == "low" else "sources_only"
    query = build_query(trade_name, description)
    payload = {
        "query": query,
        "search_depth": "basic",
        "include_answer": mode == "full",
        "max_results": 5,
        "api_key": key,  # older Tavily API versions read the key here; newer ones use the header
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        data = _post_with_retry(transport or urllib_transport, TAVILY_URL, headers, payload, settings.ai_timeout_seconds, "tavily")
    except AIProviderError as exc:
        if "(432)" in str(exc) or "(433)" in str(exc) or "HTTP 432" in str(exc) or "HTTP 433" in str(exc):
            raise AIRateLimited("tavily plan/usage limit reached") from exc
        raise
    if not isinstance(data, dict):
        raise AIProviderError("tavily returned an unexpected body")

    filtered = False
    answer, note = None, None
    if mode == "full":
        raw = data.get("answer")
        if isinstance(raw, str) and raw.strip():
            answer, removed = _screen(raw.strip()[:2000])
            filtered = filtered or removed
            if removed:
                note = "Some sentences were removed because they described work that isn't safe to do yourself."
            if not answer:
                answer = None
                note = "The summary was removed because it described work that isn't safe to do yourself."
        else:
            note = "Tavily didn't return a summary for this search."
    else:
        note = (
            "Because the safety check found a possible risk, MENDORA shows only links — no summary or how-to text. "
            f"Please contact {safety.professional}."
        )

    sources: list[WebSource] = []
    for item in (data.get("results") or [])[:5]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue  # never show a javascript: or broken link
        title = " ".join(str(item.get("title") or parsed.netloc).split())[:200]
        snippet = None
        if mode == "full" and isinstance(item.get("content"), str):
            snippet, removed = _screen(" ".join(item["content"].split())[:400])
            filtered = filtered or removed
            snippet = snippet or None
        sources.append(WebSource(title=title, url=url, domain=parsed.netloc.removeprefix("www."), snippet=snippet))

    return WebResearchOut(
        mode=mode,
        query_sent=query,
        answer=answer,
        answer_note=note,
        sources=sources,
        safety_filter_applied=filtered,
        generated_at=datetime.now(timezone.utc),
    )


__all__ = ["AIError", "WebResearchOut", "research", "status", "build_query"]
