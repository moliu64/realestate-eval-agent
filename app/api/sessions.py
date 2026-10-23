"""Valuation session endpoints: CRUD, report generation and in-session RAG."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import current_owner
from app.api.models import SessionMessageRequest, SessionPatchRequest, SessionRagRequest
from app.logging_config import get_logger
from app.rag.chain import answer as rag_answer
from app.services import session_store
from app.services.errors import UnavailableError
from app.services.workflow_service import build_question, build_requirement, initial_state, run_workflow

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_DEFAULT_TITLES = {"新建估价会话", "未命名估价"}
_DEFAULT_MESSAGE = "请根据当前固定估价参数生成估值报告。"


@router.get("")
def list_sessions(owner_id: str = Depends(current_owner)) -> list[dict[str, Any]]:
    return session_store.list_sessions(owner_id)


@router.post("")
def create_session(owner_id: str = Depends(current_owner)) -> dict[str, Any]:
    return session_store.create_session(owner_id)


@router.get("/{session_id}")
def get_session(session_id: str, owner_id: str = Depends(current_owner)) -> dict[str, Any]:
    return session_store.read_session(session_id, owner_id)


@router.patch("/{session_id}")
def patch_session(
    session_id: str,
    payload: SessionPatchRequest,
    owner_id: str = Depends(current_owner),
) -> dict[str, Any]:
    def mutate(session: dict[str, Any]) -> None:
        if payload.title is not None:
            session["title"] = payload.title.strip() or "未命名估价"
        if payload.fixed_fields is not None:
            session["fixed_fields"] = payload.fixed_fields
        if payload.layout_description is not None:
            session["layout_description"] = payload.layout_description
        if payload.layout_filename is not None:
            session["layout_filename"] = payload.layout_filename

    return session_store.mutate_session(session_id, owner_id, mutate)


@router.delete("/{session_id}")
def delete_session(session_id: str, owner_id: str = Depends(current_owner)) -> dict[str, bool]:
    session_store.delete_session(session_id, owner_id)
    return {"deleted": True}


@router.post("/{session_id}/messages")
def add_session_message(
    session_id: str,
    payload: SessionMessageRequest,
    owner_id: str = Depends(current_owner),
) -> dict[str, Any]:
    session_store.read_session(session_id, owner_id)
    message = payload.message.strip() or payload.note.strip() or _DEFAULT_MESSAGE
    fixed_fields = payload.model_dump(exclude={"message"}, exclude_none=True)
    workflow_request = payload.model_copy(update={"note": message})
    init = initial_state(
        question=build_question(workflow_request),
        requirement=build_requirement(workflow_request),
    )
    result = run_workflow(init)

    assistant = {
        "role": "assistant",
        "kind": "report",
        "content": result.answer,
        "steps": result.steps,
        "report_json": result.report_json,
        "created_at": session_store.now_iso(),
    }

    def mutate(session: dict[str, Any]) -> None:
        session["fixed_fields"] = fixed_fields
        if session.get("title") in _DEFAULT_TITLES:
            session["title"] = message[:36]
        session["messages"].append(
            {
                "role": "user",
                "kind": "message",
                "content": message,
                "created_at": session_store.now_iso(),
            }
        )
        session["messages"].append(assistant)

    updated = session_store.mutate_session(session_id, owner_id, mutate)
    return {"session": updated, "message": assistant}


@router.post("/{session_id}/rag")
def add_session_rag(
    session_id: str,
    payload: SessionRagRequest,
    owner_id: str = Depends(current_owner),
) -> dict[str, Any]:
    session_store.read_session(session_id, owner_id)
    question = payload.question.strip()
    try:
        answer = rag_answer(question)
    except (FileNotFoundError, RuntimeError) as exc:
        logger.warning("RAG failed: %s", exc)
        raise UnavailableError("知识库暂不可用，请先构建向量库后重试。") from exc
    assistant = {
        "role": "assistant",
        "kind": "rag_answer",
        "content": answer,
        "created_at": session_store.now_iso(),
    }

    def mutate(session: dict[str, Any]) -> None:
        session["messages"].append(
            {
                "role": "user",
                "kind": "rag_question",
                "content": question,
                "created_at": session_store.now_iso(),
            }
        )
        session["messages"].append(assistant)

    updated = session_store.mutate_session(session_id, owner_id, mutate)
    return {"session": updated, "message": assistant}
