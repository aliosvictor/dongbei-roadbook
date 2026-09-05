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


if __name__ == '__main__':
    unittest.main()
