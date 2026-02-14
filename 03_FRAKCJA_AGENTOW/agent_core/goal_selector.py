from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .world_model import WorldModel


@dataclass
class Goal:
    cell: Tuple[int, int]
    mode: str
    score: float


class GoalSelector:
    def __init__(self, world_model: WorldModel):
        self.world_model = world_model

    def enemy_cells(self, sensor: Dict[str, Any], to_cell_fn) -> List[Tuple[int, int]]:
        cells: List[Tuple[int, int]] = []
        for tank in sensor.get("seen_tanks", []):
            pos = tank.get("position", {}) if isinstance(tank, dict) else getattr(tank, "position", None)
            tx, ty = to_cell_fn("xy", pos)
            cells.append(self.world_model.to_cell(tx, ty))
        return cells

    def powerup_cells(self, sensor: Dict[str, Any], to_cell_fn, powerup_type_fn) -> List[Tuple[Tuple[int, int], str]]:
        out: List[Tuple[Tuple[int, int], str]] = []
        for powerup in sensor.get("seen_powerups", []):
            pos = powerup.get("position", powerup.get("_position", {})) if isinstance(powerup, dict) else getattr(powerup, "position", getattr(powerup, "_position", None))
            px, py = to_cell_fn("xy", pos)
            out.append((self.world_model.to_cell(px, py), powerup_type_fn(powerup)))
        return out

    def nearest_safe_cell(self, my_cell: Tuple[int, int], radius: int = 10, require_known: bool = False) -> Optional[Tuple[int, int]]:
        best_cell: Optional[Tuple[int, int]] = None
        best_score = -1e9
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                cell = (my_cell[0] + dx, my_cell[1] + dy)
                if self.world_model.is_blocked_for_pathing(cell):
                    continue
                state = self.world_model.cell_states.get(cell)
                if require_known and state is None:
                    continue
                if state is None:
                    state = self.world_model.get_state(cell)
                dist = abs(dx) + abs(dy)
                score = 3.0 * state.safe - 6.0 * state.danger - 3.0 * state.blocked + 0.25 * dist
                if score > best_score:
                    best_score = score
                    best_cell = cell
        return best_cell

    def choose_goal(
        self,
        my_x: float,
        my_y: float,
        hp_ratio: float,
        sensor: Dict[str, Any],
        standing_on_danger_fn,
        to_cell_fn,
        powerup_type_fn,
    ) -> Optional[Goal]:
        my_cell = self.world_model.to_cell(my_x, my_y)
        enemy_cells = self.enemy_cells(sensor, to_cell_fn)
        powerups = self.powerup_cells(sensor, to_cell_fn, powerup_type_fn)

        if powerups and not standing_on_danger_fn(my_x, my_y, sensor):
            closest = min(powerups, key=lambda item: abs(item[0][0] - my_cell[0]) + abs(item[0][1] - my_cell[1]))
            close_dist = abs(closest[0][0] - my_cell[0]) + abs(closest[0][1] - my_cell[1])
            if close_dist <= 2:
                return Goal(closest[0], "pickup_now", 950.0)

        if standing_on_danger_fn(my_x, my_y, sensor):
            safe = self.nearest_safe_cell(my_cell, require_known=True)
            if safe:
                return Goal(safe, "escape_danger", 999.0)

        if hp_ratio < 0.45:
            medkits = [cell for cell, ptype in powerups if "med" in ptype]
            if medkits:
                medkits.sort(key=lambda cell: abs(cell[0] - my_cell[0]) + abs(cell[1] - my_cell[1]))
                return Goal(medkits[0], "low_hp_medkit", 900.0)
            safe = self.nearest_safe_cell(my_cell, require_known=True)
            if safe:
                return Goal(safe, "low_hp_safe", 850.0)

        if enemy_cells and hp_ratio >= 0.7:
            enemy_cells.sort(key=lambda cell: abs(cell[0] - my_cell[0]) + abs(cell[1] - my_cell[1]))
            return Goal(enemy_cells[0], "attack", 700.0)

        if powerups:
            if hp_ratio < 0.8:
                medkits = [cell for cell, ptype in powerups if "med" in ptype]
                if medkits:
                    medkits.sort(key=lambda cell: abs(cell[0] - my_cell[0]) + abs(cell[1] - my_cell[1]))
                    return Goal(medkits[0], "collect_medkit", 600.0)

            powerups.sort(key=lambda item: abs(item[0][0] - my_cell[0]) + abs(item[0][1] - my_cell[1]))
            return Goal(powerups[0][0], "collect_powerup", 500.0)

        best_cell: Optional[Tuple[int, int]] = None
        best_value = 1e9
        for dx in range(-8, 9):
            for dy in range(-8, 9):
                cell = (my_cell[0] + dx, my_cell[1] + dy)
                if self.world_model.is_blocked_for_pathing(cell):
                    continue
                visits = self.world_model.visit_counts.get(cell, 0)
                state = self.world_model.get_state(cell)
                dist_penalty = abs((abs(dx) + abs(dy)) - 5)
                safety_penalty = 4.0 * state.danger + 3.0 * state.blocked - 0.6 * min(state.safe, 3.0)
                value = float(visits) + 0.1 * dist_penalty + safety_penalty
                if value < best_value:
                    best_value = value
                    best_cell = cell

        if best_cell:
            return Goal(best_cell, "explore", 300.0)

        return None
