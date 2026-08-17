import json
import os
from pathlib import Path
import unittest

from app.agent.graph import agent_app


@unittest.skipUnless(os.getenv("RUN_LLM_TESTS") == "1", "requires real LLM with tool calling")
class AgentEndToEndTest(unittest.TestCase):
    def test_all_valuation_scenarios(self):
        cases = [
            json.loads(line)
            for line in Path("tests/fixtures/agent_questions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for case in cases:
            result = agent_app.invoke(
                {
                    "question": case["question"],
                    "context": "",
                    "messages": [],
                    "answer": "",
                }
            )
            norm = result["answer"].replace(",", "").replace("−", "-")
            with self.subTest(question=case["question"]):
                self.assertIn(case["expected_value"], norm)
                self.assertIn(case["expected_source"], norm)


if __name__ == "__main__":
    unittest.main()
