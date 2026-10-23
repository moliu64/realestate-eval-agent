"""One-shot valuation, RAG, preset and layout-analysis endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import require_user
from app.api.models import AskRequest, AskResponse, EvaluateRequest, RagRequest
from app.logging_config import get_logger
from app.presets import build_wuhan_preset, preset_options
from app.rag.chain import answer as rag_answer
from app.services.errors import InvalidInputError, PayloadTooLargeError, UnavailableError
from app.services.workflow_service import build_question, build_requirement, initial_state, run_workflow
from app.vision import describe_image

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["valuation"])

_LAYOUT_SUFFIXES = {".png", ".jpg", ".jpeg"}
_LAYOUT_PROMPT = "这是房屋户型/房间布局图。请提取并描述：几室几厅、朝向、面积标注、各房间分布；无法确认的内容请标注不确定。"


@router.post("/evaluate", response_model=AskResponse)
def evaluate(payload: EvaluateRequest) -> AskResponse:
    init = initial_state(
        question=build_question(payload),
        requirement=build_requirement(payload),
    )
    result = run_workflow(init)
    return AskResponse(answer=result.answer, steps=result.steps, report_json=result.report_json)


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    try:
        init = initial_state(question=payload.question.strip())
        result = run_workflow(init)
    except Exception as exc:  # noqa: BLE001 - model providers raise many exception types
        logger.exception("one-shot valuation failed")
        raise UnavailableError("问答服务暂时不可用，请稍后重试。") from exc
    return AskResponse(answer=result.answer, steps=result.steps, report_json=result.report_json)


@router.post("/rag")
def rag(payload: RagRequest, _: dict[str, Any] = Depends(require_user)) -> dict[str, str]:
    try:
        answer = rag_answer(payload.question.strip())
    except (FileNotFoundError, RuntimeError) as exc:
        logger.warning("RAG failed: %s", exc)
        raise UnavailableError("知识库暂不可用，请先构建向量库后重试。") from exc
    return {"answer": answer}


@router.get("/presets/options")
def get_preset_options() -> dict[str, Any]:
    return preset_options()


@router.get("/presets/wuhan")
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
        raise InvalidInputError(str(exc)) from exc


@router.post("/analyze-layout")
async def analyze_layout(file: UploadFile = File(...)) -> dict[str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _LAYOUT_SUFFIXES:
        raise InvalidInputError("仅支持 png/jpg/jpeg 户型图。")
    from app.config import load_config

    limit = load_config().max_upload_bytes
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise PayloadTooLargeError(f"图片不能超过 {limit // (1024 * 1024)}MB。")
    try:
        description = describe_image(content, _LAYOUT_PROMPT)
    except RuntimeError as exc:
        raise UnavailableError(str(exc)) from exc
    return {"layout": description}
