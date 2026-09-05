#!/usr/bin/env python3
"""Build compact WebP roadbook maps with checked Amap route geometry.

OpenStreetMap provides the static basemap.  Every drawn road/transfer line comes
from the dated first-party Amap route snapshot in ``data/amap-routes.json``;
point sequences that are not public-road navigation (for example a park shuttle)
are shown only as labelled points and never joined by an invented line.
"""

from __future__ import annotations

import io
import hashlib
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from update_amap_routes import parse_geometry, validate_snapshot


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "itinerary.json"
AMAP_DATA = ROOT / "data" / "amap-routes.json"
OUTPUT = ROOT / "figures" / "maps"
CACHE = ROOT / "tmp" / "map_cache"
TILE_CACHE = CACHE / "tiles"

USER_AGENT = "DongbeiRoadbook/1.0 (personal trip map; contact: local-build)"
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

TARGET = (1260, 980)
OVERVIEW_TARGET = (1500, 930)
CONTEXT_TARGET = (390, 255)
TILE_SIZE = 256

COLORS = {
    "drive": "#B85335",
    "rail": "#2F6F73",
    "transfer": "#A47E25",
    "alternative": "#6D6B63",
    "ink": "#273128",
    "olive": "#5F693B",
    "paper": "#F5F0E4",
    "rust": "#B85335",
    "context_route": "#7E8978",
    "context_day": "#D45532",
    "photo": "#1677D2",
    "photo_pale": "#EAF4FF",
    "optional": "#7652A6",
    "optional_pale": "#F1EAFB",
}

GCJ_A = 6378245.0
GCJ_EE = 0.00669342162296594323


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "FandolHei-Bold.otf" if bold else "FandolHei-Regular.otf"
    path = ROOT / "assets" / "fonts" / "fandol" / filename
    if not path.exists():
        raise FileNotFoundError(f"Bundled map font not found: {path}")
    return ImageFont.truetype(str(path), size=size)


FONT_LABEL = load_font(27, bold=True)
FONT_SMALL = load_font(21)
FONT_TINY = load_font(16)
FONT_PIN = load_font(20, bold=True)
FONT_CONTEXT = load_font(17, bold=True)
FONT_CONTEXT_SMALL = load_font(15)
FONT_PHOTO = load_font(21, bold=True)


def lon_to_x(lon: float, zoom: int) -> float:
    return (lon + 180.0) / 360.0 * (2**zoom) * TILE_SIZE


def lat_to_y(lat: float, zoom: int) -> float:
    lat = max(min(lat, 85.05112878), -85.05112878)
    rad = math.radians(lat)
    return (1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * (2**zoom) * TILE_SIZE


def _gcj_delta(lon: float, lat: float) -> tuple[float, float]:
    x, y = lon - 105.0, lat - 35.0
    dlat = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    dlat += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    dlat += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    dlat += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    dlon = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    dlon += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    dlon += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    dlon += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    radlat = lat / 180.0 * math.pi
    magic = 1.0 - GCJ_EE * math.sin(radlat) ** 2
    sqrt_magic = math.sqrt(magic)
    return (
        dlon * 180.0 / (GCJ_A / sqrt_magic * math.cos(radlat) * math.pi),
        dlat * 180.0 / ((GCJ_A * (1.0 - GCJ_EE)) / (magic * sqrt_magic) * math.pi),
    )


def wgs84_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    dlon, dlat = _gcj_delta(lon, lat)
    return lon + dlon, lat + dlat


def gcj02_to_wgs84(lon: float, lat: float) -> tuple[float, float]:
    """Iteratively transform an Amap coordinate for the WGS84 OSM basemap."""
    wgs_lon, wgs_lat = lon, lat
    for _ in range(5):
        gcj_lon, gcj_lat = wgs84_to_gcj02(wgs_lon, wgs_lat)
        wgs_lon += lon - gcj_lon
        wgs_lat += lat - gcj_lat
    return wgs_lon, wgs_lat


def map_point(record: dict) -> tuple[float, float]:
    return gcj02_to_wgs84(float(record["lon"]), float(record["lat"]))


def choose_zoom(points: list[tuple[float, float]], target: tuple[int, int]) -> int:
    width, height = target
    for zoom in range(11, 3, -1):
        xs = [lon_to_x(lon, zoom) for lon, _ in points]
        ys = [lat_to_y(lat, zoom) for _, lat in points]
        if max(xs) - min(xs) <= width * 0.66 and max(ys) - min(ys) <= height * 0.64:
            return zoom
    return 4


def http_get(url: str, timeout: int = 25) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_tile(z: int, x: int, y: int) -> Image.Image:
    n = 2**z
    x = x % n
    y = max(0, min(y, n - 1))
    path = TILE_CACHE / str(z) / str(x) / f"{y}.png"
    if path.exists():
        try:
            return Image.open(path).convert("RGB")
        except OSError:
            pass

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = http_get(TILE_URL.format(z=z, x=x, y=y))
    tile = Image.open(io.BytesIO(payload)).convert("RGB")
    path.write_bytes(payload)
    time.sleep(0.08)
    return tile


def route_chunks(route: dict, amap_routes: dict) -> list[list[tuple[float, float]]]:
    """Preserve every Amap step boundary, including gaps between adjacent steps."""
    if route.get("draw", True) is False:
        return []
    route_key = route.get("amap_route")
    if not route_key:
        raise ValueError(f"Drawn route has no checked Amap snapshot: {route!r}")
    if route_key not in amap_routes:
        raise KeyError(f"Missing Amap snapshot: {route_key}")
    snapshot = amap_routes[route_key]
    if snapshot["points"] != route["points"]:
        raise ValueError(
            f"Amap snapshot {route_key} point sequence differs from itinerary: "
            f'{snapshot["points"]!r} != {route["points"]!r}'
        )
    if snapshot["kind"] != route["kind"]:
        raise ValueError(f"Amap snapshot {route_key} has the wrong route kind")
    chunks = parse_geometry(snapshot["geometry"])
    if sum(map(len, chunks)) != snapshot["geometry_point_count"]:
        raise ValueError(f"Amap snapshot {route_key} geometry point count changed")
    return [[gcj02_to_wgs84(*point) for point in chunk] for chunk in chunks]


def route_lonlat(route: dict, amap_routes: dict) -> list[tuple[float, float]]:
    """Flatten only for extent/label calculations, never for drawing lines."""
    return [point for chunk in route_chunks(route, amap_routes) for point in chunk]


def map_input_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for name in ("data/itinerary.json", "data/amap-routes.json", "scripts/build_maps.py",
                 "scripts/update_amap_routes.py", "requirements.txt",
                 "assets/fonts/fandol/FandolHei-Regular.otf", "assets/fonts/fandol/FandolHei-Bold.otf"):
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def line_segments(draw: ImageDraw.ImageDraw, xy: list[tuple[float, float]], kind: str) -> None:
    if len(xy) < 2:
        return
    color = COLORS[kind]
    width = 8 if kind == "drive" else 7
    if kind == "drive":
        draw.line(xy, fill="#FFF7EA", width=width + 5, joint="curve")
        draw.line(xy, fill=color, width=width, joint="curve")
        return
    dash = 18 if kind == "rail" else 10
    gap = 11 if kind == "rail" else 9
    for a, b in zip(xy, xy[1:]):
        x1, y1 = a
        x2, y2 = b
        length = math.hypot(x2 - x1, y2 - y1)
        if length == 0:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        cursor = 0.0
        while cursor < length:
            end = min(cursor + dash, length)
            draw.line(
                [(x1 + ux * cursor, y1 + uy * cursor), (x1 + ux * end, y1 + uy * end)],
                fill=color,
                width=width,
            )
            cursor += dash + gap


def label_box(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    index: int,
    canvas_width: int,
    canvas_height: int,
    occupied: list[tuple[float, float, float, float]],
    role: str = "stay",
) -> tuple[float, float, float, float]:
    optional, reference = role == "optional", role == "reference"
    radius = 7 if reference else 11 if role == "photo" else 17
    marker_color = "#777D78" if reference else COLORS["optional"] if optional else COLORS["photo"] if role == "photo" else COLORS["olive"]
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#FFFDF7" if optional else marker_color, outline=marker_color if optional else "#FFFDF7", width=3)
    index_text = str(index) if role in {"stay", "access"} else ""
    bbox = draw.textbbox((0, 0), index_text, font=FONT_PIN)
    draw.text((x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2 - 2), index_text, fill="white", font=FONT_PIN)

    text_bbox = draw.textbbox((0, 0), text, font=FONT_LABEL, stroke_width=1)
    tw = text_bbox[2] - text_bbox[0]
    th = text_bbox[3] - text_bbox[1]
    candidates = [
        (x + radius + 8, y - th / 2 - 4),
        (x - radius - tw - 18, y - th / 2 - 4),
        (x + radius + 8, y + radius + 6),
        (x - radius - tw - 18, y + radius + 6),
        (x + radius + 8, y - radius - th - 10),
        (x - radius - tw - 18, y - radius - th - 10),
        (x - tw / 2, y - radius - th - 12),
        (x - tw / 2, y + radius + 8),
    ]

    best: tuple[float, float, tuple[float, float, float, float]] | None = None
    best_score = float("inf")
    for raw_tx, raw_ty in candidates:
        tx = max(8.0, min(raw_tx, canvas_width - tw - 10.0))
        ty = max(8.0, min(raw_ty, canvas_height - th - 98.0))
        box = (tx - 6, ty - 3, tx + tw + 8, ty + th + 7)
        overlap = sum(boxes_overlap(box, other) for other in occupied)
        displacement = abs(tx - raw_tx) + abs(ty - raw_ty)
        score = overlap * 1000 + displacement
        if score < best_score:
            best_score = score
            best = (tx, ty, box)

    assert best is not None
    tx, ty, box = best
    # A displaced label must point back to its own location, especially in
    # dense overview maps where the nearest town label may belong elsewhere.
    anchor = (max(box[0], min(x, box[2])), max(box[1], min(y, box[3])))
    draw.line((x, y, *anchor), fill=(98, 105, 99, 180), width=2)
    box_fill = (241, 234, 251, 235) if optional else (250, 248, 240, 224)
    draw.rounded_rectangle(box, radius=6, fill=box_fill, outline=(255, 255, 255, 235), width=2)
    text_fill = "#626963" if reference else COLORS["optional"] if optional else COLORS["photo"] if role == "photo" else COLORS["ink"]
    draw.text((tx, ty), text, fill=text_fill, font=FONT_LABEL, stroke_width=1, stroke_fill="#FFFDF7")
    return box


def boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return width * height


def place_role(spec: dict, key: str, places: dict) -> str:
    """A supply candidate can be a required overnight base in another plan."""
    return spec.get("label_roles", {}).get(key, places[key]["role"])


def photo_marker(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    canvas_width: int,
    canvas_height: int,
    occupied: list[tuple[float, float, float, float]],
    show_label: bool = True,
    conditional: bool = False,
) -> None:
    """Blue is planned photography; purple is optional, independent of grade."""
    radius = 11
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill="#FFFDF7" if conditional else COLORS["photo"],
        outline=COLORS["optional"] if conditional else "#FFFDF7",
        width=4,
    )
    if not show_label:
        return

    text_bbox = draw.textbbox((0, 0), text, font=FONT_PHOTO, stroke_width=1)
    tw = text_bbox[2] - text_bbox[0]
    th = text_bbox[3] - text_bbox[1]
    candidates = [
        (x + 17, y - th - 17),
        (x + 17, y + 11),
        (x - tw - 27, y - th - 17),
        (x - tw - 27, y + 11),
        (x - tw / 2 - 5, y - th - 28),
        (x - tw / 2 - 5, y + 18),
    ]

    best: tuple[float, float, tuple[float, float, float, float]] | None = None
    best_score = float("inf")
    for tx, ty in candidates:
        box = (tx - 6, ty - 4, tx + tw + 8, ty + th + 7)
        overflow = (
            max(0.0, 8 - box[0])
            + max(0.0, 8 - box[1])
            + max(0.0, box[2] - canvas_width + 8)
            + max(0.0, box[3] - canvas_height + 94)
        )
        overlap = sum(boxes_overlap(box, other) for other in occupied)
        score = overflow * 10000 + overlap
        if score < best_score:
            best_score = score
            best = (tx, ty, box)

    assert best is not None
    tx, ty, box = best
    draw.rounded_rectangle(
        box,
        radius=7,
        fill=(241, 234, 251, 238) if conditional else (234, 244, 255, 238),
        outline=COLORS["optional"] if conditional else COLORS["photo"],
        width=2,
    )
    draw.text(
        (tx, ty),
        text,
        fill=COLORS["optional"] if conditional else "#0C5FAA",
        font=FONT_PHOTO,
        stroke_width=1,
        stroke_fill="#FFFFFF",
    )
    occupied.append(box)


def hazard_marker(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    canvas_width: int,
    canvas_height: int,
    occupied: list[tuple[float, float, float, float]],
) -> None:
    """Draw a warning marker with a label that avoids route labels."""
    tri = [(x, y - 20), (x - 19, y + 16), (x + 19, y + 16)]
    draw.polygon(tri, fill=COLORS["rust"], outline="#FFFDF7")

    bbox = draw.textbbox((0, 0), text, font=FONT_LABEL, stroke_width=2)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    candidates = [
        (x + 24, y - th / 2 - 3),
        (x - tw - 28, y - th / 2 - 3),
        (x - tw / 2, y + 24),
        (x - tw / 2, y - th - 28),
    ]

    best: tuple[float, float, tuple[float, float, float, float]] | None = None
    best_score = float("inf")
    for raw_tx, raw_ty in candidates:
        tx = max(8.0, min(raw_tx, canvas_width - tw - 10.0))
        ty = max(8.0, min(raw_ty, canvas_height - th - 98.0))
        hazard_box = (tx - 5, ty - 3, tx + tw + 7, ty + th + 6)
        overlap = sum(boxes_overlap(hazard_box, other) for other in occupied)
        displacement = abs(tx - raw_tx) + abs(ty - raw_ty)
        score = overlap * 1000 + displacement
        if score < best_score:
            best_score = score
            best = (tx, ty, hazard_box)

    assert best is not None
    tx, ty, hazard_box = best
    draw.text((tx, ty), text, fill=COLORS["rust"], font=FONT_LABEL, stroke_width=2, stroke_fill="#FFFDF7")
    occupied.extend([hazard_box, (x - 21, y - 22, x + 21, y + 18)])


def build_context_inset(
    key: str,
    spec: dict,
    places: dict,
    photo_points: dict,
    overview_spec: dict,
    amap_routes: dict,
) -> Image.Image:
    """Build a fixed-scale whole-trip locator with the current day highlighted."""
    target = CONTEXT_TARGET
    full_routes = overview_spec["routes"]
    full_points = [point for route in full_routes for point in route_lonlat(route, amap_routes)]

    zoom = choose_zoom(full_points, target)
    px = [lon_to_x(lon, zoom) for lon, _ in full_points]
    py = [lat_to_y(lat, zoom) for _, lat in full_points]
    x_span = max(px) - min(px)
    y_span = max(py) - min(py)
    left = min(px) - max(24, x_span * 0.12)
    right = max(px) + max(24, x_span * 0.12)
    top = min(py) - max(20, y_span * 0.13)
    bottom = max(py) + max(20, y_span * 0.13)

    crop_w, crop_h = right - left, bottom - top
    wanted_ratio = target[0] / target[1]
    if crop_w / crop_h < wanted_ratio:
        extra = crop_h * wanted_ratio - crop_w
        left -= extra / 2
        right += extra / 2
    else:
        extra = crop_w / wanted_ratio - crop_h
        top -= extra / 2
        bottom += extra / 2

    tx0, tx1 = math.floor(left / TILE_SIZE), math.floor(right / TILE_SIZE)
    ty0, ty1 = math.floor(top / TILE_SIZE), math.floor(bottom / TILE_SIZE)
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE_SIZE, (ty1 - ty0 + 1) * TILE_SIZE), "#DDD8CA")
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            canvas.paste(fetch_tile(zoom, tx, ty), ((tx - tx0) * TILE_SIZE, (ty - ty0) * TILE_SIZE))

    crop_box = (
        int(left - tx0 * TILE_SIZE),
        int(top - ty0 * TILE_SIZE),
        int(right - tx0 * TILE_SIZE),
        int(bottom - ty0 * TILE_SIZE),
    )
    inset = canvas.crop(crop_box).resize(target, Image.Resampling.LANCZOS).convert("RGBA")
    inset = Image.alpha_composite(inset, Image.new("RGBA", target, (247, 243, 232, 118)))
    draw = ImageDraw.Draw(inset, "RGBA")
    sx = target[0] / (right - left)
    sy = target[1] / (bottom - top)

    def project(lon: float, lat: float) -> tuple[float, float]:
        return ((lon_to_x(lon, zoom) - left) * sx, (lat_to_y(lat, zoom) - top) * sy)

    for route in full_routes:
        for chunk in route_chunks(route, amap_routes):
            line = [project(lon, lat) for lon, lat in chunk]
            if len(line) >= 2:
                draw.line(line, fill="#FFFDF7", width=9, joint="curve")
                draw.line(line, fill=COLORS["context_route"], width=5, joint="curve")

    daily_routes = [route for route in spec["routes"] if route["kind"] != "alternative"]
    for route in daily_routes:
        for chunk in route_chunks(route, amap_routes):
            segment = [project(lon, lat) for lon, lat in chunk]
            if len(segment) >= 2:
                draw.line(segment, fill="#FFFDF7", width=12, joint="curve")
                draw.line(segment, fill=COLORS["context_day"], width=8, joint="curve")
        line = [project(lon, lat) for lon, lat in route_lonlat(route, amap_routes)]
        if len(line) < 2:
            continue
        for endpoint in (line[0], line[-1]):
            x, y = endpoint
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=COLORS["context_day"], outline="#FFFDF7", width=2)

    for photo_key in spec.get("photos", []):
        photo = photo_points[photo_key]
        x, y = project(*map_point(photo))
        conditional = photo["visit"] != "planned"
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#FFFDF7" if conditional else COLORS["photo"], outline=COLORS["optional"] if conditional else "#FFFDF7", width=1)

    badge = spec.get("badge", f"{key.upper()} / 8")
    badge_bbox = draw.textbbox((0, 0), badge, font=FONT_CONTEXT)
    badge_width = badge_bbox[2] - badge_bbox[0] + 20
    draw.rounded_rectangle((8, 8, 8 + badge_width, 36), radius=6, fill=(250, 248, 240, 232), outline=(95, 105, 59, 150), width=1)
    draw.text((18, 10), badge, fill=COLORS["ink"], font=FONT_CONTEXT)

    legend_y = target[1] - 28
    draw.rounded_rectangle((8, legend_y - 6, 193, target[1] - 5), radius=6, fill=(250, 248, 240, 232))
    draw.line((18, legend_y + 5, 46, legend_y + 5), fill=COLORS["context_route"], width=5)
    draw.text((52, legend_y - 5), "全程", fill=COLORS["ink"], font=FONT_CONTEXT_SMALL)
    draw.line((103, legend_y + 5, 131, legend_y + 5), fill=COLORS["context_day"], width=7)
    draw.text((137, legend_y - 5), "当日", fill=COLORS["ink"], font=FONT_CONTEXT_SMALL)
    draw.rounded_rectangle((1, 1, target[0] - 2, target[1] - 2), radius=10, outline=(95, 105, 59, 210), width=3)
    return inset


def place_context_inset(image: Image.Image, inset: Image.Image, route_points: list[tuple[float, float]]) -> None:
    """Place the locator in the least occupied corner of the daily map."""
    width, height = image.size
    inset_w, inset_h = inset.size
    candidates = [
        (18, 18),
        (width - inset_w - 18, 18),
        (18, height - inset_h - 108),
        (width - inset_w - 18, height - inset_h - 64),
    ]

    def score(candidate: tuple[int, int]) -> float:
        x0, y0 = candidate
        x1, y1 = x0 + inset_w, y0 + inset_h
        total = 0.0
        for x, y in route_points:
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - y, 0, y - y1)
            distance = math.hypot(dx, dy)
            total += max(0.0, 150.0 - distance)
        return total

    x, y = min(candidates, key=score)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow, "RGBA")
    shadow_draw.rounded_rectangle((x + 5, y + 6, x + inset_w + 5, y + inset_h + 6), radius=12, fill=(39, 49, 40, 48))
    image.alpha_composite(shadow)
    image.alpha_composite(inset, (x, y))


def build_map(
    key: str,
    spec: dict,
    places: dict,
    photo_points: dict,
    output: Path,
    overview_spec: dict,
    amap_routes: dict,
    checked_date: str,
) -> None:
    target = OVERVIEW_TARGET if key in {"overview", "risk"} or spec.get("layout") == "overview" else TARGET
    point_keys: list[str] = []
    for route in spec["routes"]:
        point_keys.extend(route["points"])
    points = [map_point(places[p]) for p in dict.fromkeys(point_keys)]
    points.extend(point for route in spec["routes"] for point in route_lonlat(route, amap_routes))
    for hazard in spec.get("hazards", []):
        points.append(map_point(hazard))
    for photo_key in spec.get("photos", []):
        photo = photo_points[photo_key]
        points.append(map_point(photo))

    zoom = choose_zoom(points, target)
    px = [lon_to_x(lon, zoom) for lon, _ in points]
    py = [lat_to_y(lat, zoom) for _, lat in points]
    x_span = max(max(px) - min(px), target[0] * 0.35)
    y_span = max(max(py) - min(py), target[1] * 0.35)
    x_pad = max(120, x_span * 0.20)
    y_pad = max(110, y_span * 0.24)
    left = min(px) - x_pad
    right = max(px) + x_pad
    top = min(py) - y_pad
    bottom = max(py) + y_pad

    # Adjust the crop to the output aspect ratio without distorting the map.
    crop_w, crop_h = right - left, bottom - top
    wanted_ratio = target[0] / target[1]
    if crop_w / crop_h < wanted_ratio:
        extra = crop_h * wanted_ratio - crop_w
        left -= extra / 2
        right += extra / 2
    else:
        extra = crop_w / wanted_ratio - crop_h
        top -= extra / 2
        bottom += extra / 2

    tx0, tx1 = math.floor(left / TILE_SIZE), math.floor(right / TILE_SIZE)
    ty0, ty1 = math.floor(top / TILE_SIZE), math.floor(bottom / TILE_SIZE)
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE_SIZE, (ty1 - ty0 + 1) * TILE_SIZE), "#DDD8CA")
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            tile = fetch_tile(zoom, tx, ty)
            canvas.paste(tile, ((tx - tx0) * TILE_SIZE, (ty - ty0) * TILE_SIZE))

    crop_box = (
        int(left - tx0 * TILE_SIZE),
        int(top - ty0 * TILE_SIZE),
        int(right - tx0 * TILE_SIZE),
        int(bottom - ty0 * TILE_SIZE),
    )
    image = canvas.crop(crop_box).resize(target, Image.Resampling.LANCZOS).convert("RGBA")
    veil = Image.new("RGBA", image.size, (247, 243, 232, 28))
    image = Image.alpha_composite(image, veil)
    draw = ImageDraw.Draw(image, "RGBA")

    sx = target[0] / (right - left)
    sy = target[1] / (bottom - top)

    def project(lon: float, lat: float) -> tuple[float, float]:
        return ((lon_to_x(lon, zoom) - left) * sx, (lat_to_y(lat, zoom) - top) * sy)

    # Rail/alternatives underneath, driving routes on top.
    ordered_routes = sorted(spec["routes"], key=lambda r: 1 if r["kind"] == "drive" else 0)
    for route in ordered_routes:
        for chunk in route_chunks(route, amap_routes):
            geometry = [project(lon, lat) for lon, lat in chunk]
            line_segments(draw, geometry, route["kind"])

    # Reserve every marker before placing labels; later photo pins must not
    # overwrite earlier town/hotel labels in dense areas such as Arxan.
    occupied: list[tuple[float, float, float, float]] = []
    logistics_pins = [project(*map_point(places[k])) for k in spec.get("labels", [])
                      if place_role(spec, k, places) in {"stay", "access"}]
    photo_positions = {}
    for photo_key in spec.get("photos", []):
        photo = photo_points[photo_key]
        x, y = project(*map_point(photo))
        labelled_photo = any(place_role(spec, k, places) == "photo" and
                             map_point(places[k]) == map_point(photo)
                             for k in spec.get("labels", []))
        if not labelled_photo and any(math.hypot(x - px, y - py) < 28 for px, py in logistics_pins):
            draw.line((x, y, x + 32, y + 28), fill="#777D78", width=2)
            x, y = x + 32, y + 28
        photo_positions[photo_key] = (x, y)
        occupied.append((x - 14, y - 14, x + 14, y + 14))
    for hazard in spec.get("hazards", []):
        x, y = project(*map_point(hazard))
        occupied.append((x - 25, y - 25, x + 25, y + 25))
    for place_key in spec.get("labels", []):
        x, y = project(*map_point(places[place_key]))
        occupied.append((x - 20, y - 20, x + 20, y + 20))
    i = 0
    photo_labels = set(spec.get("photo_labels", spec.get("photos", [])))
    for place_key in spec.get("labels", []):
        p = places[place_key]
        role = place_role(spec, place_key, places)
        if role == "photo" and any(map_point(p) == map_point(photo_points[k]) for k in photo_labels):
            continue
        if role in {"stay", "access"}:
            i += 1
        suffix = {"stay": "·住宿", "access": "·换乘/入口", "optional": "·选停"}.get(role, "")
        occupied.append(
            label_box(
                draw,
                *project(*map_point(p)),
                p["short"] + suffix,
                i,
                target[0],
                target[1],
                occupied,
                role=role,
            )
        )

    for photo_key in spec.get("photos", []):
        photo = photo_points[photo_key]
        x, y = photo_positions[photo_key]
        photo_marker(
            draw,
            x, y,
            photo["short"],
            target[0],
            target[1],
            occupied,
            show_label=photo_key in photo_labels,
            conditional=photo["visit"] != "planned",
        )

    for hazard in spec.get("hazards", []):
        x, y = project(*map_point(hazard))
        hazard_marker(draw, x, y, hazard["label"], target[0], target[1], occupied)

    if spec.get("context") or key.startswith("d"):
        daily_route_points: list[tuple[float, float]] = []
        for route in spec["routes"]:
            if route["kind"] != "alternative":
                daily_route_points.extend(
                    project(lon, lat) for lon, lat in route_lonlat(route, amap_routes)
                )
        daily_route_points.extend(
            project(*map_point(photo_points[p]))
            for p in spec.get("photos", [])
        )
        place_context_inset(
            image,
            build_context_inset(key, spec, places, photo_points, overview_spec, amap_routes),
            daily_route_points,
        )
        draw = ImageDraw.Draw(image, "RGBA")

    # Compact legend and attribution; route timings remain in the roadbook text.
    legend_items = []
    kinds = {route["kind"] for route in spec["routes"] if route.get("draw", True)}
    for kind, label in (("drive", "自驾"), ("rail", "铁路"), ("transfer", "接驳"), ("alternative", "备选")):
        if kind in kinds:
            legend_items.append((kind, label))
    legend_x, legend_y = 20, target[1] - 76
    roles = {place_role(spec, key, places) for key in spec.get("labels", [])}
    has_optional = "optional" in roles or any(photo_points[key]["visit"] != "planned" for key in spec.get("photos", []))
    has_planned = "photo" in roles or any(photo_points[key]["visit"] == "planned" for key in spec.get("photos", []))
    has_reference = "reference" in roles
    has_logistics = bool(roles & {"stay", "access"})
    legend_w = 92 * len(legend_items) + (116 if has_planned else 0) + (170 if has_optional else 0) + (116 if has_reference else 0) + (170 if has_logistics else 0) + 24
    draw.rounded_rectangle((12, target[1] - 92, 12 + legend_w, target[1] - 16), radius=10, fill=(250, 248, 240, 228), outline=(95, 105, 59, 170), width=2)
    for kind, label in legend_items:
        draw.line((legend_x, legend_y + 10, legend_x + 32, legend_y + 10), fill=COLORS[kind], width=6)
        draw.text((legend_x + 39, legend_y - 4), label, fill=COLORS["ink"], font=FONT_SMALL)
        legend_x += 92
    if has_planned:
        draw.ellipse((legend_x, legend_y + 1, legend_x + 18, legend_y + 19), fill=COLORS["photo"], outline="#FFFDF7", width=2)
        draw.text((legend_x + 27, legend_y - 4), "主拍点", fill=COLORS["ink"], font=FONT_SMALL)
        legend_x += 116
    if has_optional:
        draw.ellipse((legend_x, legend_y + 1, legend_x + 18, legend_y + 19), fill="#FFFDF7", outline=COLORS["optional"], width=3)
        draw.text((legend_x + 27, legend_y - 4), "选停/备选", fill=COLORS["optional"], font=FONT_SMALL)
        legend_x += 170
    if has_logistics:
        draw.ellipse((legend_x, legend_y + 1, legend_x + 18, legend_y + 19), fill=COLORS["olive"], outline="#FFFDF7", width=2)
        draw.text((legend_x + 27, legend_y - 4), "住宿/换乘", fill=COLORS["ink"], font=FONT_SMALL)
        legend_x += 170
    if has_reference:
        draw.ellipse((legend_x + 3, legend_y + 4, legend_x + 15, legend_y + 16), fill="#777D78", outline="#FFFDF7", width=1)
        draw.text((legend_x + 27, legend_y - 4), "参照点", fill=COLORS["ink"], font=FONT_SMALL)
        legend_x += 116

    credit = f"© OpenStreetMap contributors · 线路：高德推荐方案（核验 {checked_date}）"
    bbox = draw.textbbox((0, 0), credit, font=FONT_TINY)
    cw = bbox[2] - bbox[0]
    draw.rounded_rectangle((target[0] - cw - 26, target[1] - 42, target[0] - 10, target[1] - 10), radius=5, fill=(250, 248, 240, 220))
    draw.text((target[0] - cw - 18, target[1] - 39), credit, fill=(39, 49, 40, 220), font=FONT_TINY)

    output.mkdir(parents=True, exist_ok=True)
    out = output / f"{key}.webp"
    image.convert("RGB").save(out, format="WEBP", quality=86, method=6)
    print(f"{key}: z{zoom} -> {out.relative_to(ROOT)}")


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    if data.get("coordinate_system") != "GCJ-02":
        raise ValueError("itinerary coordinates must declare GCJ-02 for Amap/OSM reprojection")
    amap_data = json.loads(AMAP_DATA.read_text(encoding="utf-8"))
    amap_routes = amap_data["routes"]
    for key, spec in data["amap_route_specs"].items():
        validate_snapshot(spec, amap_routes[key], data["places"])
    checked_date = amap_data["checked_at"][:10]
    requested = sys.argv[1:]
    unknown = [key for key in requested if key not in data["maps"]]
    if unknown:
        raise SystemExit(f"Unknown map key(s): {', '.join(unknown)}")
    keys = requested or list(data["maps"])
    manifest_path = OUTPUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    signature = map_input_digest(ROOT)
    for key in keys:
        spec = data["maps"][key]
        context_key = spec.get("context", "overview")
        overview_spec = data["maps"][context_key]
        build_map(
            key,
            spec,
            data["places"],
            data["photo_points"],
            OUTPUT,
            overview_spec,
            amap_routes,
            checked_date,
        )
        manifest[key] = {"inputs": signature, "sha256": hashlib.sha256((OUTPUT / f"{key}.webp").read_bytes()).hexdigest()}
    manifest = {key: value for key, value in manifest.items() if key in data["maps"]}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
