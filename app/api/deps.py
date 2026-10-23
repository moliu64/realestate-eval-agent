"""Shared FastAPI dependencies: authentication and ownership helpers."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request

from app.services import auth_store
from app.services.errors import ForbiddenError, UnauthorizedError


def get_principal(request: Request) -> dict[str, Any] | None:
    """Return the logged-in principal, or ``None`` for anonymous requests."""

    return auth_store.get_principal(request.cookies.get(auth_store.AUTH_COOKIE, ""))


def require_user(principal: dict[str, Any] | None = Depends(get_principal)) -> dict[str, Any]:
    if not principal:
        raise UnauthorizedError("请先登录。")
    return principal


def require_admin(principal: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if principal.get("role") != "admin":
        raise ForbiddenError("只有管理员可以管理知识库。")
    return principal


def current_owner(principal: dict[str, Any] = Depends(require_user)) -> str:
    return f"user:{principal['username']}"


def is_secure_request(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return forwarded_proto.lower() == "https"
