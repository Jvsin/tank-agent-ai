"""
Hard test suite: real map, long horizon, difficult starts, enemy pressure.

Założenia:
- bazuje na tej samej mapie co test podstawowy (advanced_road_trees.csv)
- scenariusze są dłuższe i trudniejsze (mniejsza wizja, presja od "wroga")
- walidujemy nie tylko ruch, ale też przeżywalność i stabilność nawigacji
"""

import csv
import math
import os
import sys
from typing import Dict, List, Sequence, Tuple

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent

MAP_PATH = os.path.join(
    os.path.dirname(AGENT_DIR),
    "02_FRAKCJA_SILNIKA",
    "backend",
    "maps",
    "advanced_road_trees.csv",
)

TILE_SIZE = 10.0
DT = 1.0 / 60.0
OBSTACLE_TILES = {"Wall", "Tree", "AntiTankSpike"}
HAZARD_TILES = {"Water", "PotholeRoad"}


def _load_map_grid(path: str) -> List[List[str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return [row for row in csv.reader(f)]


def _to_cell(x: float, y: float) -> Tuple[int, int]:
    return int(x // TILE_SIZE), int(y // TILE_SIZE)


def _cell_center(ix: int, iy: int) -> Tuple[float, float]:
    return (ix + 0.5) * TILE_SIZE, (iy + 0.5) * TILE_SIZE


def _in_bounds(grid: List[List[str]], c: Tuple[int, int]) -> bool:
    h = len(grid)
    w = len(grid[0]) if h else 0
    return 0 <= c[0] < w and 0 <= c[1] < h


def _tile_at_cell(grid: List[List[str]], c: Tuple[int, int]) -> str:
    if not _in_bounds(grid, c):
        return "Wall"
    return grid[c[1]][c[0]].strip()


def _tile_at_xy(grid: List[List[str]], x: float, y: float) -> str:
    return _tile_at_cell(grid, _to_cell(x, y))


def _neighbors4(c: Tuple[int, int]) -> Sequence[Tuple[int, int]]:
    x, y = c
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def _classify_start_cell(grid: List[List[str]], c: Tuple[int, int]) -> Tuple[int, int, int]:
    obstacle_n = 0
    hazard_n = 0
    safe_n = 0
    for n in _neighbors4(c):
        tile = _tile_at_cell(grid, n)
        if tile in OBSTACLE_TILES:
            obstacle_n += 1
        elif tile in HAZARD_TILES:
            hazard_n += 1
        else:
            safe_n += 1
    return obstacle_n, hazard_n, safe_n


def _find_challenging_starts(grid: List[List[str]], count: int = 5) -> List[Tuple[float, float]]:
    h = len(grid)
    w = len(grid[0]) if h else 0

    hazard_candidates: List[Tuple[float, Tuple[int, int]]] = []
    safe_candidates: List[Tuple[float, Tuple[int, int]]] = []

    for y in range(1, h - 1):
        for x in range(1, w - 1):
            c = (x, y)
            tile = _tile_at_cell(grid, c)
            obstacle_n, hazard_n, safe_n = _classify_start_cell(grid, c)
            if safe_n <= 0:
                continue

            if tile in HAZARD_TILES and obstacle_n >= 1:
                score = 2.0 * obstacle_n + 1.5 * hazard_n + 0.5 * (4 - safe_n)
                hazard_candidates.append((score, c))
            elif tile not in OBSTACLE_TILES and hazard_n >= 1 and obstacle_n >= 1:
                score = 1.8 * obstacle_n + 1.2 * hazard_n + 0.5 * (4 - safe_n)
                safe_candidates.append((score, c))

    hazard_candidates.sort(key=lambda item: item[0], reverse=True)
    safe_candidates.sort(key=lambda item: item[0], reverse=True)

    selected_cells: List[Tuple[int, int]] = []
    for _, cell in hazard_candidates[: max(2, count // 2 + 1)]:
        selected_cells.append(cell)
    for _, cell in safe_candidates:
        if len(selected_cells) >= count:
            break
        if cell not in selected_cells:
            selected_cells.append(cell)

    if len(selected_cells) < count:
        fallback = [(2, 2), (3, 10), (10, 10), (16, 16), (8, 4)]
        for c in fallback:
            if len(selected_cells) >= count:
                break
            if _in_bounds(grid, c) and _tile_at_cell(grid, c) not in OBSTACLE_TILES and c not in selected_cells:
                selected_cells.append(c)

    return [_cell_center(cx, cy) for cx, cy in selected_cells[:count]]


def _build_sensor(
    grid: List[List[str]],
    my_x: float,
    my_y: float,
    radius: float,
    enemy_pos: Tuple[float, float] | None = None,
) -> Dict:
    h = len(grid)
    w = len(grid[0]) if h else 0

    seen_obstacles = []
    seen_terrains = []

    for y in range(h):
        for x in range(w):
            tile = grid[y][x].strip()
            cx, cy = _cell_center(x, y)
            d = math.hypot(cx - my_x, cy - my_y)
            if d > radius:
                continue

            if tile in OBSTACLE_TILES:
                seen_obstacles.append(
                    {
                        "position": {"x": cx, "y": cy},
                        "type": tile,
                        "is_destructible": tile == "Tree",
                    }
                )
            else:
                seen_terrains.append(
                    {
                        "position": {"x": cx, "y": cy},
                        "type": tile,
                        "dmg": 1 if tile in HAZARD_TILES else 0,
                        "speed_modifier": 0.7 if tile in HAZARD_TILES else 1.0,
                    }
                )

    seen_tanks = []
    if enemy_pos is not None:
        ex, ey = enemy_pos
        if math.hypot(ex - my_x, ey - my_y) <= radius:
            seen_tanks.append(
                {
                    "id": "enemy_dummy",
                    "team": 2,
                    "tank_type": "HEAVY",
                    "is_damaged": False,
                    "position": {"x": ex, "y": ey},
                }
            )

    return {
        "seen_tanks": seen_tanks,
        "seen_powerups": [],
        "seen_obstacles": seen_obstacles,
        "seen_terrains": seen_terrains,
    }


def _enemy_lure_position(grid: List[List[str]], tick: int) -> Tuple[float, float]:
    points = [
        (11, 2),
        (15, 5),
        (16, 10),
        (14, 15),
        (10, 17),
        (6, 15),
        (4, 10),
        (6, 5),
    ]
    idx = (tick // 40) % len(points)
    cell = points[idx]
    if not _in_bounds(grid, cell) or _tile_at_cell(grid, cell) in OBSTACLE_TILES:
        return _cell_center(10, 10)
    return _cell_center(cell[0], cell[1])


def _simulate(
    grid: List[List[str]],
    start_xy: Tuple[float, float],
    ticks: int,
    sensor_radius: float,
    enemy_pressure: bool,
) -> Dict[str, float]:
    agent = SmartAgent(name="HardMapTest")

    my_status = {
        "_id": "tank_test",
        "_team": 1,
        "_tank_type": "LIGHT",
        "hp": 80.0,
        "_max_hp": 80.0,
        "position": {"x": start_xy[0], "y": start_xy[1]},
        "heading": 0.0,
        "barrel_angle": 0.0,
        "_top_speed": 5.0,
        "_heading_spin_rate": 70.0,
        "_barrel_spin_rate": 90.0,
    }

    move_ticks = 0
    wall_hits = 0
    hazard_ticks = 0
    total_distance = 0.0
    unique_cells: set[Tuple[int, int]] = set()

    for tick in range(1, ticks + 1):
        enemy_pos = _enemy_lure_position(grid, tick) if enemy_pressure else None
        sensor = _build_sensor(
            grid,
            my_status["position"]["x"],
            my_status["position"]["y"],
            radius=sensor_radius,
            enemy_pos=enemy_pos,
        )

        action = agent.get_action(
            current_tick=tick,
            my_tank_status=my_status,
            sensor_data=sensor,
            enemies_remaining=3 if enemy_pressure else 0,
        )

        if abs(action.move_speed) > 0.15:
            move_ticks += 1

        my_status["heading"] = (my_status["heading"] + action.heading_rotation_angle) % 360
        old_x = my_status["position"]["x"]
        old_y = my_status["position"]["y"]

        if abs(action.move_speed) > 0.01:
            hrad = math.radians(my_status["heading"])
            new_x = old_x + math.cos(hrad) * action.move_speed * DT
            new_y = old_y + math.sin(hrad) * action.move_speed * DT

            next_cell = _to_cell(new_x, new_y)
            next_tile = _tile_at_xy(grid, new_x, new_y)
            if not _in_bounds(grid, next_cell) or next_tile in OBSTACLE_TILES:
                wall_hits += 1
                my_status["hp"] = max(0.0, my_status["hp"] - 8.0)
            else:
                my_status["position"]["x"] = new_x
                my_status["position"]["y"] = new_y
                total_distance += math.hypot(new_x - old_x, new_y - old_y)

        current_cell = _to_cell(my_status["position"]["x"], my_status["position"]["y"])
        unique_cells.add(current_cell)
        current_tile = _tile_at_cell(grid, current_cell)
        if current_tile in HAZARD_TILES:
            hazard_ticks += 1
            my_status["hp"] = max(0.0, my_status["hp"] - 0.12)

    return {
        "move_ratio": move_ticks / ticks,
        "hazard_ratio": hazard_ticks / ticks,
        "wall_hits": float(wall_hits),
        "final_hp": my_status["hp"],
        "distance": total_distance,
        "unique_cells": float(len(unique_cells)),
    }


def run_test() -> int:
    grid = _load_map_grid(MAP_PATH)
    starts = _find_challenging_starts(grid, count=5)

    multi_results = [_simulate(grid, start, ticks=260, sensor_radius=38.0, enemy_pressure=False) for start in starts]

    avg_move = sum(r["move_ratio"] for r in multi_results) / len(multi_results)
    avg_hazard = sum(r["hazard_ratio"] for r in multi_results) / len(multi_results)
    total_hits = sum(r["wall_hits"] for r in multi_results)
    survivors = sum(1 for r in multi_results if r["final_hp"] > 30.0)

    pressure_result = _simulate(
        grid,
        start_xy=starts[0],
        ticks=320,
        sensor_radius=40.0,
        enemy_pressure=True,
    )

    print(
        "[HARD_MAP] "
        f"multi_avg_move={avg_move:.2f} multi_avg_hazard={avg_hazard:.2f} "
        f"multi_wall_hits={total_hits:.0f} survivors={survivors}/{len(multi_results)} "
        f"pressure_move={pressure_result['move_ratio']:.2f} pressure_hazard={pressure_result['hazard_ratio']:.2f} "
        f"pressure_hits={pressure_result['wall_hits']:.0f} pressure_hp={pressure_result['final_hp']:.1f} "
        f"pressure_cells={pressure_result['unique_cells']:.0f}"
    )

    if avg_move < 0.82:
        print("[HARD_MAP] FAIL: agent za mało aktywny przy wielu trudnych startach")
        return 1

    if avg_hazard > 0.58:
        print("[HARD_MAP] FAIL: agent za długo przebywa w hazardzie (multi-start)")
        return 1

    if total_hits > 28:
        print("[HARD_MAP] FAIL: zbyt dużo kolizji ściana/przeszkoda (multi-start)")
        return 1

    if survivors < 4:
        print("[HARD_MAP] FAIL: za mało scenariuszy zakończonych z sensownym HP")
        return 1

    if pressure_result["move_ratio"] < 0.78:
        print("[HARD_MAP] FAIL: agent zamiera pod presją widocznego przeciwnika")
        return 1

    if pressure_result["hazard_ratio"] > 0.56:
        print("[HARD_MAP] FAIL: agent wpada w hazard pod presją przeciwnika")
        return 1

    if pressure_result["wall_hits"] > 14:
        print("[HARD_MAP] FAIL: za dużo kolizji pod presją przeciwnika")
        return 1

    if pressure_result["final_hp"] < 24.0:
        print("[HARD_MAP] FAIL: przeżywalność za niska w scenariuszu presji")
        return 1

    if pressure_result["unique_cells"] < 22:
        print("[HARD_MAP] FAIL: eksploracja zbyt mała pod presją")
        return 1

    print("[HARD_MAP] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_test())
