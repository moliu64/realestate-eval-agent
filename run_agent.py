from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.graph import agent_app


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python run_agent.py "估价场景"')
    question = " ".join(sys.argv[1:]).strip()
    result = agent_app.invoke({"question": question, "context": "", "messages": [], "answer": ""})
    answer = result["answer"].replace("−", "-")
    print(answer)


if __name__ == "__main__":
    main()
