from langchain_core.messages import HumanMessage, SystemMessage
import time

from app.config import load_config
from app.llm import get_chat_model
from app.logging_config import get_logger
from app.rag.retriever import retrieve

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "你是一名资深房地产估价师。只能依据给定上下文回答问题；"
    "必须标注来源，格式为 [来源: 文件名]；如果上下文没有相关依据，"
    "请明确回答“没有找到相关依据”，不要编造。"
)


def _format_context(results: list) -> str:
    parts: list[str] = []
    for doc, score in results:
        source = doc.metadata.get("source", "unknown")
        parts.append(f"[来源: {source}; 相似度: {score:.3f}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def _fallback_answer(question: str, results: list) -> str:
    lines = [
        "LLM 未配置，以下为基于检索结果的依据摘要：",
        f"问题：{question}",
    ]
    for doc, score in results[:2]:
        source = doc.metadata.get("source", "unknown")
        snippet = doc.page_content.strip().replace("\n", " ")
        lines.append(f"- {snippet[:220]}... [来源: {source}; 相似度: {score:.3f}]")
    return "\n".join(lines)


def answer(question: str) -> str:
    started = time.perf_counter()
    config = load_config()
    results = retrieve(question, k=config.retrieval_top_k)
    logger.info("retrieved %d chunks in %.2fs", len(results), time.perf_counter() - started)
    relevant_results = [
        (doc, score) for doc, score in results if score >= config.min_relevance_score
    ]
    if not relevant_results:
        return "没有找到相关依据。"

    context = _format_context(relevant_results)
    user_prompt = f"{context}\n\n问题：{question}"
    try:
        chat_model = get_chat_model()
    except RuntimeError as exc:
        if "OPENAI_API_KEY is not configured" not in str(exc):
            raise
        return _fallback_answer(question, relevant_results)

    response = chat_model.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
    )
    logger.info("RAG answer generated in %.2fs", time.perf_counter() - started)
    return str(response.content).strip()
