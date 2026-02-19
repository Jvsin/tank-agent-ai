
"""Checkpointy prowadzące w stronę wrogiej armii."""

from __future__ import annotations

from typing import List, Tuple

# Zasięgi strzału według typu amunicji (backend/structures/ammo.py)
AMMO_RANGE = {
    "HEAVY": 25.0,
    "LIGHT": 50.0,
    "LONG_DISTANCE": 100.0,
}

# Stały korytarz (mapa 200x200): łuk przez górę wygenerowanego SVG i środek mapy.
# Uwaga: w debug SVG mniejsze y jest wyżej, więc punkty start/end mają relatywnie małe y.
# Team 1 porusza się ze zachodu na wschód, Team 2 czyta listę od tyłu.
STATIC_CORRIDOR_CHECKPOINTS: List[Tuple[float, float]] = [
    (35.0, 45.0),
    (30.0, 75.0),
    (35.0, 95.0),
    (75.0, 95.0),
    (115.0, 95.0),
    (145.0, 95.0),
    (155.0, 55.0),
]


def get_firing_range(ammo_loaded: str | None) -> float:
    """Zwraca zasięg strzału dla załadowanego typu amunicji."""
    if not ammo_loaded:
        return AMMO_RANGE["LIGHT"]  # domyślnie LIGHT
    key = str(ammo_loaded).upper()
    return AMMO_RANGE.get(key, AMMO_RANGE["LIGHT"])


def build_checkpoints_to_enemy(
    team: int,
    start_x: float,
    start_y: float,
    map_width: float = 200.0,
    map_height: float = 200.0,
    num_checkpoints: int = 6,
    map_filename: str = "advanced_road_trees.csv",
) -> List[Tuple[float, float]]:
    """
    Zwraca listę stałych checkpointów.
    Team 2 dostaje tę samą listę czytaną od tyłu (wschód -> zachód).
    """
    _ = (start_x, start_y, map_width, map_height, num_checkpoints, map_filename)
    if team == 2:
        return list(reversed(STATIC_CORRIDOR_CHECKPOINTS))
    return list(STATIC_CORRIDOR_CHECKPOINTS)


def lane_offset_checkpoint(tank_id: str, point: Tuple[float, float]) -> Tuple[float, float]:
    """Lekki, deterministyczny offset pasa jazdy, aby sojusznicy nie jechali identycznym śladem."""
    lane = (sum(ord(ch) for ch in str(tank_id)) % 3) - 1  # -1, 0, +1
    return point[0], point[1] + 4.0 * lane
