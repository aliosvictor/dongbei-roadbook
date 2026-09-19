"""Main-plan hotel regression checks: supplied dates are not booking confirmations."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_project import validate_lodgings
from build_lodgings import bd09_to_gcj02, generated_lodgings
from update_amap_routes import generated_variables


class LodgingTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "data/itinerary.json").read_text())
        self.lodgings = json.loads((ROOT / "data/lodgings.json").read_text())

    def test_all_eight_nights_and_daily_endpoints(self):
        validate_lodgings(self.data, self.lodgings)

    def test_date_overlap_is_rejected(self):
        self.lodgings["stays"][1]["check_in"] = "2026-09-25"
        with self.assertRaisesRegex(ValueError, "date gap or overlap"):
            validate_lodgings(self.data, self.lodgings)

    def test_false_poi_link_is_rejected(self):
        self.lodgings["stays"][2]["amap_url"] = "https://www.amap.com/place/invented"
        with self.assertRaisesRegex(ValueError, "honest name search"):
            validate_lodgings(self.data, self.lodgings)

    def test_wrong_hotel_city_is_rejected(self):
        self.lodgings["stays"][3]["city"] = "海拉尔区"
        with self.assertRaisesRegex(ValueError, "Wrong hotel search"):
            validate_lodgings(self.data, self.lodgings)

    def test_baidu_coordinates_must_not_be_used_directly_in_amap(self):
        self.data["places"]["saina"]["lon"] = self.lodgings["stays"][3]["map_reference"]["lon"]
        with self.assertRaisesRegex(ValueError, "Hotel coordinate drift"):
            validate_lodgings(self.data, self.lodgings)

    def test_converter_matches_existing_yizi_reference(self):
        self.assertEqual(bd09_to_gcj02(120.219723, 47.350449), (120.213251, 47.34439))

    def test_generated_table_and_links_are_current(self):
        table, links = generated_lodgings(self.lodgings)
        self.assertEqual((ROOT / "includes/lodgings-primary.md").read_text(), table)
        self.assertEqual((ROOT / "includes/lodging-links.md").read_text(), links)
        self.assertEqual(table.count('data-lodging='), 8)
        self.assertEqual(links.count('https://uri.amap.com/search?'), 8)

    def test_daily_hotel_labels_match_the_single_lodging_list(self):
        names = {s["id"]: s["name"] for s in self.lodgings["stays"]}
        links = re.findall(r'\[([^]\n]+)\]\[stay-([a-z0-9_]+)\]', (ROOT / "primary.qmd").read_text())
        self.assertGreater(len(links), 25)
        for label, key in links:
            self.assertEqual(label, names[key])

    def test_risk_map_uses_the_updated_main_route(self):
        self.assertEqual(self.data["maps"]["risk"]["routes"], self.data["maps"]["overview"]["routes"])

    def test_saina_is_not_the_sunrise_slope_or_an_extra_roundtrip(self):
        day3 = self.data["maps"]["d03"]["routes"]
        day4 = self.data["maps"]["d04"]["routes"]
        self.assertEqual(day3[-1]["points"][-1], "saina")
        self.assertEqual(day4[0]["points"][:2], ["saina", "heishantou"])
        self.assertEqual(day4[0]["points"].count("saina"), 1)
        text = (ROOT / "primary.qmd").read_text()
        self.assertIn("| 04:35—05:20 |", text)
        self.assertIn("不回赛纳取行李", text)
        self.assertIn("19:15—19:45", text)
        self.assertNotIn("赛纳民宿已收藏住宿点", text)

    def test_backup_not_silently_bound_to_main_hotels(self):
        main_only = {s["id"] for s in self.lodgings["stays"]} - {"yizi"}
        for route in self.data["maps"]["skip_overview"]["routes"]:
            self.assertFalse(main_only.intersection(route["points"]))
        self.assertIn("不自动等于备用方案订房", (ROOT / "option-skip-qiqian.qmd").read_text())

    def test_harbin_hotel_and_rental_store_not_invented(self):
        self.assertEqual(self.lodgings["stays"][-1]["check_out"], "2026-10-03")
        text = (ROOT / "primary.qmd").read_text()
        self.assertIn("10 月 3 日哈尔滨住宿", text)
        self.assertIn("继续标为待补", text)

    def test_plan_difference_includes_all_hotel_endpoints(self):
        snapshot = json.loads((ROOT / "data/amap-routes.json").read_text())
        sums = []
        for key in ("overview", "skip_overview"):
            sums.append(sum(snapshot["routes"][r["amap_route"]]["distance_m"]
                            for r in self.data["maps"][key]["routes"] if r.get("draw", True)))
        value = f'{(sums[0] - sums[1]) / 1000:.1f}'
        self.assertIn('primary-extra-km: "' + value + '"', generated_variables(self.data, snapshot))

    def test_new_snapshot_timing_leaves_room_for_breaks(self):
        for filename in ("primary.qmd", "option-skip-qiqian.qmd"):
            text = (ROOT / filename).read_text()
            self.assertIn("| 08:40—12:45 |", text)
            self.assertNotIn("| 08:40—11:35 |", text)
            day5 = text.split("### Day 5", 1)[1].split("### Day 6", 1)[0]
            self.assertIn("| 08:00 |", day5)
            self.assertNotIn("| 09:00 |", day5)
            self.assertIn("07:20—", day5)


if __name__ == "__main__":
    unittest.main()
