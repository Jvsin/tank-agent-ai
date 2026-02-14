from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class CellState:
    safe: float = 0.0
    danger: float = 0.0
    blocked: float = 0.0


class WorldModel:
    def __init__(self, grid_size: float = 10.0):
        self.grid_size = grid_size
        self.cell_states: Dict[Tuple[int, int], CellState] = {}
        self.visit_counts: Dict[Tuple[int, int], int] = {}
        self.dead_end_ttl: Dict[Tuple[int, int], float] = {}

    def to_cell(self, x: float, y: float) -> Tuple[int, int]:
        return int(x // self.grid_size), int(y // self.grid_size)

    def to_world_center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        return (cell[0] + 0.5) * self.grid_size, (cell[1] + 0.5) * self.grid_size

    def get_state(self, cell: Tuple[int, int]) -> CellState:
        if cell not in self.cell_states:
            self.cell_states[cell] = CellState()
        return self.cell_states[cell]

    def increment_visit(self, cell: Tuple[int, int]) -> None:
        self.visit_counts[cell] = self.visit_counts.get(cell, 0) + 1

    def decay_dead_ends(self) -> None:
        remaining: Dict[Tuple[int, int], float] = {}
        for cell, ttl in self.dead_end_ttl.items():
            next_ttl = ttl - 1.0
            if next_ttl > 0:
                remaining[cell] = next_ttl
        self.dead_end_ttl = remaining

    def mark_dead_end(self, cell: Tuple[int, int], ttl: float = 520.0) -> None:
        self.dead_end_ttl[cell] = max(self.dead_end_ttl.get(cell, 0.0), ttl)

    def is_blocked_for_pathing(self, cell: Tuple[int, int]) -> bool:
        if cell in self.dead_end_ttl:
            return True
        state = self.cell_states.get(cell)
        if state is None:
            return False
        if state.blocked >= 1.0:
            return True
        if state.danger > state.safe + 1.0:
            return True
        return False

    def is_dangerous_cell(self, cell: Tuple[int, int]) -> bool:
        state = self.cell_states.get(cell)
        if state is None:
            return False
        return state.danger >= 1.0

    def movement_cost(self, cell: Tuple[int, int]) -> float:
        state = self.cell_states.get(cell, CellState())
        visits = float(self.visit_counts.get(cell, 0))
        return 2.0 - 0.25 * min(state.safe, 3.0) + 5.0 * state.danger + 6.0 * state.blocked + 0.15 * min(visits, 12.0)
