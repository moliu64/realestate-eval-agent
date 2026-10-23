"""Knowledge-base administration endpoints (admin role required)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app.api.deps import require_admin
from app.config import STATIC_DIR, load_config
from app.logging_config import get_logger
from app.services import auth_store, knowledge_service
from app.services.errors import InvalidInputError, NotFoundError, PayloadTooLargeError

logger = get_logger(__name__)

router = APIRouter(tags=["admin"])
MAX_UPLOAD_SUFFIXES_TEXT = "md、txt、csv、pdf、docx、png、jpg、jpeg"


@router.get("/admin")
def admin_page(request: Request) -> Response:
    """Serve the admin shell for admins and send everyone else back to the app."""

    principal = auth_store.get_principal(request.cookies.get(auth_store.AUTH_COOKIE, ""))
    if not principal or principal.get("role") != "admin":
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(STATIC_DIR / "admin.html")


@router.get("/admin/access")
def admin_access(principal: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return {"authorized": True, "username": principal["username"], "role": principal["role"]}


@router.post("/admin/preview")
async def admin_preview(
    file: UploadFile = File(...),
    _: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    content, suffix = await _read_upload(file)
    return knowledge_service.preview_content(content, suffix, Path(file.filename or "document").name)


@router.post("/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    category: str = Form(default="用户资料"),
    title: str = Form(default=""),
    _: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    content, suffix = await _read_upload(file)
    if category not in knowledge_service.DOCUMENT_CATEGORIES:
        raise InvalidInputError("无效的文档分类。")
    filename = knowledge_service.document_filename(
        category,
        title or Path(file.filename or "document").stem,
        suffix,
    )
    docs_dir = Path(load_config().docs_dir).resolve()
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = (docs_dir / filename).resolve()
    if target.parent != docs_dir:
        raise InvalidInputError("非法文件名。")
    previous = target.read_bytes() if target.exists() else None
    target.write_bytes(content)
    try:
        count = knowledge_service.rebuild_index()
    except Exception as exc:
        logger.exception("upload failed, rolling back %s", filename)
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(previous)
        try:
            knowledge_service.rebuild_index()
        except Exception:  # noqa: BLE001 - best effort rollback
            logger.exception("rollback rebuild failed")
        raise InvalidInputError(f"文件解析或入库失败：{exc}") from exc
    return {
        "source": filename,
        "file_type": suffix[1:],
        "vector_count": count,
        "replaced": previous is not None,
    }


@router.get("/admin/documents")
def admin_documents(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return knowledge_service.list_documents()


@router.get("/admin/documents/{source}")
def admin_document_preview(
    source: str,
    _: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    return knowledge_service.preview_stored_document(source)


@router.delete("/admin/documents/{source}")
def admin_delete(
    source: str,
    _: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    target = knowledge_service.document_target(source)
    if not target.exists():
        raise NotFoundError("文档不存在。")
    previous = target.read_bytes()
    target.unlink()
    try:
        count = knowledge_service.rebuild_index()
    except Exception as exc:
        logger.exception("delete failed, restoring %s", target.name)
        target.write_bytes(previous)
        try:
            knowledge_service.rebuild_index()
        except Exception:  # noqa: BLE001 - best effort rollback
            logger.exception("rollback rebuild failed")
        raise InvalidInputError(f"删除后重建失败，原文档已恢复：{exc}") from exc
    return {"source": target.name, "deleted": True, "vector_count": count}


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in knowledge_service.ALLOWED_UPLOAD_SUFFIXES:
        raise InvalidInputError(f"仅支持 {MAX_UPLOAD_SUFFIXES_TEXT} 文件。")
    limit = knowledge_service.max_upload_bytes()
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise PayloadTooLargeError(f"文件不能超过 {limit // (1024 * 1024)}MB。")
    return content, suffix
