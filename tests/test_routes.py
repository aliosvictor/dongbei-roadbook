import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_maps import route_chunks
from update_amap_routes import (
    generated_variables, geometry_from_path, parse_geometry,
    validate_route_points, validate_snapshot,
)
from validate_project import validate_data


def point(lon):
    return {"name": str(lon), "lon": lon, "lat": 50.0, "route_snap_tolerance_m": 30}


class RouteIntegrityTests(unittest.TestCase):
    def test_ordered_route(self):
        self.assertEqual(validate_route_points([point(120), point(120.02), point(120.04)], ["120,50;120.02,50;120.04,50"]), [0, 0, 0])

    def test_reversed_vias_rejected_with_correct_endpoints(self):
        with self.assertRaises(RuntimeError):
            validate_route_points([point(x) for x in [120,120.02,120.04,120.06]], ["120,50;120.04,50;120.02,50;120.06,50"])

    def test_reversed_endpoints_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_route_points([point(120),point(121)], ["121,50;120,50"])

    def test_legitimate_return_trip(self):
        self.assertEqual(validate_route_points([point(120),point(121),point(120)], ["120,50;121,50;120,50"]), [0,0,0])

    def test_missing_point_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_route_points([point(120),point(121)], ["120,50;120.02,50"])

    def test_nonfinite_and_out_of_range(self):
        for geometry in [[],[""],["nan,50"],["120,inf"],["181,50"],["120,91"]]:
            with self.subTest(geometry=geometry), self.assertRaises(ValueError):
                parse_geometry(geometry)

    def test_empty_api_path_rejected(self):
        with self.assertRaises(RuntimeError):
            geometry_from_path({"roads": []})

    def test_step_gaps_not_joined(self):
        route={"points":["a","b"],"kind":"drive","amap_route":"test"}
        snapshot={"test":{"points":["a","b"],"kind":"drive","geometry":["120,50;120.01,50","120.02,50;120.03,50"],"geometry_point_count":4}}
        chunks=route_chunks(route,snapshot)
        self.assertEqual([len(c) for c in chunks],[2,2])
        self.assertNotEqual(chunks[0][-1],chunks[1][0])

    def test_undrawn_route_has_no_geometry(self):
        self.assertEqual(route_chunks({"draw":False},{}),[])

    def test_all_repository_data(self):
        validate_data(json.loads((ROOT/'data/itinerary.json').read_text()),json.loads((ROOT/'data/amap-routes.json').read_text()))

    def test_coordinate_changes_invalidate_snapshot(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        snapshot=json.loads((ROOT/'data/amap-routes.json').read_text())['routes']['d07']
        data['places']['aoluguya']['lon']+=0.001
        with self.assertRaisesRegex(ValueError,'coordinates are stale'):
            validate_snapshot(data['amap_route_specs']['d07'],snapshot,data['places'])

    def test_changed_link_rejected(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        snapshot=json.loads((ROOT/'data/amap-routes.json').read_text())['routes']['d07']
        snapshot['route_url']='https://www.amap.com/'
        with self.assertRaisesRegex(ValueError,'navigation link'):
            validate_snapshot(data['amap_route_specs']['d07'],snapshot,data['places'])

    def test_metrics_change_with_snapshot(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        snapshot=json.loads((ROOT/'data/amap-routes.json').read_text())
        before=generated_variables(data,snapshot)
        snapshot['routes']['d07']['distance_m']+=1000
        self.assertNotEqual(before,generated_variables(data,snapshot))

    def test_day_five_transfer_and_navigation_agree(self):
        for filename,slot in [('primary.qmd','11:10—11:40'),('option-skip-qiqian.qmd','11:30—12:00')]:
            text=(ROOT/filename).read_text()
            line=next(line for line in text.splitlines() if line.startswith('| '+slot+' |'))
            self.assertIn('B0IK3CUHLM',line)
            self.assertIn('B0FFH58MN1',line)
            self.assertNotIn('白鹿岛',line)

    def test_left_banner_sunset_and_next_day_route_agree(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        self.assertEqual(data['amap_route_specs']['d02_drive']['points'],['jinjianggou','xinzuoqi'])
        self.assertEqual(data['amap_route_specs']['d03']['points'][0],'xinzuoqi')
        self.assertIn('xinzuoqi_sunset',data['maps']['d02']['photos'])
        self.assertEqual(data['navigation_points']['amugulang_wetland']['status'],'name_search')
        for day in ('d02','d03'):
            self.assertEqual(data['maps'][day]['routes'],data['maps']['s'+day[1:]]['routes'])
        for filename in ('primary.qmd','option-skip-qiqian.qmd'):
            text=(ROOT/filename).read_text()
            self.assertIn('阿木古郎湿地公园没有经过独立核实的停车场落点',text)
            self.assertNotIn('海拉尔是 9 月 27 日固定住宿和补给点',text)

    def test_unselected_stops_and_imaginary_photo_coordinates_removed(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        for key in ('shanshui_rock','moa_valley','moerdaoga_forest'):
            self.assertNotIn(key,data['photo_points'])
        for filename in ('index.qmd','primary.qmd','option-skip-qiqian.qmd','sources.qmd'):
            text=(ROOT/filename).read_text()
            for name in ('山水岩壁画','白龙湖','柴河源游客服务中心','图嘎营地'):
                self.assertNotIn(name,text)

    def test_north_route_does_not_force_campsite_detour(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        self.assertEqual(data['amap_route_specs']['d03']['points'],['xinzuoqi','morigele_cliff','erguna_riverbend','heishantou'])

    def test_shared_photography_choices_are_identical(self):
        texts=[(ROOT/name).read_text().split('### 每日拍摄安排',1)[1].split('## 三、',1)[0] for name in ('primary.qmd','option-skip-qiqian.qmd')]
        for date in ('9 月 26 日','9 月 27 日','9 月 28 日','9 月 29 日','10 月 2 日','10 月 3 日'):
            rows=[next(line for line in text.splitlines() if line.startswith('| '+date+' |')) for text in texts]
            self.assertEqual(rows[0],rows[1],date)

    def test_conditional_photography_is_explicit_and_not_repeated(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        for key in ('dujuan_lake','shitang_forest','baka_curve','jiuka_valley','qika_light'):
            self.assertEqual(data['photo_points'][key]['visit'],'optional')
        for day in ('d05','s05'):
            self.assertNotIn('qika_light',data['maps'][day]['photos'])
        for key in ('xinzuoqi_sunset','erguna_riverbend_sunset'):
            self.assertEqual(data['photo_points'][key]['visit'],'planned')

    def test_qiqian_return_does_not_force_second_bailudao_visit(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        self.assertEqual(data['amap_route_specs']['d06']['points'],['qiqian','moerdaoga','genhe'])
        text=(ROOT/'primary.qmd').read_text()
        day=text.split('### Day 6',1)[1].split('### Day 7',1)[0]
        self.assertNotIn('| 11:30—11:50 |',day)
        self.assertIn('午餐出镇后',day)

    def test_harbin_station_not_an_execution_destination(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        self.assertEqual(data['places']['harbin']['role'],'reference')
        for filename in ('primary.qmd','option-skip-qiqian.qmd'):
            text=(ROOT/filename).read_text()
            self.assertNotIn('哈尔滨站',text)
            self.assertIn('还车门店（待录入）',text)

    def test_visit_status_and_overview_photo_drift_rejected(self):
        data=json.loads((ROOT/'data/itinerary.json').read_text())
        snapshot=json.loads((ROOT/'data/amap-routes.json').read_text())
        data['photo_points']['dujuan_lake'].pop('visit')
        with self.assertRaisesRegex(ValueError,'visit status'):
            validate_data(data,snapshot)
        data['photo_points']['dujuan_lake']['visit']='optional'
        data['maps']['overview']['photos'].remove('dujuan_lake')
        with self.assertRaisesRegex(ValueError,'daily photo drift'):
            validate_data(data,snapshot)


if __name__ == '__main__':
    unittest.main()
