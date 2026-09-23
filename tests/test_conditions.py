"""Dated travel guidance consistency; not a test of future weather or access."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConditionsTests(unittest.TestCase):
    def setUp(self):
        self.pages = {name: (ROOT / name).read_text() for name in (
            'index.qmd', 'primary.qmd', 'option-skip-qiqian.qmd', 'sources.qmd')}
        self.weather = (ROOT / 'includes/weather-outlook.md').read_text()

    def test_weather_covers_each_travel_day_and_arrival_night(self):
        dates = re.findall(r'^\| (\d+ 月 \d+ 日) ·', self.weather, re.M)
        self.assertEqual(dates, [f'9 月 {d} 日' for d in range(25, 31)]
                         + [f'10 月 {d} 日' for d in range(1, 4)])
        self.assertIn('2026-09-23', self.weather)
        self.assertIn('9 月 23 日为首日', self.weather)
        self.assertIn('覆盖至 9 月 29 日', self.weather)
        self.assertIn('9 月 30 日—10 月 3 日', self.weather)
        self.assertIn('第 8—15 天', self.weather)
        self.assertIn('不会自动刷新', self.weather)
        self.assertIn('不能直接当成当天 05:00', self.weather)

    def test_city_links_match_the_named_forecast_location(self):
        expected = {'齐齐哈尔': '101050201', '阿尔山': '101081102',
                    '新左旗': '101081008', '陈旗': '101081007',
                    '额尔古纳': '101081014', '根河': '101081015',
                    '嫩江': '101050602', '五大连池': '101050605',
                    '哈尔滨': '101050101'}
        for name, code in expected.items():
            kind = 'weather15d' if name in ('根河', '嫩江', '五大连池', '哈尔滨') else 'weather'
            self.assertIn(f'[{name}](https://www.weather.com.cn/{kind}/{code}.shtml)',
                          self.weather)
        self.assertIn('未取得奇乾村、白鹿岛逐点可靠预报', self.weather)
        self.assertIn('10108101401A.shtml', self.weather)
        self.assertIn('公园预报不等于奇乾村', self.weather)
        self.assertIn('不能用陈旗旗府天气替代民宿实况', self.weather)

    def test_candidate_roles_and_access_gate_match_across_plans(self):
        data = json.loads((ROOT / 'data/itinerary.json').read_text())
        self.assertEqual(data['places']['erguna_riverbend']['role'], 'optional')
        for key in ('erguna_riverbend_sunset', 'heishantou_sunrise'):
            self.assertEqual(data['photo_points'][key]['visit'], 'optional')
        self.assertEqual(data['photo_points']['xinzuoqi_sunset']['visit'], 'planned')
        gate = (ROOT / 'includes/riverbend-gate.md').read_text()
        for phrase in ('保护区边界尚未核定', '不专程去支路入口探路', '删除河湾途经点'):
            self.assertIn(phrase, gate)
        self.assertIn('{#riverbend-access}', self.pages['sources.qmd'])
        self.assertIn('1439809.html', self.pages['sources.qmd'])
        for day, key in (('d03', 'p03_direct'), ('s03', 'd03_direct')):
            self.assertEqual(data['maps'][day]['routes'][0]['amap_route'], key)
            self.assertNotIn('erguna_riverbend', data['amap_route_specs'][key]['points'])
            self.assertIn('erguna_riverbend_sunset', data['maps'][day]['photos'])
            self.assertIn(day, data['route_options'])
        for name in ('primary.qmd', 'option-skip-qiqian.qmd'):
            self.assertIn('{{< include includes/riverbend-gate.md >}}', self.pages[name])
            self.assertIn('候选晨拍：仅 9 月 28 日晚确认条件改善后启用', self.pages[name])
        for text in self.pages.values():
            for stale in ('河湾固定日落', '唯一固定日落', '两个明确蓝点', '| 固定早起 |'):
                self.assertNotIn(stale, text)

    def test_original_road_notice_and_historical_reopening_are_distinguished(self):
        text = self.pages['sources.qmd']
        for phrase in ('1431216.html', '1444462.html', '1448717.html',
                       '政府原文已核实', '7 月 22 日 17:30', '截至 8 月 6 日'):
            self.assertIn(phrase, text)
        self.assertNotIn('未取得原发布页', text)
        self.assertNotIn('仍只有封闭公告转载', text)

    def test_cold_weather_is_conditional_and_wenbo_is_not_a_mandatory_four_hours(self):
        for name in ('primary.qmd', 'option-skip-qiqian.qmd'):
            text = self.pages[name]
            self.assertIn('{{< include includes/cold-weather-gate.md >}}', text)
            self.assertIn('不强凑 4 小时', text)
            self.assertIn('最长 4 小时拍摄预算', text)
        self.assertNotIn('9 月 28 日和 10 月 3 日也均为 08:00 起床，接受主路夜间驾驶', self.pages['option-skip-qiqian.qmd'])
        self.assertIn('15:45 是最晚离场上限', self.weather)
        self.assertIn('备用方案同受冷空气影响', self.weather)

    def test_dated_weather_has_one_authoritative_table(self):
        for name in ('index.qmd', 'primary.qmd', 'option-skip-qiqian.qmd'):
            self.assertIn('{{< include includes/conditions-update.md >}}', self.pages[name])
            self.assertNotIn('{{< include includes/weather-outlook.md >}}', self.pages[name])
        self.assertIn('{{< include includes/weather-outlook.md >}}', self.pages['sources.qmd'])

    def test_expired_preparation_deadlines_are_not_future_instructions(self):
        for text in self.pages.values():
            for stale in ('9 月 16 日前提交', '现在至 9 月 16 日', '9 月 19 日前向'):
                self.assertNotIn(stale, text)
        self.assertIn('不是保证获批', self.pages['sources.qmd'])

    def test_qiqihar_exit_retains_plan_specific_routing(self):
        snapshot = json.loads((ROOT / 'data/amap-routes.json').read_text())['routes']
        self.assertIn('G10绥满高速', snapshot['p01']['roads'])
        self.assertIn('碾北公路', snapshot['d01']['roads'])
        self.assertNotIn('G10绥满高速', snapshot['d01']['roads'])
        for name in ('primary.qmd', 'option-skip-qiqian.qmd'):
            self.assertIn('{{< include includes/qiqihar-exit.md >}}', self.pages[name])

    def test_management_scope_and_people_vehicle_permits_remain_distinct(self):
        text = self.pages['sources.qmd']
        for phrase in ('{#jurisdictions}', '兴安盟阿尔山市', '不是鄂温克族自治旗',
                       '根河河湾机位不等于根河市', '原则上一人一证', '原则上一车一证',
                       '防火期不等于全境封山', '不是行政边界图或法定许可范围'):
            self.assertIn(phrase, text)

    def test_disputed_park_status_is_not_rendered_as_confirmed_closure(self):
        data = json.loads((ROOT / 'data/itinerary.json').read_text())
        self.assertIn('开放待确认', data['photo_points']['heilongshan_volcano']['name'])
        for text in self.pages.values():
            self.assertNotIn('恢复开放', text)
            self.assertNotIn('高德当前显示暂停开放', text)
        self.assertIn('来源状态不一致', self.pages['sources.qmd'])

    def test_common_road_closure_does_not_imply_an_open_backup(self):
        self.assertIn('共用进路受限则暂缓', self.pages['primary.qmd'])
        self.assertIn('只有交通部门确认另一条开放路线后', self.pages['option-skip-qiqian.qmd'])
        self.assertIn('不是本次从临江进入奇乾的完整进路', self.pages['sources.qmd'])
        self.assertIn('左旗日落 16:45—18:25', self.weather)


if __name__ == '__main__':
    unittest.main()
