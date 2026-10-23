"""Authentication, password hashing and in-memory login sessions."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from threading import Lock
from typing import Any

from app.config import load_config
from app.services.errors import ConflictError, ServiceError

AUTH_COOKIE = "realestate_auth"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
VALID_ROLES = {"admin", "user"}

_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSIONS_LOCK = Lock()
_USERS_LOCK = Lock()


def _normalized_role(role: str) -> str:
    return role if role in VALID_ROLES else "user"


def load_registered_users() -> dict[str, dict[str, str]]:
    """Read self-registered users from the local JSON store."""

    path = load_config().auth_users_file
    from pathlib import Path

    user_file = Path(path)
    if not user_file.exists():
        return {}
    try:
        payload = json.loads(user_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceError("注册账号数据无法读取。") from exc
    if not isinstance(payload, dict):
        return {}
    return {
        str(username): {"password": str(details.get("password", "")), "role": "user"}
        for username, details in payload.items()
        if isinstance(details, dict) and details.get("password")
    }


def save_registered_users(users: dict[str, dict[str, str]]) -> None:
    from pathlib import Path

    user_file = Path(load_config().auth_users_file)
    user_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = user_file.with_suffix(".tmp")
    temporary.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(user_file)


def find_user(username: str) -> dict[str, str] | None:
    """Look up an account in configured and registered users (case-insensitive)."""

    target = username.strip().casefold()
    for candidate, account in load_config().auth_users.items():
        if candidate.casefold() == target:
            return {
                "username": candidate,
                "password": account.get("password", ""),
                "role": _normalized_role(account.get("role", "user")),
            }
    for candidate, account in load_registered_users().items():
        if candidate.casefold() == target:
            return {
                "username": candidate,
                "password": account.get("password", ""),
                "role": _normalized_role(account.get("role", "user")),
            }
    return None


def register_user(username: str, password: str) -> dict[str, str]:
    """Create a regular user account, rejecting duplicates atomically."""

    username = username.strip()
    with _USERS_LOCK:
        if find_user(username):
            raise ConflictError("用户名已存在，请更换用户名。")
        users = load_registered_users()
        users[username] = {"password": hash_password(password), "role": "user"}
        save_registered_users(users)
    return {"username": username, "role": "user"}


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    account = find_user(username)
    if not account or not verify_password(password, account["password"]):
        return None
    return {"username": account["username"], "role": account["role"], "expires_at": 0.0}


def create_session(username: str, role: str) -> tuple[str, dict[str, Any]]:
    """Issue an opaque login token and return it with the principal payload."""

    token = secrets.token_urlsafe(32)
    principal = {
        "username": username,
        "role": _normalized_role(role),
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    with _SESSIONS_LOCK:
        _purge_expired_sessions()
        _SESSIONS[token] = principal
    return token, principal


def get_principal(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    with _SESSIONS_LOCK:
        principal = _SESSIONS.get(token)
        if principal and principal["expires_at"] <= time.time():
            _SESSIONS.pop(token, None)
            return None
        return dict(principal) if principal else None


def revoke_session(token: str) -> None:
    if not token:
        return
    with _SESSIONS_LOCK:
        _SESSIONS.pop(token, None)


def _purge_expired_sessions() -> None:
    now = time.time()
    expired = [token for token, principal in _SESSIONS.items() if principal["expires_at"] <= now]
    for token in expired:
        _SESSIONS.pop(token, None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return f"pbkdf2_sha256$260000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds_text, salt_hex, digest_hex = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(rounds_text),
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(digest.hex(), digest_hex)
    # Plain-text passwords are only allowed for accounts injected through .env.
    return bool(stored) and hmac.compare_digest(stored, password)
