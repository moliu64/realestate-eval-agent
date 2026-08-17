from __future__ import annotations

from typing import Any
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.llm import get_chat_model
from app.rag.retriever import retrieve
from app.tools.valuation import (
    calc_cost_approach,
    calc_income_approach,
    calc_market_comparison,
)
from app.workflow.schemas import ComputationItem, MethodPlanSchema, ReportSchema, RequirementSchema
from app.workflow.state import EvalState

METHOD_LABELS = {
    "market_comparison": "市场比较法",
    "income": "收益法",
    "cost": "成本法",
}

METHOD_QUERY = {
    "market_comparison": "市场比较法 定义 适用场景 计算公式 步骤",
    "income": "收益法 资本化率 净收益 直接资本化公式",
    "cost": "成本法 土地价值 重置成本 折旧 计算公式",
}

METHOD_SOURCES = {
    "market_comparison": "估价方法_市场比较法.md",
    "income": "估价方法_收益法.md",
    "cost": "估价方法_成本法.md",
}

REQUIRED_PARAMS = {
    "market_comparison": ["comparable_price", "area"],
    "income": ["net_income", "cap_rate"],
    "cost": ["land_value", "replacement_cost", "depreciation"],
}

METHOD_TO_TOOL = {
    "market_comparison": calc_market_comparison,
    "income": calc_income_approach,
    "cost": calc_cost_approach,
}

MAX_METHOD_LOOPS = 4


def _model_dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump()


def _parse_json_from_text(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("No JSON object found in LLM output.")
    return json.loads(match.group(0))


def _structured_invoke(schema: type[BaseModel], system_prompt: str, user_prompt: str) -> BaseModel:
    llm = get_chat_model()
    try:
        return llm.with_structured_output(schema).invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
    except Exception:
        fallback_prompt = (
            f"{system_prompt}\n\n只输出 JSON，不要输出 markdown。JSON 字段必须符合："
            f"{schema.model_json_schema()}\n\n用户输入：{user_prompt}"
        )
        response = llm.invoke([HumanMessage(content=fallback_prompt)])
        return schema.model_validate(_parse_json_from_text(str(response.content)))


def understand_node(state: EvalState) -> dict:
    requirement = state.get("requirement") or {}
    if requirement.get("property_usage") or requirement.get("area") is not None or requirement.get("layout"):
        return {}
    prompt = (
        "你负责把房地产估价需求结构化。金额单位统一换算为元，百分比统一换算为小数。"
        "提取户型、面积、房龄、朝向、楼层和装修状况；无法确定的信息放入 missing_data。"
    )
    requirement = _structured_invoke(RequirementSchema, prompt, state["question"])
    return {"requirement": _model_dump(requirement)}


def plan_node(state: EvalState) -> dict:
    prompt = (
        "你负责规划估价方法。规则：有可比成交数据选 market_comparison；"
        "有净收益和资本化率选 income；有土地价值、重置成本、折旧选 cost；"
        "可多选。params 只填工具所需字段，金额单位为元，比例为小数。"
    )
    user_prompt = json.dumps(
        {"question": state["question"], "requirement": state["requirement"]},
        ensure_ascii=False,
    )
    plan = _structured_invoke(MethodPlanSchema, prompt, user_prompt)
    methods = _dedupe_methods(plan.methods)
    params = _normalize_params(plan.params)
    if not methods:
        methods, params = _heuristic_plan(state["question"], state["requirement"])
    params = _supplement_params_from_question(state["question"], state["requirement"], methods, params)
    return {"methods": methods, "params": params, "loop_count": 0}


def next_method_node(state: EvalState) -> dict:
    methods = list(state.get("methods") or [])
    loop_count = int(state.get("loop_count") or 0)
    if not methods or loop_count >= MAX_METHOD_LOOPS:
        return {"current_method": "", "methods": [], "loop_count": loop_count}
    current = methods.pop(0)
    return {"current_method": current, "methods": methods, "loop_count": loop_count + 1}


def route_next_method(state: EvalState) -> str:
    return "verify" if not state.get("current_method") else "retrieve"


def retrieve_node(state: EvalState) -> dict:
    method = state["current_method"]
    query = f"{METHOD_QUERY.get(method, method)}\n用户需求：{state['question']}"
    results = retrieve(query, k=4)
    context = _format_context(results)

    trend_sources = _retrieve_trend_sources(state["question"])
    return {"context": context, "trend_sources": trend_sources}


def compute_node(state: EvalState) -> dict:
    method = state["current_method"]
    params = dict((state.get("params") or {}).get(method) or {})
    missing = [name for name in REQUIRED_PARAMS.get(method, []) if params.get(name) in (None, "")]
    source = _source_from_context(state.get("context", "")) or METHOD_SOURCES.get(method, "")

    if missing:
        return {
            "computations": [
                {
                    "method": method,
                    "tool": "",
                    "result": f"{METHOD_LABELS.get(method, method)}因缺少参数未计算：{', '.join(missing)}。",
                    "source": source,
                    "value": None,
                    "missing": missing,
                }
            ]
        }

    tool = METHOD_TO_TOOL[method]
    result = tool.invoke(params)
    return {
        "computations": [
            {
                "method": method,
                "tool": tool.name,
                "result": result,
                "source": source,
                "value": _extract_last_number(result),
                "missing": [],
            }
        ]
    }


def verify_node(state: EvalState) -> dict:
    computations = state.get("computations") or []
    if not computations:
        return {"verification": "未形成可计算的方法结果，需补充关键市场、收益或成本资料后再估价。"}

    summary = json.dumps(computations, ensure_ascii=False)
    prompt = (
        "你是一名房地产估价复核人。请基于各方法计算结果做交叉校核："
        "说明结果是否互相印证、差异可能原因，并给出最终结论或合理区间。"
    )
    response = get_chat_model().invoke(
        [SystemMessage(content=prompt), HumanMessage(content=summary)]
    )
    return {"verification": str(response.content).strip()}


def report_node(state: EvalState) -> dict:
    computations = state.get("computations") or []
    sources = _collect_sources(computations)
    requirement = state.get("requirement", {}) or {}
    known_data = requirement.get("known_data") or {}
    for source in known_data.get("preset_sources") or []:
        if source not in sources:
            sources.append(source)
    trend_sources = state.get("trend_sources") or []
    if not trend_sources:
        trend_sources = _retrieve_trend_sources(state["question"])
    methods_text = ", ".join(METHOD_LABELS.get(item["method"], item["method"]) for item in computations) or "未采用"
    calc_text = "\n\n".join(
        f"### {METHOD_LABELS.get(item['method'], item['method'])}\n{item['result']}\n[来源: {item.get('source') or '未匹配'}]"
        for item in computations
    ) or "暂无计算结果。"
    missing = requirement.get("missing_data") or []
    preset_basis = known_data.get("preset_basis") or "未使用区域年份预设"

    draft = (
        "# 房地产估价报告\n\n"
        "## 1. 估价对象\n"
        f"- 原始需求：{state['question']}\n"
        f"- 用途：{state.get('requirement', {}).get('property_usage') or '未明确'}\n"
        f"- 建筑面积：{state.get('requirement', {}).get('area') or '未明确'}\n\n"
        "## 1.1 参考因素说明\n"
        f"- 户型：{state.get('requirement', {}).get('layout') or '未明确'}\n"
        f"- 房龄：{state.get('requirement', {}).get('building_age') or '未明确'} 年\n"
        f"- 朝向：{state.get('requirement', {}).get('orientation') or '未明确'}\n"
        f"- 楼层：{state.get('requirement', {}).get('floor') or '未明确'}\n"
        f"- 装修：{state.get('requirement', {}).get('decoration') or '未明确'}\n"
        f"- 市场趋势依据：{'; '.join(f'[来源: {source}]' for source in trend_sources) or '未检索到趋势资料'}\n\n"
        f"- 参数预设口径：{preset_basis}\n\n"
        "## 2. 估价目的与时点\n"
        f"- 估价目的：{state.get('requirement', {}).get('valuation_purpose') or '未明确'}\n"
        f"- 估价时点：{state.get('requirement', {}).get('valuation_date') or '未明确'}\n\n"
        "## 3. 采用方法\n"
        f"{methods_text}\n\n"
        "## 4. 各方法计算过程\n"
        f"{calc_text}\n\n"
        "## 5. 交叉校核结论\n"
        f"{state.get('verification') or '未形成校核结论。'}\n\n"
        "## 6. 缺失资料与限制条件\n"
        f"{'; '.join(missing) if missing else '未识别到影响当前演示测算的关键缺失资料。'}\n\n"
        "## 7. 来源引用\n"
        f"{'; '.join(f'[来源: {source}]' for source in sources) if sources else '暂无来源引用。'}\n"
    )
    report_json = _build_report_json(state, computations, sources, draft)
    return {"report": draft, "report_json": report_json}


def _build_report_json(
    state: EvalState,
    computations: list[dict],
    sources: list[str],
    report_markdown: str,
) -> str:
    requirement = state.get("requirement", {}) or {}
    report = ReportSchema(
        question=state["question"],
        property_info={
            "property_usage": requirement.get("property_usage") or "",
            "area": requirement.get("area"),
            "location": requirement.get("location") or "",
            "rights_type": requirement.get("rights_type") or "",
            "known_data": requirement.get("known_data") or {},
            "layout": requirement.get("layout") or "",
            "building_age": requirement.get("building_age"),
            "orientation": requirement.get("orientation") or "",
            "floor": requirement.get("floor") or "",
            "decoration": requirement.get("decoration") or "",
        },
        valuation_purpose=requirement.get("valuation_purpose") or "",
        valuation_date=requirement.get("valuation_date") or "",
        methods=[item.get("method", "") for item in computations],
        computations=[ComputationItem.model_validate(item) for item in computations],
        verification=state.get("verification") or "",
        missing_data=requirement.get("missing_data") or [],
        sources=sources,
        report_markdown=report_markdown,
    )
    return report.model_dump_json(indent=2, ensure_ascii=False)


def _dedupe_methods(methods: list[str]) -> list[str]:
    allowed = {"market_comparison", "income", "cost"}
    result: list[str] = []
    for method in methods:
        if method in allowed and method not in result:
            result.append(method)
    return result


def _normalize_params(params: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for method, values in params.items():
        if isinstance(values, dict):
            normalized[method] = values
    return normalized


def _heuristic_plan(question: str, requirement: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    text = question
    methods: list[str] = []
    params: dict[str, dict[str, Any]] = {}
    known = requirement.get("known_data") or {}

    if "净收益" in text or "资本化率" in text or "收益" in text:
        methods.append("income")
        params["income"] = {
            "net_income": known.get("net_income"),
            "cap_rate": known.get("cap_rate"),
        }
    if "可比" in text or "成交单价" in text or "市场比较" in text:
        methods.append("market_comparison")
        params["market_comparison"] = {
            "comparable_price": known.get("comparable_price"),
            "area": requirement.get("area") or known.get("area"),
        }
    if "重置成本" in text or "折旧" in text or "成本法" in text:
        methods.append("cost")
        params["cost"] = {
            "land_value": known.get("land_value"),
            "replacement_cost": known.get("replacement_cost"),
            "depreciation": known.get("depreciation"),
        }
    return _dedupe_methods(methods), params


def _supplement_params_from_question(
    question: str,
    requirement: dict[str, Any],
    methods: list[str],
    params: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    supplemented = {method: dict(params.get(method) or {}) for method in methods}
    area = requirement.get("area") or _extract_area(question)
    if requirement.get("building_age") is None:
        age_match = re.search(r"(?:房龄|楼龄|建成于)\D{0,8}(\d+(?:\.\d+)?)\s*年?", question)
        if age_match:
            requirement["building_age"] = float(age_match.group(1))

    if "income" in methods:
        income_params = supplemented.setdefault("income", {})
        _set_if_blank(income_params, "net_income", _extract_net_income(question))
        _set_if_blank(income_params, "cap_rate", _extract_percent_after_keywords(question, ["资本化率", "报酬率"]))

    if "market_comparison" in methods:
        market_params = supplemented.setdefault("market_comparison", {})
        _set_if_blank(market_params, "comparable_price", _extract_unit_price(question))
        _set_if_blank(market_params, "area", area)

    if "cost" in methods:
        cost_params = supplemented.setdefault("cost", {})
        _set_if_blank(cost_params, "land_value", _extract_money_after_keywords(question, ["土地价值"]))
        _set_if_blank(cost_params, "replacement_cost", _extract_money_after_keywords(question, ["重置成本"]))
        _set_if_blank(cost_params, "depreciation", _extract_money_after_keywords(question, ["折旧"]))

    return supplemented


def _set_if_blank(params: dict[str, Any], key: str, value: Any) -> None:
    if params.get(key) in (None, "") and value is not None:
        params[key] = value


def _extract_area(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:平方米|平米|㎡)", text)
    return float(match.group(1)) if match else None


def _extract_unit_price(text: str) -> float | None:
    patterns = [
        r"(?:成交单价|可比.*?单价|单价)\s*(\d+(?:\.\d+)?)\s*元",
        r"(\d+(?:\.\d+)?)\s*元\s*/?\s*(?:平方米|平米|㎡)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def _extract_net_income(text: str) -> float | None:
    return _extract_money_after_keywords(text, ["年度稳定净收益", "年净收益", "净收益", "年租金净收益"])


def _extract_percent_after_keywords(text: str, keywords: list[str]) -> float | None:
    for keyword in keywords:
        match = re.search(rf"{keyword}\D{{0,8}}(\d+(?:\.\d+)?)\s*%", text)
        if match:
            return float(match.group(1)) / 100
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(match.group(1)) / 100 if match else None


def _extract_money_after_keywords(text: str, keywords: list[str]) -> float | None:
    for keyword in keywords:
        match = re.search(rf"{keyword}\D{{0,8}}(\d+(?:\.\d+)?)\s*(万元|万|元)?", text)
        if match:
            return _to_yuan(float(match.group(1)), match.group(2) or "元")
    return None


def _to_yuan(value: float, unit: str) -> float:
    return value * 10000 if unit in {"万元", "万"} else value


def _format_context(results: list, max_chars_per_doc: int = 300) -> str:
    parts: list[str] = []
    for doc, score in results[:4]:
        source = doc.metadata.get("source", "unknown")
        text = doc.page_content.strip().replace("\n\n", "\n")
        if len(text) > max_chars_per_doc:
            text = f"{text[:max_chars_per_doc]}..."
        parts.append(f"[来源: {source}; 相似度: {score:.3f}]\n{text}")
    return "\n\n---\n\n".join(parts)


def _retrieve_trend_sources(question: str) -> list[str]:
    if not any(keyword in question for keyword in ("趋势", "走势", "房龄", "户型", "房价")):
        return []
    sources: list[str] = []
    for doc, _ in retrieve("武汉房地产市场趋势 户型 房龄 价格走势", k=4):
        source = doc.metadata.get("source", "")
        if source.startswith("市场数据_武汉") and source not in sources:
            sources.append(source)
    return sources


def _source_from_context(context: str) -> str:
    match = re.search(r"\[来源:\s*([^;\]]+)", context)
    return match.group(1).strip() if match else ""


def _collect_sources(computations: list[dict]) -> list[str]:
    sources: list[str] = []
    for item in computations:
        source = item.get("source")
        if source and source not in sources:
            sources.append(source)
    return sources


def _extract_last_number(text: str) -> float | None:
    numbers = re.findall(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?", text)
    if not numbers:
        return None
    return float(numbers[-1].replace(",", ""))
