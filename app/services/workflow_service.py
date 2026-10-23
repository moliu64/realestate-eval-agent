"""Valuation workflow orchestration shared by the API and CLI entry points."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Any

from app.api.models import EvaluateRequest
from app.logging_config import get_logger
from app.workflow.graph import workflow_app

logger = get_logger(__name__)

METHOD_LABELS = {
    "market_comparison": "市场比较法",
    "income": "收益法",
    "cost": "成本法",
}

INITIAL_STATE: dict[str, Any] = {
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


@dataclass
class WorkflowResult:
    answer: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    report_json: str = ""


def initial_state(question: str = "", requirement: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a fresh graph state so callers never mutate the shared template."""

    state = dict(INITIAL_STATE)
    state["question"] = question
    if requirement is not None:
        state["requirement"] = requirement
    return state


def collect_known_data(request: EvaluateRequest) -> dict[str, Any]:
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


def build_requirement(request: EvaluateRequest) -> dict[str, Any]:
    return {
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
        "known_data": collect_known_data(request),
        "missing_data": [],
    }


def build_question(request: EvaluateRequest) -> str:
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


def run_workflow(init: dict[str, Any]) -> WorkflowResult:
    """Execute the LangGraph workflow and collect the chat-friendly result."""

    started = time.perf_counter()
    result = WorkflowResult()
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
                result.steps.append(step)
            if "report" in update:
                result.answer = str(update["report"]).replace("−", "-")
            if "report_json" in update:
                result.report_json = str(update["report_json"])
    logger.info("workflow finished in %.2fs (%d steps)", time.perf_counter() - started, len(result.steps))
    return result


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
            "detail": {"methods": [method_label(method) for method in methods]},
        }
    if node == "retrieve":
        return {
            "type": "retrieve",
            "label": "检索知识",
            "detail": {
                "method": method_label(current_method),
                "sources": extract_sources(update.get("context") or ""),
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
                "method": method_label(method),
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
            "detail": {"verification": truncate(update.get("verification") or "", 220)},
        }
    return None


def method_label(method: str) -> str:
    return METHOD_LABELS.get(method, method or "未明确")


def extract_sources(context: str) -> list[str]:
    matches = re.findall(r"\[来源:\s*([^;\]]+)", context)
    sources: list[str] = []
    for source in matches:
        source = source.strip()
        if source and source not in sources:
            sources.append(source)
    return sources


def truncate(text: str, max_chars: int) -> str:
    text = str(text).strip()
    return text if len(text) <= max_chars else f"{text[:max_chars]}..."
