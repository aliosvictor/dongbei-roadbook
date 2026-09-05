#!/usr/bin/env python3
"""Rebuild reproducible WOFF2 subsets from the bundled, licensed map fonts."""
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]


def required_characters(root: Path) -> set[int]:
    paths = list(root.glob("*.qmd")) + [root / "_quarto.yml", root / "_variables.yml", root / "filters/table-scroll.lua"]
    text = "".join(path.read_text(encoding="utf-8") for path in paths)
    return set(range(32, 127)) | {ord(c) for c in text if not c.isspace()}


def font_characters(path: Path) -> set[int]:
    with TTFont(path) as font:
        return set(font.getBestCmap())


def main() -> None:
    needed = required_characters(ROOT)
    for weight in ("Regular", "Bold"):
        source = ROOT / f"assets/fonts/fandol/FandolHei-{weight}.otf"
        missing = needed - font_characters(source)
        if missing:
            raise ValueError(f"Bundled font lacks: {''.join(map(chr, sorted(missing)))}")
        options = subset.Options()
        options.flavor = "woff2"
        options.recalc_timestamp = False
        # Preserve attribution and licence metadata in the distributed subset.
        options.name_IDs = ["*"]
        options.name_languages = ["*"]
        font = subset.load_font(str(source), options)
        worker = subset.Subsetter(options=options)
        worker.populate(unicodes=needed)
        worker.subset(font)
        output = ROOT / f"assets/fonts/web/FandolHei-Roadbook-{weight}.woff2"
        subset.save_font(font, str(output), options)
        print(f"{output.name}: {len(needed)} characters")


if __name__ == "__main__":
    main()
