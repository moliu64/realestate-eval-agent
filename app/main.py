"""FastAPI application factory.

The web layer is split into small routers (``app.api``) and framework-agnostic
services (``app.services``). This module only wires them together and applies
the cross-cutting HTTP policy: security headers and local static caching.

The application is designed for local use only (``127.0.0.1``); there is no
domain, tunnel or reverse-proxy specific behavior.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import admin, auth, sessions, system, valuation
from app.config import STATIC_DIR, load_config
from app.logging_config import configure_logging, get_logger
from app.services.errors import ServiceError

logger = get_logger(__name__)

_STATIC_CACHE = "public, max-age=31536000, immutable"
_HTML_CACHE = "no-cache"
_HTML_PATHS = {"/", "/admin"}


async def _service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def create_app() -> FastAPI:
    configure_logging()
    config = load_config()

    application = FastAPI(
        title="RealEstate Eval Agent",
        version=__version__,
        description="面向房地产估价场景的 RAG + LangGraph 智能体工作台。",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    application.add_exception_handler(ServiceError, _service_error_handler)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    application.include_router(auth.router)
    application.include_router(sessions.router)
    application.include_router(valuation.router)
    application.include_router(admin.router)
    application.include_router(system.router)

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path in _HTML_PATHS:
            response.headers["Cache-Control"] = _HTML_CACHE
            response.headers["Pragma"] = "no-cache"
        elif request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = _STATIC_CACHE
        elif request.url.path.startswith("/api/") or request.url.path.startswith("/admin/"):
            response.headers["Cache-Control"] = "no-store"

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    logger.info("application ready: model=%s embedding=%s", config.model, config.embedding_model)
    return application


app = create_app()
