#!/usr/bin/env python3
"""Build bounded OSM-based schematic maps for the final travel roadbook.

Route lines pass through locally stored control points. OSM tiles are cached so
later builds retain the same basemap and avoid repeated downloads.
"""

from __future__ import annotations

import io
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "itinerary.json"
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
}


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


def smooth_polyline(xy: list[tuple[float, float]], samples: int = 12) -> list[tuple[float, float]]:
    """Round a local schematic through its explicit control points.

    This is not road routing: it keeps all processing local and makes that
    limitation visible in the map attribution.
    """
    if len(xy) < 3:
        return xy
    padded = [xy[0], *xy, xy[-1]]
    result: list[tuple[float, float]] = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for step in range(samples):
            t = step / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2*p0[0] - 5*p1[0] + 4*p2[0] - p3[0]) * t2 + (-p0[0] + 3*p1[0] - 3*p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2*p0[1] - 5*p1[1] + 4*p2[1] - p3[1]) * t2 + (-p0[1] + 3*p1[1] - 3*p2[1] + p3[1]) * t3)
            result.append((x, y))
    result.append(xy[-1])
    return result


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
) -> tuple[float, float, float, float]:
    radius = 17
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=COLORS["olive"], outline="#FFFDF7", width=3)
    index_text = str(index)
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
    draw.rounded_rectangle(box, radius=6, fill=(250, 248, 240, 224), outline=(255, 255, 255, 235), width=2)
    draw.text((tx, ty), text, fill=COLORS["ink"], font=FONT_LABEL, stroke_width=1, stroke_fill="#FFFDF7")
    return box


def boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return width * height


def photo_marker(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    canvas_width: int,
    canvas_height: int,
    occupied: list[tuple[float, float, float, float]],
    show_label: bool = True,
) -> None:
    """Draw a blue photography pin and place its label away from existing labels."""
    radius = 11
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=COLORS["photo"],
        outline="#FFFDF7",
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
        fill=(234, 244, 255, 238),
        outline=COLORS["photo"],
        width=2,
    )
    draw.text(
        (tx, ty),
        text,
        fill="#0C5FAA",
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


def build_context_inset(key: str, spec: dict, places: dict, photo_points: dict, overview_spec: dict) -> Image.Image:
    """Build a fixed-scale whole-trip locator with the current day highlighted."""
    target = CONTEXT_TARGET
    full_routes = overview_spec["routes"]
    full_keys: list[str] = []
    for route in full_routes:
        full_keys.extend(route["points"])
    full_points = [(places[p]["lon"], places[p]["lat"]) for p in dict.fromkeys(full_keys)]

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
        raw = [places[p] for p in route["points"]]
        line = smooth_polyline([project(p["lon"], p["lat"]) for p in raw], samples=8)
        draw.line(line, fill="#FFFDF7", width=9, joint="curve")
        draw.line(line, fill=COLORS["context_route"], width=5, joint="curve")

    daily_routes = [route for route in spec["routes"] if route["kind"] != "alternative"]
    for route in daily_routes:
        raw = [places[p] for p in route["points"]]
        line = smooth_polyline([project(p["lon"], p["lat"]) for p in raw], samples=8)
        draw.line(line, fill="#FFFDF7", width=12, joint="curve")
        draw.line(line, fill=COLORS["context_day"], width=8, joint="curve")
        for endpoint in (line[0], line[-1]):
            x, y = endpoint
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=COLORS["context_day"], outline="#FFFDF7", width=2)

    for photo_key in spec.get("photos", []):
        photo = photo_points[photo_key]
        x, y = project(photo["lon"], photo["lat"])
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=COLORS["photo"], outline="#FFFDF7", width=1)

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


def build_map(key: str, spec: dict, places: dict, photo_points: dict, output: Path, overview_spec: dict) -> None:
    target = OVERVIEW_TARGET if key in {"overview", "risk"} or spec.get("layout") == "overview" else TARGET
    point_keys: list[str] = []
    for route in spec["routes"]:
        point_keys.extend(route["points"])
    points = [(places[p]["lon"], places[p]["lat"]) for p in dict.fromkeys(point_keys)]
    for hazard in spec.get("hazards", []):
        points.append((hazard["lon"], hazard["lat"]))
    for photo_key in spec.get("photos", []):
        photo = photo_points[photo_key]
        points.append((photo["lon"], photo["lat"]))

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
        raw = [places[p] for p in route["points"]]
        control_line = [project(p["lon"], p["lat"]) for p in raw]
        geometry = smooth_polyline(control_line) if route["kind"] == "drive" else control_line
        line_segments(draw, geometry, route["kind"])

    occupied: list[tuple[float, float, float, float]] = []
    for i, place_key in enumerate(spec.get("labels", []), start=1):
        p = places[place_key]
        occupied.append(
            label_box(
                draw,
                *project(p["lon"], p["lat"]),
                p["short"],
                i,
                target[0],
                target[1],
                occupied,
            )
        )

    photo_labels = set(spec.get("photo_labels", spec.get("photos", [])))
    for photo_key in spec.get("photos", []):
        photo = photo_points[photo_key]
        photo_marker(
            draw,
            *project(photo["lon"], photo["lat"]),
            photo["short"],
            target[0],
            target[1],
            occupied,
            show_label=photo_key in photo_labels,
        )

    for hazard in spec.get("hazards", []):
        x, y = project(hazard["lon"], hazard["lat"])
        hazard_marker(draw, x, y, hazard["label"], target[0], target[1], occupied)

    if spec.get("context") or key.startswith("d"):
        daily_route_points: list[tuple[float, float]] = []
        for route in spec["routes"]:
            if route["kind"] != "alternative":
                daily_route_points.extend(project(places[p]["lon"], places[p]["lat"]) for p in route["points"])
        daily_route_points.extend(
            project(photo_points[p]["lon"], photo_points[p]["lat"])
            for p in spec.get("photos", [])
        )
        place_context_inset(
            image,
            build_context_inset(key, spec, places, photo_points, overview_spec),
            daily_route_points,
        )
        draw = ImageDraw.Draw(image, "RGBA")

    # Compact legend and attribution; route timings remain in the roadbook text.
    legend_items = []
    kinds = {route["kind"] for route in spec["routes"]}
    for kind, label in (("drive", "自驾"), ("rail", "铁路"), ("transfer", "接驳"), ("alternative", "备选")):
        if kind in kinds:
            legend_items.append((kind, label))
    legend_x, legend_y = 20, target[1] - 76
    legend_w = 92 * len(legend_items) + (116 if spec.get("photos") else 0) + 24
    draw.rounded_rectangle((12, target[1] - 92, 12 + legend_w, target[1] - 16), radius=10, fill=(250, 248, 240, 228), outline=(95, 105, 59, 170), width=2)
    for kind, label in legend_items:
        draw.line((legend_x, legend_y + 10, legend_x + 32, legend_y + 10), fill=COLORS[kind], width=6)
        draw.text((legend_x + 39, legend_y - 4), label, fill=COLORS["ink"], font=FONT_SMALL)
        legend_x += 92
    if spec.get("photos"):
        draw.ellipse((legend_x, legend_y + 1, legend_x + 18, legend_y + 19), fill=COLORS["photo"], outline="#FFFDF7", width=2)
        draw.text((legend_x + 27, legend_y - 4), "拍摄点", fill=COLORS["ink"], font=FONT_SMALL)

    credit = "© OpenStreetMap contributors · 路线示意，实时导航与交通管制优先"
    bbox = draw.textbbox((0, 0), credit, font=FONT_TINY)
    cw = bbox[2] - bbox[0]
    draw.rounded_rectangle((target[0] - cw - 26, target[1] - 42, target[0] - 10, target[1] - 10), radius=5, fill=(250, 248, 240, 220))
    draw.text((target[0] - cw - 18, target[1] - 39), credit, fill=(39, 49, 40, 220), font=FONT_TINY)

    output.mkdir(parents=True, exist_ok=True)
    out = output / f"{key}.png"
    image.convert("RGB").save(out, quality=94, optimize=True)
    print(f"{key}: z{zoom} -> {out.relative_to(ROOT)}")


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    requested = sys.argv[1:]
    unknown = [key for key in requested if key not in data["maps"]]
    if unknown:
        raise SystemExit(f"Unknown map key(s): {', '.join(unknown)}")
    keys = requested or list(data["maps"])
    for key in keys:
        spec = data["maps"][key]
        context_key = spec.get("context", "overview")
        overview_spec = data["maps"][context_key]
        build_map(key, spec, data["places"], data["photo_points"], OUTPUT, overview_spec)


if __name__ == "__main__":
    main()
