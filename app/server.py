"""Backward-compatible ASGI entry point.

``uvicorn app.server:app`` keeps working for existing deployment scripts, while
new code should import ``app.main:app``.
"""

from app.main import app

__all__ = ["app"]
