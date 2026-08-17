from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.workflow.graph import workflow_app


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python run_eval.py "估价需求"')
    question = " ".join(sys.argv[1:]).strip()
    result = workflow_app.invoke(
        {
            "question": question,
            "requirement": {},
            "methods": [],
            "params": {},
            "current_method": "",
            "context": "",
            "trend_sources": [],
            "computations": [],
            "verification": "",
            "report": "",
            "messages": [],
            "loop_count": 0,
        }
    )
    print(result["report"].replace("−", "-"))


if __name__ == "__main__":
    main()
