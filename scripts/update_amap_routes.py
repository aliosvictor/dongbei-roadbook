#!/usr/bin/env python3
"""Refresh the checked Amap road-route snapshots used by the static maps.

The endpoint is the first-party JSON route endpoint used by Amap's current PC
route-planning page.  The generated file is a dated snapshot: driving times and
recommended paths must still be refreshed before departure.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ITINERARY = ROOT / "data" / "itinerary.json"
OUTPUT = ROOT / "data" / "amap-routes.json"
LINKS = ROOT / "includes" / "amap-route-links.md"
ROUTE_ENDPOINT = "https://amap-pc-ssr.amap.com/ssr/api/getCarRoutePlan"
ROUTE_PAGE = "https://amap-pc-ssr.amap.com/ssr/dir"
USER_AGENT = "Mozilla/5.0 (compatible; DongbeiRoadbook/1.0; personal route check)"


def route_page_url(points: list[dict]) -> str:
    start, *vias, destination = points
    params = {
        "fname": start["name"],
        "flat": f'{start["lat"]:.6f}',
        "flon": f'{start["lon"]:.6f}',
        "dname": destination["name"],
        "dlat": f'{destination["lat"]:.6f}',
        "dlon": f'{destination["lon"]:.6f}',
        "policy": "1",
        "type": "0",
    }
    if vias:
        params.update(
            {
                "vname": "|".join(point["name"] for point in vias),
                "vlat": "|".join(f'{point["lat"]:.6f}' for point in vias),
                "vlon": "|".join(f'{point["lon"]:.6f}' for point in vias),
            }
        )
    return f"{ROUTE_PAGE}?{urllib.parse.urlencode(params)}"


def request_route(points: list[dict]) -> tuple[dict, str]:
    start, *vias, destination = points
    params = {
        "fromX": f'{start["lon"]:.6f}',
        "fromY": f'{start["lat"]:.6f}',
        "toX": f'{destination["lon"]:.6f}',
        "toY": f'{destination["lat"]:.6f}',
        "originid": "",
        "start_poitype": "",
        "destinationid": "",
        "end_poitype": "",
        "viapoints": ";".join(f'{point["lon"]:.6f},{point["lat"]:.6f}' for point in vias),
        "policy2": "10",
        "dataTime": "now",
    }
    url = f"{ROUTE_ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Referer": f"{ROUTE_PAGE}?type=0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("code") != "1" and payload.get("code") != 1:
        raise RuntimeError(f"Amap route request failed: {payload!r}")
    paths = payload.get("data", {}).get("route", {}).get("paths", [])
    if not paths:
        raise RuntimeError(f"Amap returned no driving path for {url}")
    return paths[0], url


def geometry_from_path(path: dict) -> tuple[list[str], int]:
    """Preserve Amap's original step polylines without resampling."""
    polylines: list[str] = []
    point_count = 0
    for road in path.get("roads", []):
        for step in road.get("steps", []):
            polyline = step.get("polyline", "")
            if not polyline:
                continue
            pairs = [pair for pair in polyline.split(";") if pair]
            for pair in pairs:
                lon_text, lat_text = pair.split(",")
                float(lon_text), float(lat_text)
            polylines.append(polyline)
            point_count += len(pairs)
    if point_count < 2:
        raise RuntimeError("Amap path did not contain usable polyline geometry")
    return polylines, point_count


def main() -> None:
    itinerary = json.loads(ITINERARY.read_text(encoding="utf-8"))
    places = itinerary["places"]
    checked_at = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")
    routes: dict[str, dict] = {}

    for key, spec in itinerary["amap_route_specs"].items():
        point_keys = spec["points"]
        points = [places[point_key] for point_key in point_keys]
        path, request_url = request_route(points)
        roads = [road.get("road_name", "") for road in path.get("roads", [])]
        geometry, geometry_point_count = geometry_from_path(path)
        routes[key] = {
            "points": point_keys,
            "kind": spec["kind"],
            "strategy": path.get("strategy", "高德推荐方案"),
            "distance_m": int(path["distance"]),
            "duration_s": int(path["duration"]),
            "tolls_yuan": int(path.get("tolls") or 0),
            "traffic_lights": int(path.get("traffic_lights") or 0),
            "roads": [road for road in roads if road],
            "geometry": geometry,
            "geometry_point_count": geometry_point_count,
            "route_url": route_page_url(points),
            "request_url": request_url,
        }
        print(
            f'{key}: {routes[key]["distance_m"] / 1000:.1f} km, '
            f'{routes[key]["duration_s"] / 3600:.2f} h, '
            f'{routes[key]["geometry_point_count"]} geometry points'
        )

    snapshot = {
        "checked_at": checked_at,
        "source": "高德地图 PC 端路线规划",
        "source_url": "https://www.amap.com/ssr/doc/route-plan",
        "policy2": 10,
        "note": "保存高德当次推荐路线的原始折线、距离和预计时间；实时路况与临时管制仍以出发时高德为准。",
        "routes": routes,
    }
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LINKS.parent.mkdir(parents=True, exist_ok=True)
    LINKS.write_text(
        "\n".join(f'[amap-{key}]: <{route["route_url"]}>' for key, route in routes.items())
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
