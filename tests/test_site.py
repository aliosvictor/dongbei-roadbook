import sys
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_project import validate_site


class RenderedSiteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.site = Path(self.temporary.name)
        self.html = '<div class="table-scroll"><table><tr><td>test</td></tr></table></div><p id="target">stop</p>'
        for name in ("index", "primary", "option-skip-qiqian", "sources"):
            (self.site / f"{name}.html").write_text(self.html, encoding="utf-8")

    def change_index(self, extra):
        (self.site / "index.html").write_text(self.html + extra, encoding="utf-8")

    def test_valid_cross_page_fragment(self):
        self.change_index('<a href="primary.html#target">day</a>')
        validate_site(self.site)

    def test_remote_font_import_rejected(self):
        (self.site / "theme.css").write_text('@import url("https://fonts.googleapis.com/css2?family=Example");')
        with self.assertRaisesRegex(ValueError, "remote font dependency"):
            validate_site(self.site)

    def test_missing_asset_rejected(self):
        self.change_index('<img src="missing.webp">')
        with self.assertRaisesRegex(ValueError, "missing asset"):
            validate_site(self.site)

    def test_missing_fragment_rejected(self):
        self.change_index('<a href="primary.html#missing">day</a>')
        with self.assertRaisesRegex(ValueError, "missing anchor"):
            validate_site(self.site)

    def test_duplicate_id_rejected(self):
        self.change_index('<p id="target">duplicate</p>')
        with self.assertRaisesRegex(ValueError, "duplicate fragment"):
            validate_site(self.site)

    def test_one_unwrapped_table_rejected(self):
        self.change_index('<table><tr><td>wide</td></tr></table>')
        with self.assertRaisesRegex(ValueError, "scroll wrappers"):
            validate_site(self.site)

    def test_unresolved_shortcode_rejected(self):
        self.change_index('<p>{{< var missing >}}</p>')
        with self.assertRaisesRegex(ValueError, "unresolved shortcode"):
            validate_site(self.site)


class OverviewPageTests(unittest.TestCase):
    def test_markdown_table_rows_keep_their_column_count(self):
        for file in ROOT.glob('*.qmd'):
            expected = None
            for number, line in enumerate(file.read_text().splitlines(), start=1):
                if not line.startswith('|'):
                    expected = None
                    continue
                count = len(re.split(r'(?<!\\)\|', line)) - 2
                if expected is None:
                    expected = count
                self.assertEqual(count, expected, f'{file.name}:{number}: table column drift')

    def test_sunrise_table_keeps_times_and_selected_sunset(self):
        for name in ('primary.qmd', 'option-skip-qiqian.qmd'):
            text = (ROOT/name).read_text().split('## 三、日出与日落参考', 1)[1].split('## 四、', 1)[0]
            self.assertIn('| 9 月 27 日 | 乌苏浪子湖（日出） | 05:50 | — | 05:10—05:15 |', text)
            self.assertIn('| 9 月 27 日 | 新左旗阿木古郎（日落） | — | 约 17:57 |', text)

    def test_primary_precedes_backup_without_summary_cards(self):
        source = (ROOT / "index.qmd").read_text()
        self.assertNotIn("trip-pulse", source)
        rules = source.split("## 一、方案选择规则", 1)[1].split("## 二、", 1)[0]
        self.assertLess(rules.index("**主方案**"), rules.index("**备用方案**"))
        self.assertLess(rules.index("[主方案]"), rules.index("[备用方案]"))
        usage = next(line for line in source.splitlines() if line.startswith("| 使用顺序 |"))
        self.assertNotIn("默认执行", usage)
        for filename in ("overview.webp", "skip_overview.webp"):
            self.assertIn(f"figures/maps/{filename}", source)


class PreparationPageTests(unittest.TestCase):
    def test_six_preparation_sections_and_risk_map_are_preserved(self):
        source = (ROOT / "sources.qmd").read_text()
        self.assertEqual(re.findall(r"^## .*\{#([^}]+)\}$", source, re.M), [
            "traffic-documents", "places-bookings", "weather-shooting",
            "drone-checks", "photo-equipment", "supplies",
        ])
        self.assertIn("figures/maps/risk.webp", source)

    def test_shared_plans_link_to_preparation_details(self):
        for name in ("primary.qmd", "option-skip-qiqian.qmd"):
            source = (ROOT / name).read_text()
            for anchor in ("permits", "photo-equipment", "supplies"):
                self.assertIn(f"sources.qmd#{anchor}", source, name)


if __name__ == "__main__":
    unittest.main()
