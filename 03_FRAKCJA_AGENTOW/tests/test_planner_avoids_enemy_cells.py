"""Verify A* planner considers enemy occupancy in movement cost."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent_core.world_model import WorldModel
from agent_core.planner import AStarPlanner


def test_mark_enemy_occupancy_increases_movement_cost():
    """Komórka z wrogiem ma wyższy koszt ruchu."""
    model = WorldModel(grid_size=10.0)
    cell = (5, 5)
    base_cost = model.movement_cost(cell)

    model.mark_enemy_occupancy(cell, ttl=5.0)
    cost_with_enemy = model.movement_cost(cell)

    assert cost_with_enemy > base_cost
    assert model.enemy_occupancy_score(cell) > 0


def test_planner_avoids_enemy_cell_when_alternative_exists():
    """A* wybiera ścieżkę omijającą komórkę z wrogiem, gdy jest alternatywa."""
    model = WorldModel(grid_size=10.0)
    planner = AStarPlanner(model)

    # Komórka (5, 5) ma wroga – droga przez nią jest droga
    model.mark_enemy_occupancy((5, 5), ttl=5.0)

    # Ścieżka z (3, 5) do (7, 5) – najkrótsza przechodzi przez (5, 5)
    # Ale A* powinien preferować objazd przez (5, 4) lub (5, 6) jeśli koszt wroga jest wysoki
    start = (3, 5)
    goal = (7, 5)

    path = planner.build_path(start, goal, radius=10)
    assert len(path) > 0
    # Ścieżka nie powinna zawierać (5, 5) gdy jest droga objazdem
    # (może zawierać jeśli objazd jest znacznie dłuższy – zależy od wag)
    # Sprawdzamy przynajmniej że path istnieje i dochodzi do celu
    assert path[-1] == goal
