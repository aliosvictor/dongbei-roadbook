#!/usr/bin/env python3
"""Refresh the checked Amap road-route snapshots used by the static maps.

The endpoint is the first-party JSON route endpoint used by Amap's current PC
route-planning page.  The generated file is a dated snapshot: driving times and
recommended paths must still be refreshed before departure.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ITINERARY = ROOT / "data" / "itinerary.json"
OUTPUT = ROOT / "data" / "amap-routes.json"
LINKS = ROOT / "includes" / "amap-route-links.md"
VARIABLES = ROOT / "_variables.yml"
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
    data = payload.get("data") or {}
    route = data.get("route") or {}
    paths = route.get("paths", [])
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
            polylines.append(polyline)
            point_count += len(parse_geometry([polyline])[0])
    if point_count < 2:
        raise RuntimeError("Amap path did not contain usable polyline geometry")
    return polylines, point_count


def parse_geometry(polylines: list[str]) -> list[list[tuple[float, float]]]:
    """Keep step boundaries: missing road geometry must never become a connector."""
    chunks = []
    for polyline in polylines:
        chunk = []
        for pair in polyline.split(";"):
            if not pair:
                continue
            lon, lat = map(float, pair.split(","))
            if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError(f"Invalid route coordinate: {pair}")
            chunk.append((lon, lat))
        if not chunk:
            raise ValueError("Empty route geometry step")
        chunks.append(chunk)
    if not chunks:
        raise ValueError("Empty route geometry")
    return chunks


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance for two GCJ-02 lon/lat pairs."""
    lon1, lat1 = a
    lon2, lat2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    term = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, term))))


def validate_route_points(points: list[dict], polylines: list[str]) -> list[int]:
    """Check start/end and an ordered traversal, including legitimate return trips."""
    geometry = [p for chunk in parse_geometry(polylines) for p in chunk]
    if len(points) < 2 or len(geometry) < 2:
        raise ValueError("A route needs at least two points")
    snap_distances: list[int] = []
    cursor = 0
    for index, point in enumerate(points):
        requested = (point["lon"], point["lat"])
        distances = [distance_m(requested, candidate) for candidate in geometry]
        nearest = round(min(distances))
        tolerance = point.get("route_snap_tolerance_m", 600)
        if index == 0:
            candidates = [0] if distances[0] <= tolerance else []
        elif index == len(points) - 1:
            candidates = [len(geometry) - 1] if distances[-1] <= tolerance else []
        else:
            candidates = [i for i in range(cursor, len(geometry)) if distances[i] <= tolerance]
        if not candidates:
            raise RuntimeError(
                f'Amap geometry missed ordered point {point["name"]!r}: '
                f"nearest vertex {nearest} m; tolerance {tolerance} m; cursor {cursor}"
            )
        cursor = candidates[0]
        snap_distances.append(nearest)
    return snap_distances


def validate_snapshot(spec: dict, snapshot: dict, places: dict) -> None:
    points = [places[key] for key in spec["points"]]
    if snapshot["points"] != spec["points"] or snapshot["kind"] != spec["kind"]:
        raise ValueError("Snapshot route points/kind differ from itinerary")
    if snapshot.get("point_coordinates") != [[p["lon"], p["lat"]] for p in points]:
        raise ValueError("Snapshot coordinates are stale; refresh Amap routes")
    if snapshot["route_url"] != route_page_url(points):
        raise ValueError("Snapshot navigation link differs from itinerary")
    chunks = parse_geometry(snapshot["geometry"])
    if sum(map(len, chunks)) != snapshot["geometry_point_count"]:
        raise ValueError("Snapshot geometry count mismatch")
    if validate_route_points(points, snapshot["geometry"]) != snapshot["point_snap_distances_m"]:
        raise ValueError("Snapshot point-distance check mismatch")


def generated_links(itinerary: dict, snapshot: dict) -> str:
    lines = [f'[amap-{key}]: <{route["route_url"]}>' for key, route in snapshot["routes"].items()]
    lines.extend(f'[nav-{key}]: <{point["url"]}>' for key, point in itinerary.get("navigation_points", {}).items())
    return "\n".join(lines) + "\n"


def generated_variables(itinerary: dict, snapshot: dict) -> str:
    """Quarto variables keep every repeated distance, duration and check date in sync."""
    values = {"route-checked": snapshot["checked_at"][:10]}
    groups = {key: [key] for key in snapshot["routes"]}
    for key, spec in itinerary["maps"].items():
        groups[key] = [r["amap_route"] for r in spec["routes"] if r.get("draw", True)]
    for key, route_keys in groups.items():
        distance = sum(snapshot["routes"][k]["distance_m"] for k in route_keys)
        minutes = round(sum(snapshot["routes"][k]["duration_s"] for k in route_keys) / 60)
        values[f"{key}-km"] = f"{distance / 1000:.1f}"
        values[f"{key}-time"] = f"{minutes // 60} 小时 {minutes % 60:02d} 分"
    return "# Generated by scripts/update_amap_routes.py; do not hand-edit.\n" + "".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in values.items()
    )


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
        point_snap_distances_m = validate_route_points(points, geometry)
        routes[key] = {
            "points": point_keys,
            "point_coordinates": [[p["lon"], p["lat"]] for p in points],
            "kind": spec["kind"],
            "strategy": path.get("strategy", "高德推荐方案"),
            "distance_m": int(path["distance"]),
            "duration_s": int(path["duration"]),
            "tolls_yuan": int(path.get("tolls") or 0),
            "traffic_lights": int(path.get("traffic_lights") or 0),
            "roads": [road for road in roads if road],
            "geometry": geometry,
            "geometry_point_count": geometry_point_count,
            "point_snap_distances_m": point_snap_distances_m,
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
    for key, route in routes.items():
        validate_snapshot(itinerary["amap_route_specs"][key], route, places)
    variables = generated_variables(itinerary, snapshot)
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LINKS.parent.mkdir(parents=True, exist_ok=True)
    LINKS.write_text(generated_links(itinerary, snapshot), encoding="utf-8")
    VARIABLES.write_text(variables, encoding="utf-8")


if __name__ == "__main__":
    main()
