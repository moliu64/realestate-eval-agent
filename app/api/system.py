"""Operational endpoints."""

from fastapi import APIRouter

from app import __version__
from app.api.models import HealthResponse

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="realestate-eval-agent", version=__version__)
