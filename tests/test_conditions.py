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
        self.assertIn('2026-09-20', self.weather)
        self.assertIn('9 月 19 日为首日', self.weather)
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
            self.assertIn(f'[{name}](https://e.weather.com.cn/mweather15d/{code}.shtml)',
                          self.weather)
        self.assertIn('未取得奇乾村、白鹿岛、莫尔道嘎本地', self.weather)
        self.assertIn('不能用陈旗旗府天气替代民宿实况', self.weather)

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
