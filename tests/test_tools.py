import unittest

from app.tools.valuation import (
    calc_cost_approach,
    calc_income_approach,
    calc_market_comparison,
)


class ValuationToolsTest(unittest.TestCase):
    def test_income_approach(self):
        result = calc_income_approach.invoke({"net_income": 600000, "cap_rate": 0.05})
        self.assertIn("12000000", result)
        self.assertIn("年度稳定净收益", result)

    def test_income_approach_rejects_invalid_cap_rate(self):
        result = calc_income_approach.invoke({"net_income": 600000, "cap_rate": 0})
        self.assertIn("资本化率必须大于 0", result)

    def test_market_comparison(self):
        result = calc_market_comparison.invoke({"comparable_price": 20000, "area": 100})
        self.assertIn("20000", result)
        self.assertIn("2000000", result)

    def test_cost_approach(self):
        result = calc_cost_approach.invoke(
            {"land_value": 1000000, "replacement_cost": 2000000, "depreciation": 300000}
        )
        self.assertIn("2700000", result)


if __name__ == "__main__":
    unittest.main()
