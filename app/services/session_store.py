"""JSON-file session store with atomic writes and per-session locking.

The store is intentionally simple: one JSON document per valuation session.
It is enough for a single-process demo deployment and keeps every conversation
inspectable with a text editor.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from app.config import load_config
from app.services.errors import InvalidInputError, NotFoundError, ServiceError

SESSION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_LOCKS: dict[str, Lock] = {}
_LOCKS_GUARD = Lock()


def _sessions_dir() -> Path:
    return Path(load_config().sessions_dir)


def _lock_for(session_id: str) -> Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(session_id, Lock())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def session_path(session_id: str) -> Path:
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise InvalidInputError("非法会话编号。")
    return _sessions_dir() / f"{session_id}.json"


def new_session(owner_id: str) -> dict[str, Any]:
    now = now_iso()
    return {
        "id": uuid.uuid4().hex,
        "owner_id": owner_id,
        "title": "新建估价会话",
        "created_at": now,
        "updated_at": now,
        "fixed_fields": {},
        "layout_description": "",
        "layout_filename": "",
        "messages": [],
    }


def summary(session: dict[str, Any]) -> dict[str, Any]:
    user_messages = [
        message.get("content", "")
        for message in session.get("messages", [])
        if message.get("role") == "user"
    ]
    return {
        "id": session["id"],
        "title": session.get("title") or "未命名估价",
        "updated_at": session.get("updated_at", ""),
        "message_count": len(session.get("messages", [])),
        "last_user_message": user_messages[-1] if user_messages else "暂无用户输入",
    }


def create_session(owner_id: str) -> dict[str, Any]:
    session = new_session(owner_id)
    write_session(session)
    return session


def list_sessions(owner_id: str) -> list[dict[str, Any]]:
    directory = _sessions_dir()
    if not directory.exists():
        return []
    sessions: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if session.get("owner_id") == owner_id:
            sessions.append(summary(session))
    return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)


def read_session(session_id: str, owner_id: str) -> dict[str, Any]:
    path = session_path(session_id)
    if not path.exists():
        raise NotFoundError("会话不存在。")
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceError("会话数据无法读取。") from exc
    if session.get("owner_id") != owner_id:
        raise NotFoundError("会话不存在。")
    return session


def write_session(session: dict[str, Any]) -> None:
    path = session_path(session["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def delete_session(session_id: str, owner_id: str) -> None:
    path = session_path(session_id)
    with _lock_for(session_id):
        session = read_session(session_id, owner_id)
        path.unlink(missing_ok=True)
        _LOCKS.pop(session["id"], None)


def mutate_session(
    session_id: str,
    owner_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Read, mutate and persist one session while holding its lock."""

    with _lock_for(session_id):
        session = read_session(session_id, owner_id)
        mutate(session)
        session["updated_at"] = now_iso()
        write_session(session)
        return session
