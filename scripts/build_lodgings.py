#!/usr/bin/env python3
"""Generate main-plan lodging table/links from user-supplied nights and cited listings."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bd09_to_gcj02(lon, lat):
    # Baidu BD-09 adds a second offset to GCJ-02; never feed BD-09 to Amap.
    x, y = lon - 0.0065, lat - 0.006
    factor = math.pi * 3000 / 180
    z = math.hypot(x, y) - 0.00002 * math.sin(y * factor)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * factor)
    return round(z * math.cos(theta), 6), round(z * math.sin(theta), 6)


def generated_lodgings(data):
    rows = [
        "| 入住 → 退房（2026） | 住宿 / 高德搜索 | 地址与公开资料 |",
        "|---|---|---|",
    ]
    links = []
    for stay in data["stays"]:
        key = stay["id"]
        dates = stay["check_in"][5:].replace("-", ".") + " → " + stay["check_out"][5:].replace("-", ".")
        link = f'[{stay["name"]}][stay-{key}]{{data-stop-role="logistics" data-lodging="{key}"}}'
        rows.append(f'| {dates} | {link} | {stay["city"]} · {stay["address"]}（[资料]({stay["source_url"]})） |')
        links.append(f'[stay-{key}]: <{stay["amap_url"]}>')
    return "\n".join(rows) + "\n", "\n".join(links) + "\n"


def main():
    data = json.loads((ROOT / "data/lodgings.json").read_text())
    table, links = generated_lodgings(data)
    (ROOT / "includes/lodgings-primary.md").write_text(table, encoding="utf-8")
    (ROOT / "includes/lodging-links.md").write_text(links, encoding="utf-8")
    print(f'Generated {len(data["stays"])} dated main-plan stays and name-search links')


if __name__ == "__main__":
    main()
