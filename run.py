"""Unified command line entry point.

Usage examples::

    python run.py                 # start the web workspace (same as: python run.py web)
    python run.py web --reload    # start with auto-reload for development
    python run.py index           # rebuild the local Chroma vector index
    python run.py eval "帮我评估一套..."   # run the LangGraph workflow in the terminal
    python run.py rag "收益法的资本化率怎么确定"  # run the RAG question answering chain
    python run.py agent "某商铺年净收益60万元，资本化率5%..."  # tool-calling agent
    python run.py check           # environment / knowledge-base self check
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _read_question(value: str | None) -> str:
    question = (value or "").strip() or input("请输入问题：").strip()
    if not question:
        raise SystemExit("问题不能为空。")
    return question


def _command_web(args: argparse.Namespace) -> None:
    import uvicorn

    from app.config import load_config

    config = load_config()
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=args.reload,
        log_level=config.log_level.lower(),
    )


def _command_index(args: argparse.Namespace) -> None:
    from app.services.knowledge_service import build_index

    docs, chunks, count = build_index(rebuild=True)
    print(f"索引构建完成：{docs} 份文档，{chunks} 个切片，向量库共 {count} 条向量。")


def _command_eval(args: argparse.Namespace) -> None:
    from app.services.workflow_service import initial_state, run_workflow

    question = _read_question(args.question)
    result = run_workflow(initial_state(question=question))
    print(result.answer or "未生成报告。")


def _command_rag(args: argparse.Namespace) -> None:
    from app.rag.chain import answer

    print(answer(_read_question(args.question)))


def _command_agent(args: argparse.Namespace) -> None:
    from app.agent.graph import agent_app

    question = _read_question(args.question)
    result = agent_app.invoke({"question": question, "context": "", "messages": [], "answer": ""})
    print(str(result.get("answer", "")).replace("−", "-"))


def _command_check(args: argparse.Namespace) -> None:
    from app.config import load_config
    from app.rag.loader import load_docs

    config = load_config()
    print("环境自检")
    print(f"  项目根目录 : {ROOT}")
    print(f"  Python     : {sys.version.split()[0]}")
    print(f"  监听地址   : {config.host}:{config.port}")
    print(f"  文本模型   : {config.model} @ {config.base_url or 'OpenAI 默认端点'}")
    print(f"  Embedding  : {config.embedding_model}")
    print(f"  API Key    : {'已配置' if config.api_key and config.api_key != 'your-api-key-here' else '未配置'}")
    print(f"  视觉模型   : {'已配置' if config.vision_api_key else '未配置（户型图解析不可用）'}")

    docs = load_docs(config.docs_dir)
    print(f"  知识文档   : {len(docs)} 份（{config.docs_dir}）")
    vector_dir = Path(config.vector_db_dir)
    print(f"  向量库     : {'已存在' if (vector_dir / 'chroma.sqlite3').exists() else '未构建'}（{vector_dir}）")
    if not docs:
        raise SystemExit("自检失败：data/docs 为空。")
    if not (vector_dir / "chroma.sqlite3").exists():
        print("提示：运行 `python run.py index` 构建向量库。")

    if args.llm:
        from app.llm import get_chat_model

        reply = get_chat_model().invoke("只回复两个字：你好")
        print(f"  LLM 连通性 : {str(reply.content).strip()[:30]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="房地产估价智能体统一入口")
    subparsers = parser.add_subparsers(dest="command")

    web = subparsers.add_parser("web", help="启动 Web 工作台（默认）")
    web.add_argument("--reload", action="store_true", help="开发模式：代码变更自动重载")
    web.set_defaults(handler=_command_web)

    index = subparsers.add_parser("index", help="重建本地向量索引")
    index.set_defaults(handler=_command_index)

    evaluate = subparsers.add_parser("eval", help="在终端运行估价工作流")
    evaluate.add_argument("question", nargs="?", help="估价需求；省略则交互输入")
    evaluate.set_defaults(handler=_command_eval)

    rag = subparsers.add_parser("rag", help="在终端运行 RAG 问答")
    rag.add_argument("question", nargs="?", help="问题；省略则交互输入")
    rag.set_defaults(handler=_command_rag)

    agent = subparsers.add_parser("agent", help="在终端运行 Tool Calling Agent")
    agent.add_argument("question", nargs="?", help="问题；省略则交互输入")
    agent.set_defaults(handler=_command_agent)

    check = subparsers.add_parser("check", help="检查环境与知识库状态")
    check.add_argument("--llm", action="store_true", help="额外发起一次真实 LLM 连通性请求")
    check.set_defaults(handler=_command_check)

    return parser


def main(argv: list[str] | None = None) -> None:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        args = parser.parse_args(["web", *(argv or [])])
    args.handler(args)


if __name__ == "__main__":
    main()
