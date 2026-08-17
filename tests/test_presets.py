import unittest

from app.presets import build_wuhan_preset, preset_options


class WuhanPresetTest(unittest.TestCase):
    def test_options_expose_districts_and_years(self):
        options = preset_options()
        self.assertIn("武昌区", options["districts"])
        self.assertEqual(options["years"], list(range(2019, 2025)))

    def test_residential_preset_has_all_fields_and_sources(self):
        preset = build_wuhan_preset("武昌区", 2023, "住宅", area=100, building_age=10)
        self.assertEqual(preset["representative_grade"], 1)
        self.assertEqual(preset["official_land_unit"], 10800)
        self.assertEqual(preset["fields"]["land_value"]["value"], 1080000)
        self.assertEqual(preset["fields"]["depreciation"]["value"], 70000)
        self.assertEqual(len(preset["sources"]), 2)

    def test_year_changes_market_estimate(self):
        old = build_wuhan_preset("洪山区", 2022, "住宅")
        current = build_wuhan_preset("洪山区", 2024, "住宅")
        self.assertGreater(old["fields"]["comparable_price"]["value"], current["fields"]["comparable_price"]["value"])

    def test_invalid_district_is_rejected(self):
        with self.assertRaises(ValueError):
            build_wuhan_preset("北京市", 2023, "住宅")


if __name__ == "__main__":
    unittest.main()
