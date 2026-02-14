"""
Map-condition stress tests for movement quality.

Cele:
- Spawn na wodzie (hazard) otoczonej dziurami/utrudnieniami
- Spawn przy krawędzi mapy na pothole z trudnym wyjściem
- Wymuszenie eksploracji po wyjściu z pułapki
"""

import csv
import math
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

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


def _neighbors4(c: Tuple[int, int]) -> Sequence[Tuple[int, int]]:
    x, y = c
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


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


def _build_sensor(
    grid: List[List[str]],
    my_x: float,
    my_y: float,
    radius: float,
    enemy_pos: Optional[Tuple[float, float]] = None,
) -> Dict:
    h = len(grid)
    w = len(grid[0]) if h else 0
    seen_obstacles = []
    seen_terrains = []

    for y in range(h):
        for x in range(w):
            tile = grid[y][x].strip()
            cx, cy = _cell_center(x, y)
            if math.hypot(cx - my_x, cy - my_y) > radius:
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
    if enemy_pos is not None and math.hypot(enemy_pos[0] - my_x, enemy_pos[1] - my_y) <= radius:
        seen_tanks.append(
            {
                "id": "enemy_stress",
                "team": 2,
                "tank_type": "HEAVY",
                "is_damaged": False,
                "position": {"x": enemy_pos[0], "y": enemy_pos[1]},
            }
        )

    return {
        "seen_tanks": seen_tanks,
        "seen_powerups": [],
        "seen_obstacles": seen_obstacles,
        "seen_terrains": seen_terrains,
    }


def _find_water_trap_spawn(grid: List[List[str]]) -> Tuple[float, float]:
    h = len(grid)
    w = len(grid[0]) if h else 0

    best_cell: Optional[Tuple[int, int]] = None
    best_score = -1e9
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            c = (x, y)
            if _tile_at_cell(grid, c) != "Water":
                continue

            potholes = 0
            hazards = 0
            obstacles = 0
            safe = 0
            for n in _neighbors4(c):
                t = _tile_at_cell(grid, n)
                if t == "PotholeRoad":
                    potholes += 1
                if t in HAZARD_TILES:
                    hazards += 1
                elif t in OBSTACLE_TILES:
                    obstacles += 1
                else:
                    safe += 1

            if potholes < 1 or hazards < 2 or safe < 1:
                continue

            score = 2.8 * potholes + 1.3 * hazards + 1.6 * obstacles - 1.0 * safe
            if score > best_score:
                best_score = score
                best_cell = c

    if best_cell is None:
        return _cell_center(10, 10)
    return _cell_center(best_cell[0], best_cell[1])


def _find_edge_pothole_spawn(grid: List[List[str]]) -> Tuple[float, float]:
    h = len(grid)
    w = len(grid[0]) if h else 0

    best_cell: Optional[Tuple[int, int]] = None
    best_score = -1e9
    for y in range(h):
        for x in range(w):
            c = (x, y)
            if _tile_at_cell(grid, c) != "PotholeRoad":
                continue

            edge_dist = min(x, y, w - 1 - x, h - 1 - y)
            if edge_dist > 2:
                continue

            hazards = 0
            water_n = 0
            obstacles = 0
            safe = 0
            for n in _neighbors4(c):
                t = _tile_at_cell(grid, n)
                if t in HAZARD_TILES:
                    hazards += 1
                if t == "Water":
                    water_n += 1
                elif t in OBSTACLE_TILES:
                    obstacles += 1
                else:
                    safe += 1

            if water_n < 1 or hazards < 2 or safe < 1:
                continue

            score = 2.4 * water_n + 1.2 * hazards + 1.4 * obstacles - 0.8 * safe - 0.7 * edge_dist
            if score > best_score:
                best_score = score
                best_cell = c

    if best_cell is None:
        return _cell_center(2, 2)
    return _cell_center(best_cell[0], best_cell[1])


def _enemy_patrol(tick: int) -> Tuple[float, float]:
    path = [(11, 3), (14, 5), (15, 9), (13, 13), (9, 15), (6, 13), (4, 9), (6, 5)]
    idx = (tick // 36) % len(path)
    cx, cy = path[idx]
    return _cell_center(cx, cy)


def _simulate_episode(
    grid: List[List[str]],
    start_xy: Tuple[float, float],
    ticks: int,
    sensor_radius: float,
    enemy_pressure: bool,
) -> Dict[str, float]:
    agent = SmartAgent(name="MapTrapTest")
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
    hazard_ticks = 0
    wall_hits = 0
    total_distance = 0.0
    unique_cells: set[Tuple[int, int]] = set()
    first_safe_tick: Optional[int] = None
    safe_streak = 0
    max_safe_streak = 0

    for tick in range(1, ticks + 1):
        enemy_pos = _enemy_patrol(tick) if enemy_pressure else None
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
                my_status["hp"] = max(0.0, my_status["hp"] - 9.0)
            else:
                my_status["position"]["x"] = new_x
                my_status["position"]["y"] = new_y
                total_distance += math.hypot(new_x - old_x, new_y - old_y)

        c = _to_cell(my_status["position"]["x"], my_status["position"]["y"])
        unique_cells.add(c)
        tile = _tile_at_cell(grid, c)
        if tile in HAZARD_TILES:
            hazard_ticks += 1
            my_status["hp"] = max(0.0, my_status["hp"] - 0.12)
            safe_streak = 0
        else:
            safe_streak += 1
            max_safe_streak = max(max_safe_streak, safe_streak)
            if first_safe_tick is None:
                first_safe_tick = tick

    if first_safe_tick is None:
        first_safe_tick = float(ticks)

    return {
        "move_ratio": move_ticks / ticks,
        "hazard_ratio": hazard_ticks / ticks,
        "wall_hits": float(wall_hits),
        "final_hp": my_status["hp"],
        "distance": total_distance,
        "unique_cells": float(len(unique_cells)),
        "first_safe_tick": float(first_safe_tick),
        "max_safe_streak": float(max_safe_streak),
    }


def run_test() -> int:
    grid = _load_map_grid(MAP_PATH)

    water_spawn = _find_water_trap_spawn(grid)
    edge_spawn = _find_edge_pothole_spawn(grid)

    water_result = _simulate_episode(
        grid=grid,
        start_xy=water_spawn,
        ticks=240,
        sensor_radius=34.0,
        enemy_pressure=False,
    )

    edge_result = _simulate_episode(
        grid=grid,
        start_xy=edge_spawn,
        ticks=280,
        sensor_radius=34.0,
        enemy_pressure=False,
    )

    pressure_result = _simulate_episode(
        grid=grid,
        start_xy=water_spawn,
        ticks=320,
        sensor_radius=36.0,
        enemy_pressure=True,
    )

    print(
        "[MAP_TRAPS] "
        f"water_escape_tick={water_result['first_safe_tick']:.0f} water_hazard={water_result['hazard_ratio']:.2f} "
        f"edge_explore_cells={edge_result['unique_cells']:.0f} edge_dist={edge_result['distance']:.1f} edge_hazard={edge_result['hazard_ratio']:.2f} "
        f"pressure_cells={pressure_result['unique_cells']:.0f} pressure_hazard={pressure_result['hazard_ratio']:.2f} "
        f"pressure_safe_streak={pressure_result['max_safe_streak']:.0f} pressure_hp={pressure_result['final_hp']:.1f}"
    )

    if water_result["first_safe_tick"] > 95:
        print("[MAP_TRAPS] FAIL: za wolne wyjście z wody/hazardu")
        return 1
    if water_result["hazard_ratio"] > 0.66:
        print("[MAP_TRAPS] FAIL: zbyt długie siedzenie w hazardzie po spawnie w wodzie")
        return 1
    if water_result["wall_hits"] > 12:
        print("[MAP_TRAPS] FAIL: zbyt dużo kolizji przy próbie wyjścia z pułapki")
        return 1

    if edge_result["move_ratio"] < 0.82:
        print("[MAP_TRAPS] FAIL: niska aktywność ruchu przy krawędzi i dziurach")
        return 1
    if edge_result["unique_cells"] < 18:
        print("[MAP_TRAPS] FAIL: zbyt słaba eksploracja po wyjściu z trudnego spawnu")
        return 1
    if edge_result["distance"] < 58.0:
        print("[MAP_TRAPS] FAIL: agent jedzie za krótko po wyjściu z pułapki")
        return 1

    if pressure_result["hazard_ratio"] > 0.60:
        print("[MAP_TRAPS] FAIL: pod presją wraca za dużo do hazardu")
        return 1
    if pressure_result["max_safe_streak"] < 80:
        print("[MAP_TRAPS] FAIL: brak stabilnego utrzymania się na bezpiecznych polach")
        return 1
    if pressure_result["unique_cells"] < 20:
        print("[MAP_TRAPS] FAIL: pod presją eksploracja jest za mała")
        return 1
    if pressure_result["final_hp"] < 26.0:
        print("[MAP_TRAPS] FAIL: przeżywalność pod presją jest za niska")
        return 1

    print("[MAP_TRAPS] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_test())
