import hmac
import hashlib
import json
import secrets
import time
import re
import tempfile
import uuid
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT, load_config
from app.presets import build_wuhan_preset, preset_options
from app.rag.chain import answer as rag_answer
from app.rag.loader import load_docs, load_document
from app.rag.splitter import split_docs
from app.rag.vectorstore import build_vectorstore, load_vectorstore
from app.workflow.graph import workflow_app
from app.vision import describe_image

STATIC_DIR = PROJECT_ROOT / "app" / "web" / "static"
SESSIONS_DIR = PROJECT_ROOT / "data" / "sessions"
SESSION_OWNER_COOKIE = "realestate_session_owner"
AUTH_COOKIE = "realestate_auth"
AUTH_SESSIONS: dict[str, dict[str, Any]] = {}
AUTH_USERS_FILE = PROJECT_ROOT / "data" / "auth_users.json"
AUTH_USERS_LOCK = Lock()
METHOD_LABELS = {
    "market_comparison": "市场比较法",
    "income": "收益法",
    "cost": "成本法",
}
WORKFLOW_INIT = {
    "question": "",
    "requirement": {},
    "methods": [],
    "params": {},
    "current_method": "",
    "context": "",
    "trend_sources": [],
    "computations": [],
    "verification": "",
    "report": "",
    "report_json": "",
    "messages": [],
    "loop_count": 0,
}

app = FastAPI(title="RealEstate Eval Agent")
_cors_origins = list(load_config().cors_origins)
_public_host = load_config().public_host
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".md", ".txt", ".csv", ".pdf", ".docx", ".png", ".jpg", ".jpeg"}
DOCUMENT_CATEGORIES = {"估价方法", "市场数据", "政策法规", "估价规范", "业务知识", "用户资料"}


@app.middleware("http")
async def prevent_stale_frontend_assets(request: Request, call_next):
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme).lower()
    request_host = request.headers.get("host", "").split(":", 1)[0].lower()
    if _public_host and request_host == _public_host and forwarded_proto == "http":
        return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)

    response = await call_next(request)
    if request.url.path in {"/", "/admin"}:
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Pragma"] = "no-cache"
    elif request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
        "script-src 'self' https://static.cloudflareinsights.com; "
        "connect-src 'self' https://cloudflareinsights.com; font-src 'self'; object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_\u4e00-\u9fff-]+$")
    password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=1, max_length=200)


class EvaluateRequest(BaseModel):
    property_usage: str = ""
    area: float | None = None
    layout: str = ""
    building_age: float | None = None
    orientation: str = ""
    floor: str = ""
    decoration: str = ""
    location: str = ""
    valuation_purpose: str = ""
    valuation_date: str = ""
    comparable_price: float | None = None
    net_income: float | None = None
    cap_rate: float | None = None
    land_value: float | None = None
    replacement_cost: float | None = None
    depreciation: float | None = None
    preset_year: int | None = None
    preset_sources: list[str] = Field(default_factory=list)
    preset_basis: str = ""
    note: str = ""


class RagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class SessionMessageRequest(EvaluateRequest):
    message: str = Field(default="", max_length=5000)


class SessionPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    fixed_fields: dict[str, Any] | None = None
    layout_description: str | None = None
    layout_filename: str | None = None


class SessionRagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AskResponse(BaseModel):
    answer: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    report_json: str = ""


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
def admin_index(request: Request) -> FileResponse:
    _require_admin(request)
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/admin/access")
def admin_access(request: Request) -> dict[str, Any]:
    principal = _require_admin(request)
    return {"authorized": True, "username": principal["username"], "role": principal["role"]}


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    account = _find_auth_user(payload.username)
    if not account or not _verify_password(payload.password, account.get("password", "")):
        raise HTTPException(status_code=401, detail="用户名或密码错误。")
    token = secrets.token_urlsafe(32)
    AUTH_SESSIONS[token] = {
        "username": payload.username,
        "role": account.get("role", "user") if account.get("role") in {"admin", "user"} else "user",
        "expires_at": time.time() + 7 * 86400,
    }
    response.set_cookie(AUTH_COOKIE, token, httponly=True, samesite="lax", secure=request.url.scheme == "https", max_age=7 * 86400)
    return {"authenticated": True, **AUTH_SESSIONS[token]}


@app.post("/api/auth/register")
def register(payload: RegisterRequest) -> dict[str, Any]:
    username = payload.username.strip()
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致。")
    with AUTH_USERS_LOCK:
        if _find_auth_user(username):
            raise HTTPException(status_code=409, detail="用户名已存在，请更换用户名。")
        users = _load_registered_users()
        users[username] = {"password": _hash_password(payload.password), "role": "user"}
        _save_registered_users(users)
    return {"registered": True, "username": username, "role": "user"}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    AUTH_SESSIONS.pop(request.cookies.get(AUTH_COOKIE, ""), None)
    response.delete_cookie(AUTH_COOKIE)
    response.delete_cookie(SESSION_OWNER_COOKIE)
    return {"logged_out": True}


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    principal = _auth_principal(request, required=False)
    return {"authenticated": bool(principal), **(principal or {})}


@app.post("/admin/preview")
async def admin_preview(request: Request, file: UploadFile = File(...), x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(request)
    content, suffix = await _read_upload(file)
    return _preview_content(content, suffix, Path(file.filename or "document").name)


@app.post("/admin/upload")
async def admin_upload(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(default="用户资料"),
    title: str = Form(default=""),
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    content, suffix = await _read_upload(file)
    if category not in DOCUMENT_CATEGORIES:
        raise HTTPException(status_code=400, detail="无效的文档分类。")
    filename = _document_filename(category, title or Path(file.filename or "document").stem, suffix)
    docs_dir = Path(load_config().docs_dir).resolve()
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = (docs_dir / filename).resolve()
    if target.parent != docs_dir:
        raise HTTPException(status_code=400, detail="非法文件名。")
    previous = target.read_bytes() if target.exists() else None
    target.write_bytes(content)
    try:
        count = _rebuild_index()
    except Exception as exc:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(previous)
        _rebuild_index()
        raise HTTPException(status_code=400, detail=f"文件解析或入库失败：{exc}") from exc
    return {"source": filename, "file_type": suffix[1:], "vector_count": count, "replaced": previous is not None}


@app.get("/admin/documents")
def admin_documents(request: Request, x_admin_token: str | None = Header(default=None)) -> list[dict[str, Any]]:
    _require_admin(request)
    docs_dir = Path(load_config().docs_dir)
    documents = []
    for path in sorted(docs_dir.iterdir()) if docs_dir.exists() else []:
        if path.is_file() and path.suffix.lower() in ALLOWED_UPLOAD_SUFFIXES:
            stat = path.stat()
            documents.append({
                "source": path.name,
                "file_type": path.suffix.lower().lstrip("."),
                "category": path.stem.split("_", 1)[0] if "_" in path.stem else "未分类",
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "size": stat.st_size,
            })
    return documents


@app.get("/admin/documents/{source}")
def admin_document_preview(source: str, request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(request)
    target = _document_target(source)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文档不存在。")
    document = load_document(target)
    return _preview_document(document)


@app.delete("/admin/documents/{source}")
def admin_delete(source: str, request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(request)
    target = _document_target(source)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文档不存在。")
    previous = target.read_bytes()
    target.unlink()
    try:
        count = _rebuild_index()
    except Exception as exc:
        target.write_bytes(previous)
        _rebuild_index()
        raise HTTPException(status_code=400, detail=f"删除后重建失败，原文档已恢复：{exc}") from exc
    return {"source": target.name, "deleted": True, "vector_count": count}


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持 md、txt、csv、pdf、docx、png、jpg、jpeg 文件。")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 20MB。")
    return content, suffix


def _document_filename(category: str, title: str, suffix: str) -> str:
    clean_title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", title).strip(" ._")
    if not clean_title:
        raise HTTPException(status_code=400, detail="文档标题不能为空。")
    if len(clean_title) > 80:
        clean_title = clean_title[:80].rstrip()
    return f"{category}_{clean_title}{suffix}"


def _document_target(source: str) -> Path:
    filename = Path(source).name
    docs_dir = Path(load_config().docs_dir).resolve()
    target = (docs_dir / filename).resolve()
    if target.parent != docs_dir or target.name != source or target.suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail="非法文档来源。")
    return target


def _preview_content(content: bytes, suffix: str, source: str) -> dict[str, Any]:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        document = load_document(temporary_path)
        document.metadata["source"] = source
        return _preview_document(document)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def _preview_document(document) -> dict[str, Any]:
    chunks = split_docs([document])
    return {
        "source": document.metadata.get("source", ""),
        "file_type": document.metadata.get("file_type", ""),
        "characters": len(document.page_content),
        "chunk_count": len(chunks),
        "overlap_ratio": 0.10,
        "chunks": [
            {
                "index": chunk.metadata["chunk"],
                "characters": chunk.metadata["chunk_size"],
                "overlap_chars": chunk.metadata["overlap_chars"],
                "text": chunk.page_content[:600],
            }
            for chunk in chunks[:12]
        ],
    }


def _require_admin(request: Request) -> dict[str, Any]:
    principal = _auth_principal(request)
    if principal["role"] != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以管理知识库。")
    return principal


def _load_registered_users() -> dict[str, dict[str, str]]:
    if not AUTH_USERS_FILE.exists():
        return {}
    try:
        payload = json.loads(AUTH_USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="注册账号数据无法读取。") from exc
    return {
        str(username): {"password": str(details.get("password", "")), "role": "user"}
        for username, details in payload.items()
        if isinstance(details, dict) and details.get("password")
    } if isinstance(payload, dict) else {}


def _save_registered_users(users: dict[str, dict[str, str]]) -> None:
    AUTH_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = AUTH_USERS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(AUTH_USERS_FILE)


def _find_auth_user(username: str) -> dict[str, str] | None:
    target = username.strip().casefold()
    configured = load_config().auth_users
    for candidate, account in configured.items():
        if candidate.casefold() == target:
            return account
    for candidate, account in _load_registered_users().items():
        if candidate.casefold() == target:
            return account
    return None


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return f"pbkdf2_sha256$260000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds_text, salt_hex, digest_hex = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds_text))
            return hmac.compare_digest(digest.hex(), digest_hex)
        except (ValueError, TypeError):
            return False
    return bool(stored) and hmac.compare_digest(stored, password)


def _auth_principal(request: Request, required: bool = True) -> dict[str, Any] | None:
    token = request.cookies.get(AUTH_COOKIE, "")
    principal = AUTH_SESSIONS.get(token)
    if principal and principal["expires_at"] <= time.time():
        AUTH_SESSIONS.pop(token, None)
        principal = None
    if required and not principal:
        raise HTTPException(status_code=401, detail="请先登录。")
    return principal


'''legacy token check retained below only as dead documentation'''
def _legacy_require_admin(token: str | None) -> None:
    configured = load_config().admin_token
    if not configured or not token or not hmac.compare_digest(token, configured):
        raise HTTPException(status_code=401, detail="需要有效的 X-Admin-Token。")


def _rebuild_index() -> int:
    config = load_config()
    chunks = split_docs(load_docs(config.docs_dir))
    if not chunks:
        raise RuntimeError("知识库为空，无法重建索引。")
    try:
        store = load_vectorstore(config.vector_db_dir)
        existing = store.get(include=[])["ids"]
        if existing:
            store.delete(ids=existing)
        store.add_documents(chunks)
    except FileNotFoundError:
        store = build_vectorstore(chunks, config.vector_db_dir, rebuild=True)
        load_vectorstore.cache_clear()
    return len(store.get(include=[])['ids'])


def _run_workflow(init: dict[str, Any]) -> AskResponse:
    steps: list[dict[str, Any]] = []
    answer_text = ""
    report_json = ""
    current_method = ""
    for chunk in workflow_app.stream(init, stream_mode="updates"):
        for node, update in chunk.items():
            if not isinstance(update, dict):
                continue
            if node == "next_method":
                current_method = update.get("current_method", "")
                continue
            step = _build_step(node, update, current_method)
            if step:
                steps.append(step)
            if "report" in update:
                answer_text = str(update["report"]).replace("−", "-")
            if "report_json" in update:
                report_json = str(update["report_json"])
    return AskResponse(answer=answer_text, steps=steps, report_json=report_json)


def _session_path(session_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", session_id):
        raise HTTPException(status_code=400, detail="非法会话编号。")
    return SESSIONS_DIR / f"{session_id}.json"


def _session_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _owner_id(request: Request, response: Response) -> str:
    principal = _auth_principal(request)
    return f"user:{principal['username']}"


def _read_session(session_id: str, owner_id: str) -> dict[str, Any]:
    path = _session_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="会话不存在。")
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
        if session.get("owner_id") != owner_id:
            raise HTTPException(status_code=404, detail="会话不存在。")
        return session
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="会话数据无法读取。") from exc


def _write_session(session: dict[str, Any]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _session_path(session["id"])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    user_messages = [message.get("content", "") for message in session.get("messages", []) if message.get("role") == "user"]
    return {
        "id": session["id"],
        "title": session.get("title") or "未命名估价",
        "updated_at": session.get("updated_at", ""),
        "message_count": len(session.get("messages", [])),
        "last_user_message": user_messages[-1] if user_messages else "暂无用户输入",
    }


def _new_session(owner_id: str) -> dict[str, Any]:
    now = _session_now()
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


@app.get("/api/sessions")
def list_sessions(request: Request, response: Response) -> list[dict[str, Any]]:
    owner_id = _owner_id(request, response)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
            if session.get("owner_id") == owner_id:
                sessions.append(_session_summary(session))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)


@app.post("/api/sessions")
def create_session(request: Request, response: Response) -> dict[str, Any]:
    session = _new_session(_owner_id(request, response))
    _write_session(session)
    return session


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, request: Request, response: Response) -> dict[str, Any]:
    return _read_session(session_id, _owner_id(request, response))


@app.patch("/api/sessions/{session_id}")
def patch_session(session_id: str, request: SessionPatchRequest, http_request: Request, response: Response) -> dict[str, Any]:
    session = _read_session(session_id, _owner_id(http_request, response))
    if request.title is not None:
        session["title"] = request.title.strip() or "未命名估价"
    if request.fixed_fields is not None:
        session["fixed_fields"] = request.fixed_fields
    if request.layout_description is not None:
        session["layout_description"] = request.layout_description
    if request.layout_filename is not None:
        session["layout_filename"] = request.layout_filename
    session["updated_at"] = _session_now()
    _write_session(session)
    return session


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, request: Request, response: Response) -> dict[str, bool]:
    session = _read_session(session_id, _owner_id(request, response))
    path = _session_path(session["id"])
    path.unlink()
    return {"deleted": True}


@app.post("/api/sessions/{session_id}/messages")
def add_session_message(session_id: str, request: SessionMessageRequest, http_request: Request, response: Response) -> dict[str, Any]:
    session = _read_session(session_id, _owner_id(http_request, response))
    fixed_fields = request.model_dump(exclude={"message"}, exclude_none=True)
    message = request.message.strip() or request.note.strip()
    if not message:
        message = "请根据当前固定估价参数生成估值报告。"
    session["fixed_fields"] = fixed_fields
    if session.get("title") in {"新建估价会话", "未命名估价"}:
        session["title"] = message[:36]
    session["messages"].append({"role": "user", "kind": "message", "content": message, "created_at": _session_now()})
    requirement = {
        "property_usage": request.property_usage,
        "area": request.area,
        "layout": request.layout,
        "building_age": request.building_age,
        "orientation": request.orientation,
        "floor": request.floor,
        "decoration": request.decoration,
        "location": request.location,
        "valuation_purpose": request.valuation_purpose,
        "valuation_date": request.valuation_date,
        "known_data": _collect_known_data(request),
        "missing_data": [],
    }
    workflow_request = request.model_copy(update={"note": message})
    init = dict(WORKFLOW_INIT, question=_build_question(workflow_request), requirement=requirement)
    result = _run_workflow(init)
    assistant = {
        "role": "assistant", "kind": "report", "content": result.answer,
        "steps": result.steps, "report_json": result.report_json, "created_at": _session_now(),
    }
    session["messages"].append(assistant)
    session["updated_at"] = _session_now()
    _write_session(session)
    return {"session": session, "message": assistant}


@app.post("/api/sessions/{session_id}/rag")
def add_session_rag(session_id: str, request: SessionRagRequest, http_request: Request, response: Response) -> dict[str, Any]:
    session = _read_session(session_id, _owner_id(http_request, response))
    now = _session_now()
    session["messages"].append({
        "role": "user", "kind": "rag_question", "content": request.question.strip(), "created_at": now,
    })
    answer = rag_answer(request.question.strip())
    assistant = {
        "role": "assistant", "kind": "rag_answer", "content": answer, "created_at": _session_now(),
    }
    session["messages"].append(assistant)
    session["updated_at"] = _session_now()
    _write_session(session)
    return {"session": session, "message": assistant}


def _collect_known_data(request: EvaluateRequest) -> dict[str, Any]:
    values = {
        "comparable_price": request.comparable_price,
        "net_income": request.net_income,
        "cap_rate": request.cap_rate,
        "land_value": request.land_value,
        "replacement_cost": request.replacement_cost,
        "depreciation": request.depreciation,
    }
    known_data: dict[str, Any] = {key: value for key, value in values.items() if value is not None}
    if request.preset_sources:
        known_data["preset_sources"] = request.preset_sources
    if request.preset_basis:
        known_data["preset_basis"] = request.preset_basis
    if request.preset_year:
        known_data["preset_year"] = request.preset_year
    return known_data


def _build_question(request: EvaluateRequest) -> str:
    parts = [
        f"用途：{request.property_usage}",
        f"面积：{request.area}平方米",
        f"户型：{request.layout}",
        f"房龄：{request.building_age}年",
        f"朝向：{request.orientation}",
        f"楼层：{request.floor}",
        f"装修：{request.decoration}",
        f"区位：{request.location}",
        f"估价目的：{request.valuation_purpose}",
    ]
    data = []
    if request.comparable_price is not None:
        data.append(f"可比成交单价{request.comparable_price}元/平方米")
    if request.net_income is not None:
        data.append(f"年度稳定净收益{request.net_income}元")
    if request.cap_rate is not None:
        data.append(f"资本化率{request.cap_rate}")
    if request.land_value is not None:
        data.append(f"土地价值{request.land_value}元")
    if request.replacement_cost is not None:
        data.append(f"重置成本{request.replacement_cost}元")
    if request.depreciation is not None:
        data.append(f"折旧{request.depreciation}元")
    if data:
        parts.append("已知数据：" + "；".join(data))
    if request.preset_basis:
        parts.append(f"武汉区域年份预设：{request.preset_basis}")
    if request.note:
        parts.append(f"补充说明：{request.note}")
    return "，".join(parts) + "。请给出参考估值。"


@app.post("/api/evaluate")
def evaluate(request: EvaluateRequest) -> AskResponse:
    requirement = {
        "property_usage": request.property_usage,
        "area": request.area,
        "layout": request.layout,
        "building_age": request.building_age,
        "orientation": request.orientation,
        "floor": request.floor,
        "decoration": request.decoration,
        "location": request.location,
        "valuation_purpose": request.valuation_purpose,
        "valuation_date": request.valuation_date,
        "known_data": _collect_known_data(request),
        "missing_data": [],
    }
    init = dict(WORKFLOW_INIT, question=_build_question(request), requirement=requirement)
    return _run_workflow(init)


@app.get("/api/presets/options")
def get_preset_options() -> dict[str, Any]:
    return preset_options()


@app.get("/api/presets/wuhan")
def get_wuhan_preset(
    district: str,
    year: int,
    property_usage: str = "住宅",
    area: float | None = None,
    building_age: float | None = None,
) -> dict[str, Any]:
    try:
        return build_wuhan_preset(district, year, property_usage, area, building_age)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/analyze-layout")
async def analyze_layout(file: UploadFile = File(...)) -> dict[str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=400, detail="仅支持 png/jpg/jpeg 户型图。")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 20MB。")
    prompt = "这是房屋户型/房间布局图。请提取并描述：几室几厅、朝向、面积标注、各房间分布；无法确认的内容请标注不确定。"
    try:
        description = describe_image(content, prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"layout": description}


@app.post("/api/rag")
def rag(request: RagRequest, http_request: Request) -> dict[str, str]:
    _auth_principal(http_request)
    return {"answer": rag_answer(request.question.strip())}


@app.post("/api/ask")
def ask(request: AskRequest) -> AskResponse:
    started = time.perf_counter()
    print(f"[api] ask started: {request.question[:40]}", flush=True)
    try:
        init = dict(WORKFLOW_INIT, question=request.question.strip())
        result = _run_workflow(init)

        print(f"[api] ask finished in {time.perf_counter() - started:.2f}s", flush=True)
        return result
    except Exception as exc:
        print(f"[api] ask failed in {time.perf_counter() - started:.2f}s: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="问答服务暂时不可用，请稍后重试。") from exc


def _build_step(node: str, update: dict[str, Any], current_method: str) -> dict[str, Any] | None:
    if node == "understand":
        requirement = update.get("requirement") or {}
        return {
            "type": "understand",
            "label": "需求理解",
            "detail": {
                "usage": requirement.get("property_usage") or "未明确",
                "area": requirement.get("area"),
                "purpose": requirement.get("valuation_purpose") or "未明确",
                "missing": requirement.get("missing_data") or [],
            },
        }
    if node == "plan":
        methods = update.get("methods") or []
        return {
            "type": "plan",
            "label": "方法规划",
            "detail": {"methods": [_method_label(method) for method in methods]},
        }
    if node == "retrieve":
        return {
            "type": "retrieve",
            "label": "检索知识",
            "detail": {
                "method": _method_label(current_method),
                "sources": _extract_sources(update.get("context") or ""),
            },
        }
    if node == "compute":
        computations = update.get("computations") or []
        item = computations[-1] if computations else {}
        method = item.get("method") or current_method
        return {
            "type": "compute",
            "label": "工具计算",
            "detail": {
                "method": _method_label(method),
                "tool": item.get("tool") or "",
                "result": item.get("result") or "",
                "value": item.get("value"),
                "missing": item.get("missing") or [],
                "source": item.get("source") or "",
            },
        }
    if node == "verify":
        return {
            "type": "verify",
            "label": "交叉校核",
            "detail": {"verification": _truncate(update.get("verification") or "", 220)},
        }
    return None


def _method_label(method: str) -> str:
    return METHOD_LABELS.get(method, method or "未明确")


def _extract_sources(context: str) -> list[str]:
    matches = re.findall(r"\[来源:\s*([^;\]]+)", context)
    sources: list[str] = []
    for source in matches:
        source = source.strip()
        if source and source not in sources:
            sources.append(source)
    return sources


def _truncate(text: str, max_chars: int) -> str:
    text = str(text).strip()
    return text if len(text) <= max_chars else f"{text[:max_chars]}..."
