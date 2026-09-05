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
    def test_all_daily_rows_have_exactly_one_execution_role(self):
        for name in ('primary.qmd', 'option-skip-qiqian.qmd'):
            days, rows, active = 0, 0, False
            for line in (ROOT/name).read_text().splitlines():
                if line == '| 时间 | 安排 | 对应高德导航点 |':
                    days += 1
                    active = True
                    continue
                if not line.startswith('|'):
                    active = False
                if active and not line.startswith('|---'):
                    rows += 1
                    self.assertEqual(len(re.findall(r'class="stop-tag row-(?:planned|optional|logistics|drive|rest)"', line)), 1, line)
            self.assertEqual(days, 8)
            self.assertGreater(rows, 65)

    def test_mixed_rows_do_not_make_lodging_or_rest_optional(self):
        cases = [('primary.qmd','| 18:10—20:15 |','row-drive'),
                 ('primary.qmd','| 09:10—09:25 |','row-rest'),
                 ('option-skip-qiqian.qmd','| 14:15—16:40 |','row-logistics')]
        for name, prefix, role in cases:
            line=next(x for x in (ROOT/name).read_text().splitlines() if x.startswith(prefix))
            self.assertIn('optional-stop', line)
            self.assertIn(role, line)
            self.assertNotIn('row-optional', line)
        css=(ROOT/'styles.css').read_text()
        for forbidden in ('tr:has(.optional-stop)', 'tr:has(.drone-no-fly)', 'tr:has(.drone-check)'):
            self.assertNotIn(forbidden, css)

    def test_stop_legend_is_shared_and_grade_is_not_a_visit_rule(self):
        for name in ('index.qmd','primary.qmd','option-skip-qiqian.qmd','sources.qmd'):
            text=(ROOT/name).read_text()
            self.assertEqual(text.count('{{< include includes/stop-legend.md >}}'), 1)
            self.assertNotIn('空心蓝点', text)
            self.assertNotIn('红色时间行', text)
            self.assertNotIn('固定导航到宾馆停车', text)
        legend=(ROOT/'includes/stop-legend.md').read_text()
        self.assertIn('紫色 · 选停 / 备选', legend)
        self.assertIn('与 S / A / B 摄影等级无关', legend)

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
