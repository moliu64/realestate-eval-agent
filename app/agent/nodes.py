from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.llm import get_chat_model
from app.rag.retriever import retrieve
from app.tools import TOOLS

MAX_TOOL_CALLS = 5

SYSTEM_PROMPT = """你是一名资深房地产估价师。
你会先依据检索上下文判断估价方法和参数口径，再决定是否调用估价工具。
凡是问题包含明确数值并要求估值、计算、测算、多少钱或价值时，必须调用合适的工具。
金额单位统一为元；遇到“万”要换算为元，例如 60 万元 = 600000 元；百分比要换算为小数，例如 5% = 0.05。
最终回答必须包含工具返回的计算过程，并标注知识依据来源，格式为 [来源: 文件名]。
如果检索上下文不足以支持方法口径，请说明缺少依据，不要编造。
"""


def _format_context(results: list, max_chars_per_doc: int = 300) -> str:
    if not results:
        return "没有检索到相关上下文。"
    parts: list[str] = []
    for doc, score in results[:4]:
        source = doc.metadata.get("source", "unknown")
        text = doc.page_content.strip().replace("\n\n", "\n")
        if len(text) > max_chars_per_doc:
            text = f"{text[:max_chars_per_doc]}..."
        parts.append(f"[来源: {source}; 相似度: {score:.3f}]\n{text}")
    return "\n\n---\n\n".join(parts)


def retrieve_node(state: AgentState) -> dict:
    question = state["question"]
    results = retrieve(question, k=4)
    return {
        "context": _format_context(results),
        "messages": [HumanMessage(content=question)],
    }


def agent_node(state: AgentState) -> dict:
    chat_model = get_chat_model().bind_tools(TOOLS)
    messages = [
        SystemMessage(content=f"{SYSTEM_PROMPT}\n\n检索上下文：\n{state['context']}"),
        *state["messages"],
    ]
    response = chat_model.invoke(messages)
    return {"messages": [response]}


def finalize_node(state: AgentState) -> dict:
    last = state["messages"][-1]
    content = getattr(last, "content", "")
    if not content:
        content = "工具调用次数达到上限，未能生成最终回答。"
    return {"answer": str(content).strip()}


def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    tool_call_count = sum(len(getattr(message, "tool_calls", []) or []) for message in messages)
    if tool_call_count >= MAX_TOOL_CALLS:
        return "finalize"

    last = messages[-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "finalize"
