from fastapi import APIRouter, Depends

from ...ai import web_research
from ...ai.service import ai_status
from ...config import Settings
from ...safety.rules import RULES_VERSION
from ...schemas import HealthResponse
from ..dependencies import get_app_settings

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Check that the API is running")
def health(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        message="MENDORA API is running.",
        storage="database",
        safety_engine=HealthResponse.SafetyEngineStatus(enabled=True, rules_version=RULES_VERSION, needs_ai_key=False),
        ai_diagnosis=HealthResponse.AIStatus(**ai_status(settings)),
        web_research=HealthResponse.WebResearchStatus(**web_research.status(settings)),
        payments=HealthResponse.PaymentStatus(provider=settings.payment_provider, enabled=settings.payment_provider != "none"),
    )
