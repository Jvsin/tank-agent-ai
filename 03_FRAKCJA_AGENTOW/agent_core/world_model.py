from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


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

    @staticmethod
    def neighbors4(cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        x, y = cell
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

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
        if state.danger >= 4.0 and state.safe < 1.5:
            return True
        return False

    def is_dangerous_cell(self, cell: Tuple[int, int]) -> bool:
        state = self.cell_states.get(cell)
        if state is None:
            return False
        return state.danger >= 1.0

    def local_block_pressure(self, cell: Tuple[int, int]) -> float:
        pressure = 0.0
        for neighbor in self.neighbors4(cell):
            if neighbor in self.dead_end_ttl:
                pressure += 1.2
                continue
            state = self.cell_states.get(neighbor)
            if state is None:
                continue
            pressure += 0.45 * state.blocked + 0.25 * state.danger
        return pressure

    def movement_cost(self, cell: Tuple[int, int]) -> float:
        state = self.cell_states.get(cell, CellState())
        visits = float(self.visit_counts.get(cell, 0))
        local_pressure = self.local_block_pressure(cell)
        base = 1.9
        base -= 0.35 * min(state.safe, 3.0)
        base += 4.8 * state.danger
        base += 7.2 * state.blocked
        base += 0.8 * local_pressure
        base += 0.12 * min(visits, 12.0)
        return max(0.35, base)
