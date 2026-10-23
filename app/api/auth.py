"""Authentication endpoints: login, registration, logout and session probe."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_principal, is_secure_request
from app.api.models import LoginRequest, RegisterRequest
from app.services import auth_store
from app.services.errors import InvalidInputError, UnauthorizedError

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    account = auth_store.authenticate(payload.username, payload.password)
    if not account:
        raise UnauthorizedError("用户名或密码错误。")
    token, principal = auth_store.create_session(account["username"], account["role"])
    response.set_cookie(
        auth_store.AUTH_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=is_secure_request(request),
        max_age=auth_store.SESSION_TTL_SECONDS,
    )
    return {
        "authenticated": True,
        "username": principal["username"],
        "role": principal["role"],
        "expires_at": principal["expires_at"],
    }


@router.post("/register")
def register(payload: RegisterRequest) -> dict[str, Any]:
    if payload.password != payload.confirm_password:
        raise InvalidInputError("两次输入的密码不一致。")
    account = auth_store.register_user(payload.username, payload.password)
    return {"registered": True, "username": account["username"], "role": account["role"]}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    auth_store.revoke_session(request.cookies.get(auth_store.AUTH_COOKIE, ""))
    response.delete_cookie(auth_store.AUTH_COOKIE)
    return {"logged_out": True}


@router.get("/me")
def auth_me(principal: dict[str, Any] | None = Depends(get_principal)) -> dict[str, Any]:
    if not principal:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "username": principal["username"],
        "role": principal["role"],
        "expires_at": principal["expires_at"],
    }
