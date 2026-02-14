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

    @staticmethod
    def _manhattan(a: Tuple[int, int], b: Tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _cell_safety_value(self, cell: Tuple[int, int]) -> float:
        state = self.world_model.get_state(cell)
        visits = self.world_model.visit_counts.get(cell, 0)
        local_pressure = self.world_model.local_block_pressure(cell)
        return (
            2.8 * state.safe
            - 6.5 * state.danger
            - 4.2 * state.blocked
            - 0.8 * local_pressure
            - 0.18 * visits
        )

    def _unknown_neighbors(self, cell: Tuple[int, int]) -> int:
        unknown = 0
        for n in self.world_model.neighbors4(cell):
            if n not in self.world_model.cell_states:
                unknown += 1
        return unknown

    def _choose_attack_standoff(self, my_cell: Tuple[int, int], enemy_cell: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        best_cell: Optional[Tuple[int, int]] = None
        best_score = -1e9

        ex, ey = enemy_cell
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                cell = (ex + dx, ey + dy)
                if self.world_model.is_blocked_for_pathing(cell):
                    continue
                dist_enemy = self._manhattan(cell, enemy_cell)
                if dist_enemy < 2 or dist_enemy > 6:
                    continue

                dist_me = self._manhattan(cell, my_cell)
                safety = self._cell_safety_value(cell)
                score = 1.8 * safety - 0.35 * dist_me - 0.15 * abs(dist_enemy - 4)
                if score > best_score:
                    best_score = score
                    best_cell = cell

        return best_cell

    def _choose_control_lane(self, my_cell: Tuple[int, int], radius: int = 12) -> Optional[Tuple[int, int]]:
        best_cell: Optional[Tuple[int, int]] = None
        best_score = -1e9

        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                cell = (my_cell[0] + dx, my_cell[1] + dy)
                if self.world_model.is_blocked_for_pathing(cell):
                    continue

                dist = abs(dx) + abs(dy)
                if dist < 3 or dist > radius:
                    continue

                safety = self._cell_safety_value(cell)
                frontier_bonus = 0.65 * self._unknown_neighbors(cell)
                range_bonus = -0.12 * abs(dist - 7)
                score = safety + frontier_bonus + range_bonus
                if score > best_score:
                    best_score = score
                    best_cell = cell

        return best_cell

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
                local_pressure = self.world_model.local_block_pressure(cell)
                score = 3.0 * state.safe - 6.0 * state.danger - 3.5 * state.blocked - 0.8 * local_pressure + 0.22 * dist
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

        if enemy_cells and hp_ratio >= 0.58:
            enemy_cells.sort(key=lambda cell: abs(cell[0] - my_cell[0]) + abs(cell[1] - my_cell[1]))
            standoff = self._choose_attack_standoff(my_cell, enemy_cells[0])
            if standoff is not None:
                return Goal(standoff, "attack_standoff", 720.0)
            return Goal(enemy_cells[0], "attack", 700.0)

        if powerups:
            if hp_ratio < 0.8:
                medkits = [cell for cell, ptype in powerups if "med" in ptype]
                if medkits:
                    medkits.sort(key=lambda cell: abs(cell[0] - my_cell[0]) + abs(cell[1] - my_cell[1]))
                    return Goal(medkits[0], "collect_medkit", 600.0)

            powerups.sort(key=lambda item: abs(item[0][0] - my_cell[0]) + abs(item[0][1] - my_cell[1]))
            return Goal(powerups[0][0], "collect_powerup", 500.0)

        control_cell = self._choose_control_lane(my_cell, radius=12)
        if control_cell is not None:
            return Goal(control_cell, "control_lane", 360.0)

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
                local_pressure = self.world_model.local_block_pressure(cell)
                safety_penalty = 4.5 * state.danger + 3.6 * state.blocked + 0.7 * local_pressure - 0.7 * min(state.safe, 3.0)
                value = float(visits) + 0.1 * dist_penalty + safety_penalty
                if value < best_value:
                    best_value = value
                    best_cell = cell

        if best_cell:
            return Goal(best_cell, "explore", 300.0)

        return None
