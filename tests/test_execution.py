"""Editorial regression checks for shared clocks and transport handoffs.

These checks prove document consistency, not future opening or road permission.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLANS = ('primary.qmd', 'option-skip-qiqian.qmd')


def daily_tables(text):
    tables = []
    for part in text.split('| 时间 | 安排 | 对应高德导航点 |')[1:]:
        rows = []
        for line in part.lstrip('\n').splitlines():
            if not line.startswith('|'):
                break
            if not line.startswith('|---'):
                rows.append(line)
        tables.append(rows)
    return tables


def clock_window(row):
    cell = row.split('|')[1]
    times = [int(h) * 60 + int(m) for h, m in re.findall(r'(\d{2}):(\d{2})', cell)]
    if not times or len(times) > 2:
        raise ValueError('Unrecognized time cell: ' + cell)
    return times[0], times[-1]


def check_order(rows):
    previous = 0
    for row in rows:
        start, end = clock_window(row)
        if not 0 <= start <= end < 24 * 60 or start < previous:
            raise ValueError('Overlapping or reversed time: ' + row)
        previous = end


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.plans = {name: (ROOT / name).read_text() for name in PLANS}
        self.tables = {name: daily_tables(text) for name, text in self.plans.items()}
        self.sources = (ROOT / 'sources.qmd').read_text()

    def test_all_sixteen_daily_tables_are_ordered(self):
        for name, tables in self.tables.items():
            self.assertEqual(len(tables), 8, name)
            for day, rows in enumerate(tables, 1):
                with self.subTest(plan=name, day=day):
                    check_order(rows)

    def test_blackhead_default_morning_starts_at_eight_with_optional_sunrise_separate(self):
        for name, tables in self.tables.items():
            rows = tables[3]
            self.assertEqual(clock_window(rows[0])[0], 480, name)
            self.assertNotIn((275, 320), [clock_window(row) for row in rows])
            self.assertIn('不进晨拍观测坡', '\\n'.join(rows))
            self.assertIn('候选晨拍：仅 9 月 28 日晚确认条件改善后启用', self.plans[name])
        self.assertIn('**04:35—05:20**', self.plans['primary.qmd'])

    def test_overlap_detector_rejects_a_regression(self):
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            check_order(['| 13:30—14:00 | hotel | x |', '| 13:50—15:00 | photo | y |'])

    def test_shared_clocks_and_actions_allow_plan_specific_hotel_navigation(self):
        for day in (2, 7, 8):
            # Column 3 intentionally names the supplied main-plan hotel only.
            left = [row.split('|')[1:3] for row in self.tables[PLANS[0]][day - 1]]
            right = [row.split('|')[1:3] for row in self.tables[PLANS[1]][day - 1]]
            self.assertEqual(left, right, f'Day {day}')
        left, right = [self.tables[name][2] for name in PLANS]
        self.assertEqual([clock_window(row) for row in left[:-2]],
                         [clock_window(row) for row in right[:-2]])
        self.assertEqual(clock_window(left[-1]), (975, 1005))
        self.assertEqual(clock_window(right[-1]), (1005, 1035))

    def test_arxan_return_car_retrieval_and_departure_are_separate(self):
        for text, tables in zip(self.plans.values(), self.tables.values()):
            windows = [clock_window(row) for row in tables[1]]
            for pair in ((630, 710), (710, 740), (740, 960)):
                self.assertIn(pair, windows)
            self.assertNotIn('11:40 离园', text)
            self.assertNotIn('11:40 前开始返回', text)
            self.assertIn('返回依子取自驾车与行李', text)
            self.assertIn('不是已确认的首班时刻', text)
        for phrase in ('10:30 开始返程', '11:50 回到金江沟', '12:20 驾车离场'):
            self.assertIn(phrase, self.sources)

    def test_bailudao_inbound_and_outbound_transfers_precede_driving(self):
        rows = self.tables[PLANS[0]][4]
        expected = [(840, 860), (860, 895), (895, 920), (920, 1050)]
        windows = [clock_window(row) for row in rows]
        for pair in expected:
            self.assertIn(pair, windows)
        text = self.plans[PLANS[0]]
        self.assertNotIn('室韦加满油', text)
        self.assertNotIn('室韦完成加油', text)
        self.assertNotIn('把夜间驾驶集中', text)
        self.assertIn('车程加查验余量超过 2 小时 10 分时必须更早走', text)
        self.assertIn('接驳不能落实则不下支路', self.sources)

    def test_genheyuan_has_a_full_return_to_car_and_hotel(self):
        rows = self.tables[PLANS[1]][5]
        windows = [clock_window(row) for row in rows]
        for pair in ((705, 735), (780, 840), (840, 940), (940, 960), (960, 1020)):
            self.assertIn(pair, windows)
        self.assertNotIn('14:10 前到达', self.plans[PLANS[1]])
        self.assertNotIn('14:10 前无法抵达', self.plans[PLANS[1]])
        self.assertIn('不是已核实车程', self.sources)

    def test_genhe_uses_one_shared_detour_rule_in_both_days_and_plans(self):
        include = '{{< include includes/genhe-detour.md >}}'
        for text in self.plans.values():
            self.assertEqual(text.count(include), 2)
        rule = (ROOT / 'includes/genhe-detour.md').read_text()
        self.assertIn('G332 K1066+350', rule)
        self.assertIn('明珠街向南', rule)
        self.assertIn('未证明局部绕行已纳入', rule)
        self.assertIn('{#genhe-bypass}', self.sources)
        self.assertIn('接口收藏点与局部导航尚待确认', self.sources)
        self.assertIn('主方案实际酒店已录入牧野小住', self.sources)
        self.assertIn('政府原文已核实，当期执行与导航折线匹配尚待确认', self.sources)

    def test_riverbend_spur_exit_precedes_main_road(self):
        for text in self.plans.values():
            section = text.split('| 候选时间 | 安排 | 对应高德导航点 |', 1)[1]
            rows = [line for line in section.split('</details>', 1)[0].splitlines()
                    if line.startswith('| ') and not line.startswith('|---')]
            check_order(rows)
            exit_row = next(row for row in rows if clock_window(row) == (1090, 1120))
            self.assertIn('支路原路退出', exit_row)
            main_row = next(row for row in rows if clock_window(row)[0] == 1120)
            self.assertIn('接回主路后', main_row)

    def test_car_return_deadline_uses_actual_store_not_city_reference(self):
        for text in (*self.plans.values(), self.sources):
            self.assertIn('H - D - R - B', text)
            self.assertIn('至少 60 分钟', text)
            self.assertIn('不执行下午长停', text)
        for tables in self.tables.values():
            self.assertIn((1170, 1230), [clock_window(row) for row in tables[7]])


if __name__ == '__main__':
    unittest.main()
