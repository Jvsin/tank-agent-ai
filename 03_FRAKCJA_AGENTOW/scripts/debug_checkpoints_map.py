#!/usr/bin/env python3
"""Ad-hoc debug: render map CSV with checkpoints into an SVG image."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from agent_core.checkpoints import STATIC_CORRIDOR_CHECKPOINTS  # noqa: E402

Tile = Tuple[int, int, int]
Point = Tuple[float, float]


TILE_COLORS: Dict[str, Tile] = {
    "Grass": (86, 201, 108),
    "Road": (236, 221, 173),
    "Swamp": (137, 102, 71),
    "PotholeRoad": (200, 176, 132),
    "Water": (86, 152, 220),
    "Wall": (188, 94, 36),
    "Tree": (36, 138, 56),
    "AntiTankSpike": (150, 150, 150),
}
DEFAULT_TILE_COLOR: Tile = (235, 235, 235)


def read_map_csv(path: Path) -> List[List[str]]:
    rows: List[List[str]] = []
    with path.open("r", newline="") as f:
        for row in csv.reader(f):
            clean = [c.strip() for c in row if c.strip()]
            if clean:
                rows.append(clean)
    if not rows:
        raise ValueError(f"Empty map file: {path}")
    width = len(rows[0])
    if any(len(r) != width for r in rows):
        raise ValueError(f"Inconsistent row widths in: {path}")
    return rows


def rgb(c: Tile) -> str:
    return f"rgb({c[0]},{c[1]},{c[2]})"


def map_to_svg(
    grid: Sequence[Sequence[str]],
    team1: Sequence[Point],
    team2: Sequence[Point],
    tile_size: int = 28,
) -> str:
    h = len(grid)
    w = len(grid[0])
    width_px = w * tile_size
    height_px = h * tile_size

    lines: List[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" viewBox="0 0 {width_px} {height_px}">')
    lines.append('<rect width="100%" height="100%" fill="rgb(20,20,20)"/>')

    for row_idx, row in enumerate(grid):
        for col_idx, tile in enumerate(row):
            x = col_idx * tile_size
            y = row_idx * tile_size
            color = rgb(TILE_COLORS.get(tile, DEFAULT_TILE_COLOR))
            lines.append(f'<rect x="{x}" y="{y}" width="{tile_size}" height="{tile_size}" fill="{color}" stroke="rgb(40,40,40)" stroke-width="1"/>')

    def world_to_px(p: Point) -> Tuple[float, float]:
        # World in this project: 200x200 for 20x20 map, center of tile at +5.
        return (p[0] / 10.0) * tile_size, (p[1] / 10.0) * tile_size

    def polyline(points: Sequence[Point], color: str, label: str) -> None:
        if not points:
            return
        coords = []
        for pt in points:
            x, y = world_to_px(pt)
            coords.append(f"{x:.1f},{y:.1f}")
        lines.append(
            f'<polyline points="{" ".join(coords)}" fill="none" stroke="{color}" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>'
        )
        for i, pt in enumerate(points):
            x, y = world_to_px(pt)
            radius = 5 if i == 0 else 4
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" stroke="white" stroke-width="1"/>')
            lines.append(
                f'<text x="{x + 6:.1f}" y="{y - 6:.1f}" font-size="10" fill="white" '
                f'font-family="monospace">{label}{i}</text>'
            )

    polyline(team1, "rgb(35,220,255)", "T1-")
    polyline(team2, "rgb(255,210,70)", "T2-")
    lines.append("</svg>")
    return "\n".join(lines)


def default_map_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "02_FRAKCJA_SILNIKA" / "backend" / "maps" / "symmetric.csv"
    # return root / "02_FRAKCJA_SILNIKA" / "backend" / "maps" / "advanced_road_trees.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render map CSV and checkpoints to SVG for debugging.")
    parser.add_argument("--map", dest="map_path", type=Path, default=default_map_path(), help="Path to map CSV.")
    parser.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "debug_checkpoints_map.svg",
        help="Output SVG path.",
    )
    parser.add_argument("--tile-size", dest="tile_size", type=int, default=28, help="Tile size in pixels.")
    args = parser.parse_args()

    grid = read_map_csv(args.map_path)
    team1 = list(STATIC_CORRIDOR_CHECKPOINTS)
    team2 = list(reversed(STATIC_CORRIDOR_CHECKPOINTS))
    svg = map_to_svg(grid, team1, team2, tile_size=args.tile_size)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(svg, encoding="utf-8")
    print(f"Saved: {args.output_path}")


if __name__ == "__main__":
    main()
