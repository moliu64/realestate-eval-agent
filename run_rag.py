from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag.chain import answer


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python run_rag.py "你的问题"')
    question = " ".join(sys.argv[1:]).strip()
    print(answer(question))


if __name__ == "__main__":
    main()
