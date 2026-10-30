"""
Application entry point.

Start the server from the `backend` folder with:
    python -m uvicorn app.main:app --reload --port 8000

Then open http://localhost:8000/docs for the interactive API documentation.
"""

import os
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .ai.http import Transport, urllib_transport
from .api import api_router
from .config import env_file_path, Settings, get_settings
from .db import create_tables, make_engine, make_session_factory
from .errors import register_error_handlers
from .knowledge.store import get_knowledge
from .security import resolve_jwt_secret
from .services.rate_limit import RateLimiter

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
log = logging.getLogger("mendora")

API_DESCRIPTION = """
Backend for **MENDORA**, an AI-powered home repair assistant for plumbing, electrical and carpentry problems.

### How to sign in here
1. `POST /api/auth/register` (or `/api/auth/login`) and copy the `access_token`.
2. Click **Authorize** (top right), paste the token, and click Authorize.

### Safety first
Every report is checked by a **rule-based safety engine** (no AI needed) before any AI diagnosis:
**high** risk blocks AI and DIY guidance (409 `blocked_by_safety`), **medium** risk allows only a
professional-only assessment, **low** risk continues normally. Try it with `POST /api/safety/assess`.
The engine reads words; it can't see the problem and can miss things.

### ⚠️ Limitations
- **AI diagnosis needs configuration** (`MENDORA_AI_PROVIDER` + API key). Without it, diagnosis returns a clear
  `ai_not_configured` error — results are never invented.

**In an emergency** — sparking electrical equipment, a suspected gas leak, smoke, or structural danger —
move away and contact your local emergency service or a qualified professional.
"""


def create_app(settings: Settings | None = None, ai_transport: Transport | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings (temporary database) and a fake AI transport."""
    if settings is None:
        settings = get_settings()
        if os.environ.get("MENDORA_ENV_FILE"):
            log.warning("Using settings file %s (MENDORA_ENV_FILE)", env_file_path())

    get_knowledge()  # validate the knowledge base at startup: a bad or unsafe entry stops the server here

    engine = make_engine(settings.database_url)
    create_tables(engine)  # creates missing tables; existing data is kept

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    docs = settings.api_docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        debug=False,  # never show internal error details to visitors
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.jwt_secret = resolve_jwt_secret(settings)
    app.state.login_limiter = RateLimiter(settings.login_max_failures, settings.login_window_minutes * 60)
    app.state.diagnosis_limiter = RateLimiter(settings.diagnoses_per_user_per_hour, 3600)
    app.state.booking_limiter = RateLimiter(settings.bookings_per_user_per_hour, 3600)
    app.state.payment_limiter = RateLimiter(settings.payments_per_user_per_hour, 3600)
    app.state.ai_transport = ai_transport or urllib_transport

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Location", "Retry-After"],
    )

    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs" if docs else "/api/health")

    return app


app = create_app()
