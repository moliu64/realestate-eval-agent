import operator
import os
import unittest
from typing import get_args, get_type_hints
from unittest.mock import patch

from langchain_core.documents import Document

from app.workflow.graph import workflow_app
from app.workflow.nodes import (
    _supplement_params_from_question,
    compute_node,
    next_method_node,
    report_node,
    retrieve_node,
    route_next_method,
    understand_node,
)
from app.workflow.schemas import MethodPlanSchema, RequirementSchema
from app.workflow.schemas import ReportSchema
from app.workflow.state import EvalState


class WorkflowUnitTest(unittest.TestCase):
    @patch("app.workflow.nodes._structured_invoke")
    def test_understand_skips_prefilled_requirement(self, structured_invoke):
        result = understand_node({"question": "ignored", "requirement": {"area": 100}})
        self.assertEqual(result, {})
        structured_invoke.assert_not_called()

    def test_schema_fields_exist(self):
        self.assertIn("known_data", RequirementSchema.model_fields)
        self.assertIn("missing_data", RequirementSchema.model_fields)
        self.assertIn("methods", MethodPlanSchema.model_fields)
        self.assertIn("params", MethodPlanSchema.model_fields)
        self.assertIn("report_markdown", ReportSchema.model_fields)
        self.assertIn("computations", ReportSchema.model_fields)

    def test_computations_uses_add_reducer(self):
        hints = get_type_hints(EvalState, include_extras=True)
        metadata = get_args(hints["computations"])[1:]
        self.assertIn(operator.add, metadata)

    def test_next_method_consumes_queue(self):
        state = {"methods": ["market_comparison", "income"], "loop_count": 0}
        first = next_method_node(state)
        self.assertEqual(first["current_method"], "market_comparison")
        self.assertEqual(first["methods"], ["income"])
        self.assertEqual(route_next_method(first), "retrieve")

        second_state = {"methods": first["methods"], "loop_count": first["loop_count"]}
        second = next_method_node(second_state)
        self.assertEqual(second["current_method"], "income")
        self.assertEqual(second["methods"], [])

        final_state = {"methods": second["methods"], "loop_count": second["loop_count"]}
        final = next_method_node(final_state)
        self.assertEqual(route_next_method(final), "verify")

    def test_compute_income_single_method(self):
        state = {
            "current_method": "income",
            "params": {"income": {"net_income": 600000, "cap_rate": 0.05}},
            "context": "[来源: 估价方法_收益法.md]\n收益法资料",
        }
        result = compute_node(state)
        computation = result["computations"][0]
        self.assertEqual(computation["method"], "income")
        self.assertIn("12000000", computation["result"])
        self.assertEqual(computation["source"], "估价方法_收益法.md")

    def test_compute_missing_data(self):
        state = {
            "current_method": "income",
            "params": {"income": {"net_income": 600000}},
            "context": "[来源: 估价方法_收益法.md]\n收益法资料",
        }
        result = compute_node(state)
        computation = result["computations"][0]
        self.assertIn("缺少参数", computation["result"])
        self.assertIn("cap_rate", computation["missing"])

    def test_supplement_income_params(self):
        params = _supplement_params_from_question(
            "某商铺年度稳定净收益60万元，资本化率5%，请评估价值。",
            {"known_data": {}, "area": None},
            ["income"],
            {"income": {}},
        )
        self.assertEqual(params["income"]["net_income"], 600000)
        self.assertEqual(params["income"]["cap_rate"], 0.05)

    def test_supplement_multi_method_params(self):
        params = _supplement_params_from_question(
            "100平方米住宅，可比成交单价20000元/平方米，年租金净收益8万元，资本化率4%。",
            {"known_data": {}, "area": 100},
            ["market_comparison", "income"],
            {"market_comparison": {}, "income": {}},
        )
        self.assertEqual(params["market_comparison"]["comparable_price"], 20000)
        self.assertEqual(params["market_comparison"]["area"], 100)
        self.assertEqual(params["income"]["net_income"], 80000)
        self.assertEqual(params["income"]["cap_rate"], 0.04)

    @patch("app.workflow.nodes.retrieve")
    def test_retrieve_separates_method_context_and_trend_sources(self, mock_retrieve):
        method_doc = Document(page_content="市场比较法资料", metadata={"source": "估价方法_市场比较法.md"})
        trend_doc = Document(page_content="武汉房价走势", metadata={"source": "市场数据_武汉住宅价格指数.md"})
        mock_retrieve.side_effect = [[(method_doc, 0.9)], [(trend_doc, 0.95)]]

        result = retrieve_node({
            "current_method": "market_comparison",
            "question": "结合武汉房价走势和房龄影响给参考估值",
        })

        self.assertIn("估价方法_市场比较法.md", result["context"])
        self.assertNotIn("市场数据_武汉住宅价格指数.md", result["context"])
        self.assertEqual(result["trend_sources"], ["市场数据_武汉住宅价格指数.md"])

    def test_report_uses_separate_trend_sources(self):
        result = report_node({
            "question": "2015年建成、89㎡两房、光谷，结合武汉房价走势和房龄影响给参考估值",
            "requirement": {"area": 89, "layout": "两房", "building_age": 10, "missing_data": []},
            "computations": [],
            "trend_sources": ["市场数据_武汉住宅价格指数.md"],
            "verification": "",
        })
        self.assertIn("市场趋势依据：[来源: 市场数据_武汉住宅价格指数.md]", result["report"])

    @patch("app.workflow.nodes._retrieve_trend_sources", return_value=["市场数据_武汉住宅价格指数.md"])
    def test_report_retrieves_trend_when_no_method_runs(self, mock_trend):
        result = report_node({
            "question": "结合武汉房价走势和房龄影响给参考估值",
            "requirement": {"missing_data": []},
            "computations": [],
            "trend_sources": [],
            "verification": "",
        })
        self.assertIn("市场趋势依据：[来源: 市场数据_武汉住宅价格指数.md]", result["report"])
        mock_trend.assert_called_once()


@unittest.skipUnless(os.getenv("RUN_LLM_TESTS") == "1", "requires real LLM")
class WorkflowEndToEndTest(unittest.TestCase):
    def _invoke(self, question: str):
        return workflow_app.invoke(
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
                "report_json": "",
                "messages": [],
                "loop_count": 0,
            }
        )

    def test_income_workflow_report(self):
        result = self._invoke("某商铺年度稳定净收益60万元，资本化率5%，请评估价值并说明依据。")
        report = result["report"].replace(",", "")
        self.assertIn("12000000", report)
        self.assertIn("估价方法_收益法.md", report)
        self.assertIn("## 5. 交叉校核结论", report)

    def test_multi_method_workflow_report(self):
        result = self._invoke(
            "帮我评估一套100平方米二手住宅，有近期可比成交单价20000元/平方米；"
            "同时年租金净收益8万元，资本化率4%，请做多方法校核。"
        )
        report = result["report"].replace(",", "")
        self.assertGreaterEqual(len(result["computations"]), 2)
        self.assertIn("2000000", report)
        self.assertIn("估价方法_市场比较法.md", report)
        self.assertIn("估价方法_收益法.md", report)


if __name__ == "__main__":
    unittest.main()
