"""
TRIAL diagnosis provider using Tavily (MENDORA_AI_PROVIDER=tavily).

Tavily is a web-search service with a built-in AI summary. It is NOT a full AI model:
it doesn't read the safety rules or reason about your case, so this mode is for testing only.
It's labelled "Trial — web search summary" everywhere it appears.

What it returns (in the same shape as a real AI diagnosis, so the normal safety checks still run):
  * low risk    → Tavily's AI summary of web pages about the problem, screened sentence by sentence
  * medium risk → no web text at all (it may contain DIY steps); only links, and "get a professional"
  * possible causes and follow-up questions are left EMPTY — Tavily doesn't produce them and MENDORA won't invent them
High-risk cases never reach this code (the diagnosis service refuses them first).
"""

from urllib.parse import urlparse

from .errors import AIInvalidResponse, AIProviderError, AIRateLimited
from .http import Transport
from .prompts import DiagnosisInput
from .providers import _post_with_retry
from .web_research import TAVILY_URL, _screen

TRIAL_MODEL = "tavily-search (trial)"
TRIAL_DISCLAIMER = (
    "TRIAL MODE — this is a Tavily web-search summary, not a full AI diagnosis. It's written from public web pages "
    "about problems like yours, so it can be wrong or out of date, and nobody has checked it. MENDORA cannot see the "
    "problem. If anything seems unsafe, stop and contact a qualified professional."
)
MEDIUM_SUMMARY = (
    "The safety check found a possible risk, so the trial doesn't show any web text for this problem "
    "(it could include repair steps that aren't safe to do yourself). The links below are for background reading only."
)


def build_query(data: DiagnosisInput) -> str:
    text = " ".join(data.description.split())
    extra = " ".join(f"{a}" for _, a in data.follow_up_answers if a)
    query = f"{data.trade_name} home repair problem: {text} {extra}".strip()
    return f"{query[:330]} — most likely causes and when to call a professional"


class TavilyTrialProvider:
    name = "tavily"

    def __init__(self, *, api_key: str, model: str, transport: Transport, timeout: float, max_tokens: int = 0, base_url: str | None = None):
        self.api_key = api_key
        self.model = TRIAL_MODEL
        self.transport = transport
        self.timeout = timeout

    def generate(self, data: DiagnosisInput) -> dict:
        full = data.safety_mode == "full"
        payload = {
            "query": build_query(data),
            "search_depth": "advanced",
            "include_answer": "advanced" if full else False,
            "max_results": 5,
            "api_key": self.api_key,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            body = _post_with_retry(self.transport, TAVILY_URL, headers, payload, self.timeout, "tavily")
        except AIProviderError as exc:
            if any(code in str(exc) for code in ("432", "433")):
                raise AIRateLimited("tavily plan/usage limit reached") from exc
            raise
        if not isinstance(body, dict):
            raise AIInvalidResponse("tavily returned an unexpected body")

        sources = []
        for item in (body.get("results") or [])[:5]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                continue
            title = " ".join(str(item.get("title") or parsed.netloc).split())[:200]
            sources.append({"title": title, "url": url, "domain": parsed.netloc.removeprefix("www.")})

        filtered = False
        if full:
            raw = body.get("answer")
            if not isinstance(raw, str) or not raw.strip():
                raise AIInvalidResponse("tavily returned no summary")  # never make one up
            summary, filtered = _screen(" ".join(raw.split())[:1200])
            if not summary:
                summary = f"You reported a {data.trade_name.lower()} problem. The web summary was removed because it described work that isn't safe to do yourself."
            next_step = (
                "Use this summary only as background. If the problem continues or you're unsure, "
                f"book a verified {data.trade_name.lower()} technician through MENDORA."
            )
        else:
            summary = MEDIUM_SUMMARY
            next_step = "Have a professional check it."  # the service replaces this with the exact professional

        return {
            "summary": summary[:1200],
            "possible_causes": [],
            "follow_up_questions": [],
            "recommended_next_step": next_step,
            "professional_recommended": not full,
            "professional_reason": "",
            "urgent_danger": False,  # Tavily can't judge danger; MENDORA's rule-based safety check already ran
            # extra keys (read by the service, ignored by validation)
            "_sources": sources,
            "_filtered": filtered,
        }
