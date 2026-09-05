#!/usr/bin/env python3
"""Offline consistency gate; never updates routes, files, or external services."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from build_fonts import font_characters, required_characters
from build_maps import map_input_digest
from update_amap_routes import generated_links, generated_variables, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_data(data: dict, snapshot: dict) -> None:
    require(data.get("coordinate_system") == "GCJ-02", "Wrong coordinate system")
    specs, routes, maps = data["amap_route_specs"], snapshot["routes"], data["maps"]
    require(set(specs) == set(routes), "Orphan/missing route snapshot")
    signatures = [(tuple(s["points"]), s["kind"]) for s in specs.values()]
    require(len(signatures) == len(set(signatures)), "Duplicate route specifications")
    used_places, used_routes, used_photos = set(), set(), set()
    place_roles = {"stay", "access", "photo", "optional", "reference"}
    for key, place in data["places"].items():
        require(place.get("role") in place_roles, f"{key}: missing/invalid place role")
    for key, point in data["photo_points"].items():
        require(point.get("visit") in {"planned", "optional", "replacement"}, f"{key}: missing/invalid photography visit status")
    for key, spec in specs.items():
        validate_snapshot(spec, routes[key], data["places"])
        used_places.update(spec["points"])
    for key, spec in maps.items():
        for label, role in spec.get("label_roles", {}).items():
            require(label in spec.get("labels", []), f"{key}: role override without label")
            require(role in place_roles, f"{key}: invalid role override")
        require(spec.get("context", "overview") in maps, f"{key}: missing context")
        if re.fullmatch("s0[1-8]", key):
            require(spec.get("context") == "skip_overview", f"{key}: wrong plan context")
        for route in spec["routes"]:
            used_places.update(route["points"])
            if route.get("draw", True):
                route_key = route["amap_route"]
                require(route_key in specs, f"{key}: missing route")
                require(route["points"] == specs[route_key]["points"] and route["kind"] == specs[route_key]["kind"], f"{key}: map route differs")
                used_routes.add(route_key)
        used_places.update(spec.get("labels", []))
        used_photos.update(spec.get("photos", []))
        require(set(spec.get("photo_labels", [])) <= set(spec.get("photos", [])), f"{key}: stray photo label")
    for day, options in data.get("route_options", {}).items():
        require(day in maps, f"Missing option day {day}")
        for key in options:
            require(key in specs, f"Missing alternative route {key}")
            require(specs[key]["points"][0] == maps[day]["routes"][0]["points"][0], "Alternative start differs")
            require(specs[key]["points"][-1] == maps[day]["routes"][-1]["points"][-1], "Alternative end differs")
            used_routes.add(key)
    require(used_places == set(data["places"]), f"Missing/unused places: {used_places ^ set(data['places'])}")
    require(used_routes == set(specs), "Unused route snapshot")
    require(used_photos == set(data["photo_points"]), "Missing/unused photography point")
    for prefix, overview in (("d", "overview"), ("s", "skip_overview")):
        previous = None
        daily_routes, photo_days = [], Counter()
        for n in range(1, 9):
            day = maps[f"{prefix}{n:02}"]
            photo_days.update(day.get("photos", []))
            for route in day["routes"]:
                require(previous is None or previous == route["points"][0], f"{prefix}{n}: discontinuous endpoint")
                previous = route["points"][-1]
                daily_routes.append(route)
        require(daily_routes == maps[overview]["routes"], f"{overview}: daily route drift")
        require(not any(v > 1 for v in photo_days.values()), "Undeclared repeated photography stop")
        require(set(photo_days) == set(maps[overview].get("photos", [])), f"{overview}: daily photo drift")
    for n in (1, 2, 3, 4, 7, 8):
        for field in ("routes", "labels", "photos", "photo_labels", "label_roles"):
            require(maps[f"d{n:02}"].get(field) == maps[f"s{n:02}"].get(field), f"Shared day {n}: {field} differs")


class Page(HTMLParser):
    def __init__(self, text: str):
        super().__init__()
        self.ids, self.links, self.scroll_regions = [], [], 0
        self.divs, self.table_count, self.unwrapped_tables = [], 0, 0
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "table-scroll" in attrs.get("class", "").split():
            self.scroll_regions += 1
        if tag == "div":
            self.divs.append("table-scroll" in attrs.get("class", "").split())
        if tag == "table":
            self.table_count += 1
            if not any(self.divs):
                self.unwrapped_tables += 1
        if tag in {"a", "link", "img", "script"}:
            self.links.append(attrs.get("href", attrs.get("src", "")))

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.divs:
            self.divs.pop()


def validate_site(site: Path) -> None:
    for stylesheet in site.rglob("*.css"):
        require("fonts.googleapis.com" not in stylesheet.read_text(), f"{stylesheet.name}: remote font dependency")
    pages = {p.name: Page(p.read_text()) for p in site.glob("*.html")}
    require(set(pages) == {"index.html", "primary.html", "option-skip-qiqian.html", "sources.html"}, "Rendered page set differs")
    for name, page in pages.items():
        require(len(page.ids) == len(set(page.ids)), f"{name}: duplicate fragment IDs")
        require(page.table_count > 0 and page.unwrapped_tables == 0, f"{name}: tables lack scroll wrappers")
        text = (site / name).read_text()
        require("{{<" not in text and not re.search(r"\]\[(?:amap|nav)-", text), f"{name}: unresolved shortcode/link")
        for url in page.links:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc:
                continue
            target = site / unquote(parsed.path) if parsed.path else site / name
            require(target.exists(), f"{name}: missing asset {url}")
            if parsed.fragment and target.name in pages:
                require(unquote(parsed.fragment) in pages[target.name].ids, f"{name}: missing anchor {url}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    data = json.loads((ROOT / "data/itinerary.json").read_text())
    snapshot = json.loads((ROOT / "data/amap-routes.json").read_text())
    validate_data(data, snapshot)
    require((ROOT / "includes/amap-route-links.md").read_text() == generated_links(data, snapshot), "Generated links stale")
    require((ROOT / "_variables.yml").read_text() == generated_variables(data, snapshot), "Generated metrics stale")
    variables = set(re.findall(r"^([\w-]+):", generated_variables(data, snapshot), re.M))
    definitions = set(re.findall(r"^\[([^]]+)\]:", generated_links(data, snapshot), re.M))
    for p in ROOT.glob("*.qmd"):
        text = p.read_text()
        require(set(re.findall(r"{{< var ([\w-]+) >}}", text)) <= variables, f"{p.name}: undefined metric")
        require(set(re.findall(r"\]\[((?:amap|nav)-[^]]+)\]", text)) <= definitions, f"{p.name}: undefined navigation link")
        require(not re.search(r"\d+\.\d+ 公里、(?:纯驾驶)?约 \d+ 小时", text), f"{p.name}: hard-coded navigation metrics")
        if p.name in {"primary.qmd", "option-skip-qiqian.qmd"}:
            require(text.count("| 时间 | 安排 | 对应高德导航点 |") == 8, f"{p.name}: daily table missing")
            require("五大连池清晨" not in text and "编号表示必经" not in text, f"{p.name}: stale wording")
    needed = required_characters(ROOT)
    fonts = list((ROOT / "assets/fonts/web").glob("*.woff2"))
    require({p.name for p in fonts} == {f"FandolHei-Roadbook-{weight}.woff2" for weight in ("Regular", "Bold")}, "Missing/extra web fonts")
    for font in fonts:
        require(needed <= font_characters(font), f"{font.name}: missing glyphs; run build_fonts.py")
    manifest = json.loads((ROOT / "figures/maps/manifest.json").read_text())
    require(set(manifest) == set(data["maps"]), "Map manifest has missing/extra maps")
    require({p.stem for p in (ROOT / "figures/maps").glob("*.webp")} == set(data["maps"]), "Missing/extra map images")
    signature = map_input_digest(ROOT)
    for key, record in manifest.items():
        require(record["inputs"] == signature, f"{key}: stale map inputs; rebuild maps")
        require(record["sha256"] == hashlib.sha256((ROOT / f"figures/maps/{key}.webp").read_bytes()).hexdigest(), f"{key}: map output altered")
    if args.site:
        validate_site(args.site.resolve())
    print(f"PASS: {len(snapshot['routes'])} routes, 16 days, 19 maps, generated links/metrics, fonts" + (", rendered HTML" if args.site else ""))


if __name__ == "__main__":
    main()
