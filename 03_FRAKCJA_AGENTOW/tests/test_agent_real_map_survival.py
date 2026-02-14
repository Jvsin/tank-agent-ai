"""
Test 3: Agent na realnej mapie powinien ograniczać ściany i hazard.

Scenariusz:
- Ładujemy faktyczną mapę advanced_road_trees.csv (20x20, tile=10)
- Start na kaflu hazardowym, otoczenie i przeszkody podawane w sensorze
- Uproszczona fizyka ruchu + kolizja z przeszkodą + damage od hazardu

Cel:
- agent ma jechać, a nie stać
- agent ma ograniczać wall-hit
- agent ma nie spędzać większości czasu w hazardzie
"""

import csv
import math
import os
import sys
from typing import Dict, List, Tuple

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
OBSTACLE_TILES = {"Wall", "Tree", "AntiTankSpike"}
HAZARD_TILES = {"Water", "PotholeRoad"}


def _load_map_grid(path: str) -> List[List[str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return [row for row in csv.reader(f)]


def _cell_center(ix: int, iy: int) -> Tuple[float, float]:
    return (ix + 0.5) * TILE_SIZE, (iy + 0.5) * TILE_SIZE


def _to_cell(x: float, y: float) -> Tuple[int, int]:
    return int(x // TILE_SIZE), int(y // TILE_SIZE)


def _in_bounds(grid: List[List[str]], c: Tuple[int, int]) -> bool:
    h = len(grid)
    w = len(grid[0]) if h else 0
    return 0 <= c[0] < w and 0 <= c[1] < h


def _tile_at(grid: List[List[str]], x: float, y: float) -> str:
    cx, cy = _to_cell(x, y)
    if not _in_bounds(grid, (cx, cy)):
        return "Wall"
    return grid[cy][cx].strip()


def _find_hazard_start(grid: List[List[str]]) -> Tuple[float, float]:
    h = len(grid)
    w = len(grid[0]) if h else 0
    for y in range(2, max(2, h - 2)):
        for x in range(2, max(2, w - 2)):
            tile = grid[y][x].strip()
            if tile not in HAZARD_TILES:
                continue
            neighbors = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
            free_neighbors = 0
            obstacle_neighbors = 0
            for nx, ny in neighbors:
                if not _in_bounds(grid, (nx, ny)):
                    continue
                nt = grid[ny][nx].strip()
                if nt not in OBSTACLE_TILES and nt not in HAZARD_TILES:
                    free_neighbors += 1
                if nt in OBSTACLE_TILES:
                    obstacle_neighbors += 1
            if free_neighbors >= 2 and obstacle_neighbors >= 1:
                return _cell_center(x, y)
    return _cell_center(2, 2)


def _build_sensor(grid: List[List[str]], my_x: float, my_y: float, radius: float = 55.0) -> Dict:
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

    return {
        "seen_tanks": [],
        "seen_powerups": [],
        "seen_obstacles": seen_obstacles,
        "seen_terrains": seen_terrains,
    }


def run_test(ticks: int = 180) -> int:
    grid = _load_map_grid(MAP_PATH)
    start_x, start_y = _find_hazard_start(grid)

    agent = SmartAgent(name="RealMapSurvivalTest")

    my_status = {
        "_id": "tank_test",
        "_team": 1,
        "_tank_type": "LIGHT",
        "hp": 80.0,
        "_max_hp": 80.0,
        "position": {"x": start_x, "y": start_y},
        "heading": 0.0,
        "barrel_angle": 0.0,
        "_top_speed": 5.0,
        "_heading_spin_rate": 70.0,
        "_barrel_spin_rate": 90.0,
    }

    move_ticks = 0
    wall_hits = 0
    hazard_ticks = 0

    for tick in range(1, ticks + 1):
        sensor = _build_sensor(grid, my_status["position"]["x"], my_status["position"]["y"], radius=55.0)

        action = agent.get_action(
            current_tick=tick,
            my_tank_status=my_status,
            sensor_data=sensor,
            enemies_remaining=5,
        )

        if abs(action.move_speed) > 0.15:
            move_ticks += 1

        my_status["heading"] = (my_status["heading"] + action.heading_rotation_angle) % 360

        old_x = my_status["position"]["x"]
        old_y = my_status["position"]["y"]

        if abs(action.move_speed) > 0.01:
            dt = 1.0 / 60.0
            hrad = math.radians(my_status["heading"])
            new_x = old_x + math.cos(hrad) * action.move_speed * dt
            new_y = old_y + math.sin(hrad) * action.move_speed * dt

            next_cell = _to_cell(new_x, new_y)
            next_tile = _tile_at(grid, new_x, new_y)

            if not _in_bounds(grid, next_cell) or next_tile in OBSTACLE_TILES:
                wall_hits += 1
                my_status["hp"] = max(0.0, my_status["hp"] - 10.0)
            else:
                my_status["position"]["x"] = new_x
                my_status["position"]["y"] = new_y

        current_tile = _tile_at(grid, my_status["position"]["x"], my_status["position"]["y"])
        if current_tile in HAZARD_TILES:
            hazard_ticks += 1
            my_status["hp"] = max(0.0, my_status["hp"] - 0.1)

    move_ratio = move_ticks / ticks
    hazard_ratio = hazard_ticks / ticks

    print(
        f"[REAL_MAP] ticks={ticks} move_ratio={move_ratio:.2f} "
        f"wall_hits={wall_hits} hazard_ratio={hazard_ratio:.2f} hp={my_status['hp']:.1f}"
    )

    if move_ratio < 0.70:
        print("[REAL_MAP] FAIL: agent za mało się przemieszcza")
        return 1

    if wall_hits > 20:
        print("[REAL_MAP] FAIL: zbyt dużo kolizji ze ścianami/przeszkodami")
        return 1

    if hazard_ratio > 0.75:
        print("[REAL_MAP] FAIL: agent zbyt długo siedzi w hazardzie")
        return 1

    print("[REAL_MAP] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_test())
