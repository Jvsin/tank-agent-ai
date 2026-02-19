from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from .checkpoints import build_checkpoints_to_enemy, get_firing_range, lane_offset_checkpoint
from .driver import MotionDriver
from .fuzzy_turret import FuzzyTurretController
from .geometry import euclidean_distance, heading_to_angle_deg, normalize_angle_diff, to_xy
from .goal_selector import Goal, GoalSelector
from .planner import AStarPlanner
from .world_model import WorldModel

# Tymczasowe flagi do testów
DISABLE_ESCAPE_MODE = False  # Wyłącz tryb ucieczki, testuj samo chodzenie
PRIMARY_AMMO = "LONG_DISTANCE"


class ActionCommand(BaseModel):
    barrel_rotation_angle: float = 0.0
    heading_rotation_angle: float = 0.0
    move_speed: float = 0.0
    ammo_to_load: Optional[str] = None
    should_fire: bool = False


class SmartAgent:
    def __init__(self, name: str = "OdjazdBot"):
        self.name = name
        self.is_destroyed = False

        self.model = WorldModel(grid_size=10.0)
        self.goal_selector = GoalSelector(self.model)
        self.planner = AStarPlanner(self.model)
        self.driver = MotionDriver(self.model)
        self.turret: Optional[FuzzyTurretController] = None  # Lazy init on first tick

        self.current_goal: Optional[Goal] = None
        self.replan_tick: int = 0
        self.last_hp: Optional[float] = None
        self.route_commit_until: int = 0
        self.route_commit_mode: str = ""
        self.last_danger_mark_tick: int = -9999
        self.consecutive_danger_ticks: int = 0
        self.last_cell: Optional[Tuple[int, int]] = None
        self.last_turn_cmd: float = 0.0
        self.last_turn_flip_tick: int = -9999
        self.last_mode: str = "idle"
        self.my_tank_id: str = "default"
        self.preferred_ammo: str = PRIMARY_AMMO

        # Checkpoint-based movement: lista per zespół (ustalana na start), indeks per czołg
        self.checkpoints_by_team: Dict[int, List[Tuple[float, float]]] = {}
        self.checkpoint_index_by_tank: Dict[str, int] = {}
        self.checkpoint_arrival_radius: float = 15.0

        print(f"[{self.name}] online")

    @staticmethod
    def _xy(value: Any) -> Tuple[float, float]:
        return to_xy(value)

    @staticmethod
    def _terrain_damage(terrain: Any) -> float:
        if isinstance(terrain, dict):
            return float(terrain.get("deal_damage", terrain.get("_deal_damage", terrain.get("dmg", 0))) or 0)
        return float(getattr(terrain, "deal_damage", getattr(terrain, "_deal_damage", 0)) or 0)

    @staticmethod
    def _powerup_type_text(powerup: Any) -> str:
        if isinstance(powerup, dict):
            return str(powerup.get("powerup_type", powerup.get("_powerup_type", ""))).lower()
        return str(getattr(powerup, "powerup_type", getattr(powerup, "_powerup_type", ""))).lower()

    def _mark_allies_occupancy(self, my_x: float, my_y: float, seen_allies: List[Any]) -> None:
        my_cell = self.model.to_cell(my_x, my_y)
        for ally in seen_allies:
            pos = ally.get("position", ally.get("_position", {})) if isinstance(ally, dict) else getattr(ally, "position", getattr(ally, "_position", None))
            ax, ay = self._xy(pos)
            ally_cell = self.model.to_cell(ax, ay)
            if ally_cell == my_cell:
                continue

            self.model.mark_ally_occupancy(ally_cell, ttl=5.0)
            heading = float(ally.get("heading", ally.get("_heading", 0.0)) if isinstance(ally, dict) else getattr(ally, "heading", getattr(ally, "_heading", 0.0)) or 0.0)
            heading_rad = math.radians(heading)
            for step, ttl in ((1, 4.0), (2, 2.5)):
                px = ax + math.cos(heading_rad) * self.model.grid_size * step
                py = ay + math.sin(heading_rad) * self.model.grid_size * step
                self.model.mark_ally_occupancy(self.model.to_cell(px, py), ttl=ttl)

    def _mark_enemy_occupancy(self, my_x: float, my_y: float, seen_enemies: List[Any]) -> None:
        """Oznacza komórki wrogów w WorldModel, aby A* omijał je przy planowaniu."""
        my_cell = self.model.to_cell(my_x, my_y)
        for enemy in seen_enemies:
            pos = enemy.get("position", enemy.get("_position", {})) if isinstance(enemy, dict) else getattr(enemy, "position", getattr(enemy, "_position", None))
            ex, ey = self._xy(pos)
            enemy_cell = self.model.to_cell(ex, ey)
            if enemy_cell == my_cell:
                continue

            self.model.mark_enemy_occupancy(enemy_cell, ttl=5.0)
            heading = float(enemy.get("heading", enemy.get("_heading", 0.0)) if isinstance(enemy, dict) else getattr(enemy, "heading", getattr(enemy, "_heading", 0.0)) or 0.0)
            heading_rad = math.radians(heading)
            for step, ttl in ((1, 4.0), (2, 2.5)):
                px = ex + math.cos(heading_rad) * self.model.grid_size * step
                py = ey + math.sin(heading_rad) * self.model.grid_size * step
                self.model.mark_enemy_occupancy(self.model.to_cell(px, py), ttl=ttl)

    def _update_world(
        self,
        my_x: float,
        my_y: float,
        sensor: Dict[str, Any],
        hp_ratio: float,
        ammo_stocks: Dict[str, int],
    ) -> None:
        me = self.model.to_cell(my_x, my_y)
        self.model.increment_visit(me)

        for obstacle in sensor.get("seen_obstacles", []):
            pos = obstacle.get("position", obstacle.get("_position", {})) if isinstance(obstacle, dict) else getattr(obstacle, "position", getattr(obstacle, "_position", None))
            ox, oy = self._xy(pos)
            obstacle_cell = self.model.to_cell(ox, oy)
            self.model.get_state(obstacle_cell).blocked += 1.5
            for nx, ny in (
                (obstacle_cell[0] + 1, obstacle_cell[1]),
                (obstacle_cell[0] - 1, obstacle_cell[1]),
                (obstacle_cell[0], obstacle_cell[1] + 1),
                (obstacle_cell[0], obstacle_cell[1] - 1),
            ):
                self.model.get_state((nx, ny)).blocked += 0.35

        self.model.pothole_cells = set()
        for terrain in sensor.get("seen_terrains", []):
            pos = terrain.get("position", terrain.get("_position", {})) if isinstance(terrain, dict) else getattr(terrain, "position", getattr(terrain, "_position", None))
            tx, ty = self._xy(pos)
            cell = self.model.to_cell(tx, ty)
            damage = self._terrain_damage(terrain)
            terrain_type = str(terrain.get("type", "")).lower() if isinstance(terrain, dict) else str(getattr(terrain, "terrain_type", getattr(terrain, "_terrain_type", ""))).lower()
            state = self.model.get_state(cell)
            if damage > 0:
                if "water" in terrain_type:
                    danger_boost = 3.4
                    state.danger += danger_boost
                    state.blocked += 0.25
                    # Water remains strongly repulsive.
                    for nx, ny in ((cell[0]+1, cell[1]), (cell[0]-1, cell[1]), (cell[0], cell[1]+1), (cell[0], cell[1]-1)):
                        nstate = self.model.get_state((nx, ny))
                        nstate.danger += 0.9
                        nstate.blocked += 0.18
                elif "pothole" in terrain_type:
                    self.model.pothole_cells.add(cell)
                    # PotholeRoad hurts, but should stay passable if it's the only lane.
                    state.danger = min(3.2, state.danger + 0.55)
                    for nx, ny in ((cell[0]+1, cell[1]), (cell[0]-1, cell[1]), (cell[0], cell[1]+1), (cell[0], cell[1]-1)):
                        nstate = self.model.get_state((nx, ny))
                        nstate.danger += 0.14
                else:
                    danger_boost = 1.3
                    state.danger += danger_boost
                    state.blocked += 0.22
                    for nx, ny in ((cell[0]+1, cell[1]), (cell[0]-1, cell[1]), (cell[0], cell[1]+1), (cell[0], cell[1]-1)):
                        nstate = self.model.get_state((nx, ny))
                        nstate.danger += 0.45
                        nstate.blocked += 0.08
            else:
                state.safe += 0.35

        # Powerupy – preferencja zależna od kontekstu (HP, ammo policy).
        self.model.powerup_cells = set()
        self.model.preferred_powerup_cells = set()
        for powerup in sensor.get("seen_powerups", []):
            pos = powerup.get("position", powerup.get("_position", {})) if isinstance(powerup, dict) else getattr(powerup, "position", getattr(powerup, "_position", None))
            px, py = self._xy(pos)
            powerup_cell = self.model.to_cell(px, py)
            self.model.powerup_cells.add(powerup_cell)
            ptxt = self._powerup_type_text(powerup)
            is_preferred = False
            if "medkit" in ptxt and hp_ratio <= 0.75:
                is_preferred = True
            elif "shield" in ptxt and hp_ratio <= 0.9:
                is_preferred = True
            elif "overcharge" in ptxt:
                is_preferred = True
            elif "ammo" in ptxt:
                wants_primary = (
                    ("long" in ptxt and self.preferred_ammo == "LONG_DISTANCE")
                    or ("light" in ptxt and self.preferred_ammo == "LIGHT")
                    or ("heavy" in ptxt and self.preferred_ammo == "HEAVY")
                )
                is_preferred = wants_primary or ammo_stocks.get(self.preferred_ammo, 0) <= 0

            if is_preferred:
                self.model.preferred_powerup_cells.add(powerup_cell)

    def _standing_on_danger(self, my_x: float, my_y: float, sensor: Dict[str, Any]) -> bool:
        if self._standing_on_live_hazard(my_x, my_y, sensor):
            return True

        me = self.model.to_cell(my_x, my_y)
        if self.model.get_state(me).danger >= 2.2:
            return True

        return False

    def _standing_on_live_hazard(self, my_x: float, my_y: float, sensor: Dict[str, Any]) -> bool:
        for terrain in sensor.get("seen_terrains", []):
            damage = self._terrain_damage(terrain)
            if damage <= 0:
                continue
            pos = terrain.get("position", terrain.get("_position", {})) if isinstance(terrain, dict) else getattr(terrain, "position", getattr(terrain, "_position", None))
            tx, ty = self._xy(pos)
            if euclidean_distance(my_x, my_y, tx, ty) <= self.model.grid_size * 0.8:
                return True
        return False

    def _enemy_in_firing_range(
        self,
        my_x: float,
        my_y: float,
        sensor: Dict[str, Any],
        firing_range: float,
    ) -> Optional[Tuple[float, float, float]]:
        """Zwraca najbliższego wroga w zasięgu strzału: (x, y, distance) lub None."""
        best: Optional[Tuple[float, float, float]] = None
        best_dist = firing_range + 1.0
        for tank in sensor.get("seen_tanks", []):
            pos = tank.get("position", tank.get("_position", {})) if isinstance(tank, dict) else getattr(tank, "position", getattr(tank, "_position", None))
            tx, ty = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, tx, ty)
            if dist <= firing_range and dist < best_dist:
                best_dist = dist
                best = (tx, ty, dist)
        return best

    def _closest_enemy(self, my_x: float, my_y: float, sensor: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
        best: Optional[Tuple[float, float, float]] = None
        best_dist = float("inf")
        for tank in sensor.get("seen_tanks", []):
            pos = tank.get("position", tank.get("_position", {})) if isinstance(tank, dict) else getattr(tank, "position", getattr(tank, "_position", None))
            tx, ty = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, tx, ty)
            if dist < best_dist:
                best_dist = dist
                best = (tx, ty, dist)
        return best

    def _ally_blocking_front(self, my_x: float, my_y: float, my_heading: float, allies: List[Any]) -> bool:
        return self._blocking_ally_id(my_x, my_y, my_heading, allies) is not None

    def _blocking_ally_id(self, my_x: float, my_y: float, my_heading: float, allies: List[Any]) -> Optional[str]:
        """Zwraca ID sojusznika blokującego przed nami, lub None."""
        for ally in allies:
            pos = ally.get("position", ally.get("_position", {})) if isinstance(ally, dict) else getattr(ally, "position", getattr(ally, "_position", None))
            ax, ay = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, ax, ay)
            if dist > 14.0:
                continue
            angle = heading_to_angle_deg(my_x, my_y, ax, ay)
            rel = abs(normalize_angle_diff(angle, my_heading))
            if rel <= 24.0:
                return str(ally.get("id", ally.get("_id", "")))
        return None

    def _enemy_blocking_front(self, my_x: float, my_y: float, my_heading: float, enemies: List[Any]) -> bool:
        """Sprawdza, czy wróg blokuje drogę przed nami."""
        for enemy in enemies:
            pos = enemy.get("position", enemy.get("_position", {})) if isinstance(enemy, dict) else getattr(enemy, "position", getattr(enemy, "_position", None))
            ex, ey = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, ex, ey)
            if dist > 14.0:
                continue
            angle = heading_to_angle_deg(my_x, my_y, ex, ey)
            rel = abs(normalize_angle_diff(angle, my_heading))
            if rel <= 24.0:
                return True
        return False

    def _get_checkpoints(self, team: int) -> List[Tuple[float, float]]:
        """Pobiera listę checkpointów dla zespołu (tworzy przy pierwszym wywołaniu)."""
        if team not in self.checkpoints_by_team:
            start_x = 41.0 if team == 1 else 181.0
            start_y = 41.0
            self.checkpoints_by_team[team] = build_checkpoints_to_enemy(
                team=team,
                start_x=start_x,
                start_y=start_y,
                map_width=200.0,
                map_height=200.0,
                map_filename="advanced_road_trees.csv",
            )
        return self.checkpoints_by_team[team]

    def _lane_adjusted_checkpoint(self, tank_id: str, checkpoint: Tuple[float, float]) -> Tuple[float, float]:
        return lane_offset_checkpoint(tank_id, checkpoint)

    @staticmethod
    def _ammo_stocks(my_tank_status: Dict[str, Any]) -> Dict[str, int]:
        stocks = {
            "LIGHT": 0,
            "HEAVY": 0,
            "LONG_DISTANCE": 0,
        }
        raw = my_tank_status.get("ammo_inventory")
        if isinstance(raw, dict):
            for key in stocks:
                stocks[key] = int(raw.get(key, 0) or 0)
            return stocks

        aliases = {
            "LIGHT": ("light_ammo", "_light_ammo", "ammo_light"),
            "HEAVY": ("heavy_ammo", "_heavy_ammo", "ammo_heavy"),
            "LONG_DISTANCE": ("long_distance_ammo", "_long_distance_ammo", "sniper_ammo", "_sniper_ammo", "ammo_long_distance"),
        }
        for key, names in aliases.items():
            for name in names:
                if name in my_tank_status:
                    stocks[key] = int(my_tank_status.get(name, 0) or 0)
                    break
        return stocks

    def _choose_ammo_to_load(self, my_tank_status: Dict[str, Any], enemy_close: bool) -> Optional[str]:
        ammo_loaded = str(my_tank_status.get("ammo_loaded", "") or "").upper()
        stocks = self._ammo_stocks(my_tank_status)
        preferred = self.preferred_ammo

        if ammo_loaded == preferred:
            return None
        if stocks.get(preferred, 0) > 0:
            return preferred

        if enemy_close:
            if stocks.get("LIGHT", 0) > 0 and ammo_loaded != "LIGHT":
                return "LIGHT"
            if stocks.get("HEAVY", 0) > 0 and ammo_loaded != "HEAVY":
                return "HEAVY"

        return None

    def _closest_destructible_obstacle(
        self,
        my_x: float,
        my_y: float,
        sensor: Dict[str, Any],
        max_dist: float = 45.0,
    ) -> Optional[Tuple[float, float, float]]:
        """Zwraca najbliższą zniszczalną przeszkodę (Tree itp.): (x, y, distance) lub None."""
        best: Optional[Tuple[float, float, float]] = None
        best_dist = max_dist + 1.0
        for obs in sensor.get("seen_obstacles", []):
            if not (obs.get("is_destructible", False) if isinstance(obs, dict) else getattr(obs, "is_destructible", False)):
                continue
            pos = obs.get("position", obs.get("_position", {})) if isinstance(obs, dict) else getattr(obs, "position", getattr(obs, "_position", None))
            ox, oy = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, ox, oy)
            if dist <= max_dist and dist < best_dist:
                best_dist = dist
                best = (ox, oy, dist)
        return best

    def _obstacle_blocks_route(self, ox: float, oy: float) -> bool:
        obstacle_cell = self.model.to_cell(ox, oy)
        if not self.driver.path:
            return False
        route_head = self.driver.path[:4]
        return obstacle_cell in route_head

    def _closest_powerup_position(self, my_x: float, my_y: float, sensor: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
        best: Optional[Tuple[float, float, float]] = None
        best_distance = float("inf")
        for powerup in sensor.get("seen_powerups", []):
            pos = powerup.get("position", powerup.get("_position", {})) if isinstance(powerup, dict) else getattr(powerup, "position", getattr(powerup, "_position", None))
            px, py = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, px, py)
            if dist < best_distance:
                best_distance = dist
                best = (px, py, dist)
        return best

    def _closest_non_hazard_point(self, my_x: float, my_y: float, sensor: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
        best: Optional[Tuple[float, float, float]] = None
        best_distance = float("inf")
        for terrain in sensor.get("seen_terrains", []):
            if self._terrain_damage(terrain) > 0:
                continue
            pos = terrain.get("position", terrain.get("_position", {})) if isinstance(terrain, dict) else getattr(terrain, "position", getattr(terrain, "_position", None))
            tx, ty = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, tx, ty)
            if dist < best_distance:
                best_distance = dist
                best = (tx, ty, dist)
        return best

    def _reactive_obstacle_avoidance(
        self,
        my_x: float,
        my_y: float,
        my_heading: float,
        top_speed: float,
        sensor: Dict[str, Any],
        seen_allies: Optional[List[Any]] = None,
    ) -> Optional[Tuple[float, float]]:
        best_threat = 0.0
        best_turn = 0.0

        for obstacle in sensor.get("seen_obstacles", []):
            pos = obstacle.get("position", obstacle.get("_position", {})) if isinstance(obstacle, dict) else getattr(obstacle, "position", getattr(obstacle, "_position", None))
            ox, oy = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, ox, oy)
            if dist > 22.0:
                continue

            obs_angle = heading_to_angle_deg(my_x, my_y, ox, oy)
            rel = normalize_angle_diff(obs_angle, my_heading)
            if abs(rel) > 42.0:
                continue

            threat = (22.0 - dist) + max(0.0, 42.0 - abs(rel)) * 0.08
            if threat > best_threat:
                best_threat = threat
                best_turn = -26.0 if rel >= 0 else 26.0
                blocked_cell = self.model.to_cell(ox, oy)
                self.model.get_state(blocked_cell).blocked += 1.25
                self.model.mark_dead_end(blocked_cell, ttl=540.0)

        # Treat visible tanks (allies + enemies) as obstacles to avoid collision deadlock
        all_tanks: List[Any] = list(seen_allies or [])
        all_tanks.extend(sensor.get("seen_tanks", []))
        for tank in all_tanks:
            pos = tank.get("position", tank.get("_position", {})) if isinstance(tank, dict) else getattr(tank, "position", getattr(tank, "_position", None))
            tx, ty = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, tx, ty)
            if dist > 18.0:
                continue

            tank_angle = heading_to_angle_deg(my_x, my_y, tx, ty)
            rel = normalize_angle_diff(tank_angle, my_heading)
            if abs(rel) > 45.0:
                continue

            threat = (18.0 - dist) + max(0.0, 45.0 - abs(rel)) * 0.06
            if threat > best_threat:
                best_threat = threat
                best_turn = -26.0 if rel >= 0 else 26.0
                blocked_cell = self.model.to_cell(tx, ty)
                self.model.get_state(blocked_cell).blocked += 0.9

        if best_threat > 0.0:
            return best_turn, max(0.5, top_speed * 0.3)
        return None

    def _update_path(self, my_x: float, my_y: float, goal: Goal, tick: int) -> None:
        start = self.model.to_cell(my_x, my_y)
        need_replan = self.current_goal is None or self.current_goal.cell != goal.cell or tick >= self.replan_tick or not self.driver.path

        if need_replan:
            self.driver.path = self.planner.build_path(start, goal.cell)
            self.replan_tick = tick + 20
            self.current_goal = goal

            if goal.mode == "attack":
                risk = self.planner.path_risk(self.driver.path)
                if risk > 1.4:
                    self.driver.path = []
                    self.current_goal = None

        while self.driver.path:
            wx, wy = self.model.to_world_center(self.driver.path[0])
            if euclidean_distance(my_x, my_y, wx, wy) < 2.5:
                self.driver.path.pop(0)
            else:
                break

    def _escape_target_cell(self, my_cell: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        for radius, require_known in ((10, True), (14, True), (18, False), (24, False)):
            safe_cell = self.goal_selector.nearest_safe_cell(my_cell, radius=radius, require_known=require_known)
            if safe_cell is not None and safe_cell != my_cell:
                return safe_cell

        candidate = self.driver.best_immediate_safe_neighbor(my_cell, allow_risky=True)
        if candidate is not None and candidate != my_cell:
            return candidate
        return None

    def _important_sensor_event(
        self,
        *,
        standing_on_danger: bool,
        enemies_visible: bool,
        hp_lost: float,
        stuck_triggered: bool,
        sensor: Dict[str, Any],
        my_x: float,
        my_y: float,
    ) -> bool:
        # Immediate danger / stuck are always important
        if standing_on_danger or stuck_triggered:
            return True

        # Treat visible enemies as important only when not in an explore route-commit
        # or when they are very close / multiple. This lets an exploring agent "spot"
        # enemies without immediately switching to full attack (reduces accidental fights).
        if enemies_visible:
            ENGAGE_VISIBLE_DISTANCE = 6.0  # very close => treat as immediate threat
            close_enemies = 0
            for t in sensor.get("seen_tanks", []):
                tx, ty = self._xy(t.get("position", t.get("_position", {}))) if isinstance(t, dict) else (getattr(t, "position").x, getattr(t, "position").y)
                if euclidean_distance(my_x, my_y, tx, ty) <= ENGAGE_VISIBLE_DISTANCE:
                    close_enemies += 1
            # If agent is currently committed to explore, ignore distant sightings
            if self.route_commit_mode and "explore" in self.route_commit_mode:
                if close_enemies >= 1:
                    return True
            else:
                # not exploring -> any visible enemy is important
                return True

        if hp_lost > 0.35:
            return True

        near_threat = 0
        for obstacle in sensor.get("seen_obstacles", []):
            pos = obstacle.get("position", obstacle.get("_position", {})) if isinstance(obstacle, dict) else getattr(obstacle, "position", getattr(obstacle, "_position", None))
            ox, oy = self._xy(pos)
            if euclidean_distance(my_x, my_y, ox, oy) <= 14.0:
                near_threat += 1
                if near_threat >= 2:
                    return True
        return False

    def _begin_route_commit(self, tick: int, goal_mode: str) -> None:
        # Keep a longer route-commit for exploration/control lanes so agent doesn't
        # constantly replan and oscillate — interruption still happens on danger/events.
        duration = 42
        if goal_mode in ("explore", "control_lane"):
            duration = 120  # longer commitment for smooth exploration
        elif goal_mode in ("collect_powerup", "collect_medkit", "pickup_now"):
            duration = 32
        elif goal_mode in ("attack", "attack_standoff"):
            duration = 24
        self.route_commit_until = tick + duration
        self.route_commit_mode = goal_mode

    def _clear_route_commit(self) -> None:
        self.route_commit_until = 0
        self.route_commit_mode = ""

    def _local_probe_goal(self, my_cell: Tuple[int, int]) -> Optional[Goal]:
        best_cell: Optional[Tuple[int, int]] = None
        best_score = -1e9

        for radius in (1, 2, 3, 4):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    dist = abs(dx) + abs(dy)
                    if dist != radius:
                        continue
                    cell = (my_cell[0] + dx, my_cell[1] + dy)
                    if cell == my_cell:
                        continue
                    if self.model.is_blocked_for_pathing(cell):
                        continue

                    was_known = cell in self.model.cell_states
                    state = self.model.get_state(cell)
                    visits = self.model.visit_counts.get(cell, 0)
                    unknown_bonus = 2.4 if not was_known else 0.0

                    score = (
                        unknown_bonus
                        + 1.1 * state.safe
                        - 2.8 * state.danger
                        - 2.4 * state.blocked
                        - 0.28 * visits
                        - 0.14 * dist
                    )
                    if score > best_score:
                        best_score = score
                        best_cell = cell

            if best_cell is not None:
                break

        if best_cell is None:
            fallback = self.driver.best_immediate_safe_neighbor(my_cell, allow_risky=True)
            if fallback is None:
                return None
            best_cell = fallback

        return Goal(best_cell, "local_probe", 260.0)

    def _movement_risk_score(
        self,
        my_x: float,
        my_y: float,
        my_heading: float,
        turn: float,
        speed: float,
        sensor: Dict[str, Any],
    ) -> float:
        predicted_heading = (my_heading + turn * 0.65) % 360.0
        heading_rad = math.radians(predicted_heading)

        look_steps = (2.2, 4.2, 6.8)
        risk = 0.0

        for dist_forward in look_steps:
            px = my_x + math.cos(heading_rad) * dist_forward
            py = my_y + math.sin(heading_rad) * dist_forward
            cell = self.model.to_cell(px, py)
            state = self.model.get_state(cell)
            risk += 0.55 * state.danger + 0.65 * state.blocked
            risk += 1.1 * self.model.ally_occupancy_score(cell)
            if self.model.is_blocked_for_pathing(cell):
                risk += 3.5

        cone_width = 58.0 if speed > 1.0 else 44.0
        max_probe = 18.0 if speed > 0.5 else 12.0

        for obstacle in sensor.get("seen_obstacles", []):
            pos = obstacle.get("position", obstacle.get("_position", {})) if isinstance(obstacle, dict) else getattr(obstacle, "position", getattr(obstacle, "_position", None))
            ox, oy = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, ox, oy)
            if dist > max_probe:
                continue
            angle = heading_to_angle_deg(my_x, my_y, ox, oy)
            rel = abs(normalize_angle_diff(angle, predicted_heading))
            if rel > cone_width:
                continue
            risk += max(0.0, (max_probe - dist) * 0.33) + max(0.0, (cone_width - rel) * 0.03)

        for terrain in sensor.get("seen_terrains", []):
            damage = self._terrain_damage(terrain)
            if damage <= 0:
                continue
            pos = terrain.get("position", terrain.get("_position", {})) if isinstance(terrain, dict) else getattr(terrain, "position", getattr(terrain, "_position", None))
            tx, ty = self._xy(pos)
            dist = euclidean_distance(my_x, my_y, tx, ty)
            if dist > 16.0:
                continue
            angle = heading_to_angle_deg(my_x, my_y, tx, ty)
            rel = abs(normalize_angle_diff(angle, predicted_heading))
            if rel > 62.0:
                continue
            risk += max(0.0, (16.0 - dist) * 0.18) + max(0.0, (62.0 - rel) * 0.015)

        if speed < 0.1:
            risk += 0.35

        return risk

    def _self_preserving_command(
        self,
        my_x: float,
        my_y: float,
        my_heading: float,
        turn: float,
        speed: float,
        sensor: Dict[str, Any],
        max_heading: float,
        top_speed: float,
    ) -> Tuple[float, float]:
        base_turn = self._clamp(turn, -max_heading, max_heading)
        base_speed = self._clamp(speed, -top_speed, top_speed)
        base_risk = self._movement_risk_score(my_x, my_y, my_heading, base_turn, base_speed, sensor)

        turn_offsets = (0.0, 16.0, -16.0, 30.0, -30.0, 44.0, -44.0)
        speed_scales = (1.0, 0.8, 0.6, 0.42)

        best = (base_turn, base_speed)
        best_score = base_risk

        HYSTERESIS = 0.12  # require noticeable improvement to switch to a different maneuver

        for t_off in turn_offsets:
            candidate_turn = self._clamp(base_turn + t_off, -max_heading, max_heading)
            for scale in speed_scales:
                candidate_speed = self._clamp(base_speed * scale, -top_speed, top_speed)
                risk = self._movement_risk_score(my_x, my_y, my_heading, candidate_turn, candidate_speed, sensor)
                score = (
                    risk
                    + 0.018 * abs(candidate_turn - base_turn)
                    + 0.22 * abs(candidate_speed - base_speed)
                    - 0.07 * max(0.0, candidate_speed)
                )
                # adopt candidate only if it's clearly better than current best (hysteresis)
                if score < best_score - HYSTERESIS:
                    best_score = score
                    best = (candidate_turn, candidate_speed)

        if base_risk < 1.6:
            return base_turn, base_speed
        return best

    def _stabilize_direction_and_speed(
        self,
        *,
        current_tick: int,
        mode: str,
        standing_on_danger: bool,
        enemies_visible: bool,
        my_x: float,
        my_y: float,
        my_heading: float,
        sensor: Dict[str, Any],
        top_speed: float,
        turn: float,
        speed: float,
    ) -> Tuple[float, float]:
        stable_mode = (
            not standing_on_danger
            and not enemies_visible
            and not mode.startswith("emergency")
            and not mode.startswith("avoid")
            and not mode.startswith("attack")
            and not mode.startswith("unblock")
        )

        if not stable_mode:
            self.last_turn_cmd = turn
            self.last_mode = mode
            return turn, speed

        previous_turn = self.last_turn_cmd
        max_turn_delta = 3.6
        turn = previous_turn + self._clamp(turn - previous_turn, -max_turn_delta, max_turn_delta)

        if abs(turn) < 2.2:
            turn = 0.0

        sign_changed = (turn > 0 > previous_turn) or (turn < 0 < previous_turn)
        if sign_changed:
            if current_tick - self.last_turn_flip_tick < 58 and abs(turn) < 11.0 and abs(previous_turn) > 2.5:
                turn = math.copysign(max(2.0, abs(turn)), previous_turn)
            else:
                self.last_turn_flip_tick = current_tick

        risk = self._movement_risk_score(my_x, my_y, my_heading, turn, speed, sensor)
        ally_pressure = self.model.ally_occupancy_score(self.model.to_cell(my_x, my_y))
        cruise_mode = mode.startswith("route_commit") or mode.startswith("checkpoint") or mode in ("control_lane", "explore", "local_probe", "patrol")
        if cruise_mode and risk < 1.35 and ally_pressure < 0.2:
            if abs(turn) <= 8.0:
                speed = max(speed, top_speed * 0.86)
            else:
                speed = max(speed, top_speed * 0.72)
        elif ally_pressure >= 0.2:
            speed = min(speed, top_speed * 0.62)

        self.last_turn_cmd = turn
        self.last_mode = mode
        return turn, speed

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(value, hi))

    def get_action(
        self,
        current_tick: int,
        my_tank_status: Dict[str, Any],
        sensor_data: Dict[str, Any],
        enemies_remaining: int,
    ) -> ActionCommand:
        my_x, my_y = self._xy(my_tank_status.get("position", {}))
        my_heading = float(my_tank_status.get("heading", 0.0) or 0.0)
        my_team = my_tank_status.get("_team")
        print(f'{my_team=} {my_x=} {my_y=}')

        hp = float(my_tank_status.get("hp", 100.0) or 100.0)
        max_hp = float(my_tank_status.get("_max_hp", 100.0) or 100.0)
        hp_ratio = hp / max_hp if max_hp > 0 else 0.0
        self.my_tank_id = str(my_tank_status.get("_id", "default"))

        top_speed = float(my_tank_status.get("_top_speed", 3.0) or 3.0)
        max_heading = float(my_tank_status.get("_heading_spin_rate", 30.0) or 30.0)
        max_barrel = float(my_tank_status.get("_barrel_spin_rate", 30.0) or 30.0)
        barrel_angle = float(my_tank_status.get("barrel_angle", 0.0) or 0.0)
        vision_range = float(my_tank_status.get("_vision_range", 70.0) or 70.0)

        # Lazy initialization of fuzzy turret controller with tank-specific capabilities
        if self.turret is None:
            self.turret = FuzzyTurretController(
                max_barrel_spin_rate=max_barrel,
                vision_range=vision_range,
                aim_threshold=2.5,
            )

        sensor = dict(sensor_data)
        seen_tanks = sensor_data.get("seen_tanks", [])
        seen_allies: List[Any] = []
        if my_team is not None:
            seen_allies = [tank for tank in seen_tanks if tank.get("team") == my_team and str(tank.get("id", tank.get("_id", ""))) != self.my_tank_id]
            sensor["seen_tanks"] = [tank for tank in seen_tanks if tank.get("team") is None or tank.get("team") != my_team]
        else:
            sensor["seen_tanks"] = seen_tanks

        ammo_stocks = self._ammo_stocks(my_tank_status)
        self.model.decay_dead_ends()
        self._mark_allies_occupancy(my_x, my_y, seen_allies)
        self._mark_enemy_occupancy(my_x, my_y, sensor.get("seen_tanks", []))
        self._update_world(my_x, my_y, sensor, hp_ratio, ammo_stocks)

        enemies_visible = len(sensor.get("seen_tanks", [])) > 0
        ally_blocking_front = self._ally_blocking_front(my_x, my_y, my_heading, seen_allies)
        enemy_blocking_front = self._enemy_blocking_front(my_x, my_y, my_heading, sensor.get("seen_tanks", []))
        enemy_close = self._closest_enemy(my_x, my_y, sensor)
        ammo_to_load = self._choose_ammo_to_load(my_tank_status, enemy_close is not None and enemy_close[2] <= 22.0)
        blocking_tank_in_front = ally_blocking_front or enemy_blocking_front
        stuck_triggered = self.driver.update_stuck(
            my_x, my_y, enemies_visible, my_heading, blocking_tank_in_front=blocking_tank_in_front
        )

        hp_lost = 0.0
        if self.last_hp is not None:
            hp_lost = self.last_hp - hp
            if (
                not DISABLE_ESCAPE_MODE
                and 0.01 < hp_lost <= 12.0
                and not enemies_visible
            ):
                cell = self.model.to_cell(my_x, my_y)
                self.model.get_state(cell).danger += 3.0
                self.model.mark_dead_end(cell, ttl=600.0)
                self.driver.start_escape(my_heading, force_new=hp_lost >= 8.0)
        self.last_hp = hp

        mode = "idle"
        my_cell = self.model.to_cell(my_x, my_y)
        if self.last_cell is not None and my_cell != self.last_cell:
            self.consecutive_danger_ticks = max(0, self.consecutive_danger_ticks - 4)

        live_hazard_now = self._standing_on_live_hazard(my_x, my_y, sensor)
        standing_on_danger = live_hazard_now or self._standing_on_danger(my_x, my_y, sensor)
        if standing_on_danger and not DISABLE_ESCAPE_MODE:
            self.consecutive_danger_ticks += 1
            cell = self.model.to_cell(my_x, my_y)
            self.model.get_state(cell).danger += 2.0
            if current_tick - self.last_danger_mark_tick >= 18:
                self.model.mark_dead_end(cell, ttl=460.0)
                self.last_danger_mark_tick = current_tick
            self.driver.start_escape(my_heading)
            self._clear_route_commit()
        else:
            self.consecutive_danger_ticks = 0

        if (
            not DISABLE_ESCAPE_MODE
            and self.driver.escape_ticks > 0
            and enemies_visible
            and not self._standing_on_live_hazard(my_x, my_y, sensor)
            and hp_ratio >= 0.52
        ):
            self.driver.escape_ticks = 0
            self.driver.escape_heading = None
            self.driver.path = []
            self.current_goal = None
            self._clear_route_commit()
            standing_on_danger = False

        # Zawsze oblicz unikanie przeszkód i czołgów (potrzebne do niszczenia blokad i unikania deadlocku)
        obstacle_avoid = self._reactive_obstacle_avoidance(my_x, my_y, my_heading, top_speed, sensor, seen_allies=seen_allies)

        if live_hazard_now:
            safe_patch = self._closest_non_hazard_point(my_x, my_y, sensor)
            if safe_patch is not None and safe_patch[2] <= 34.0:
                turn, speed = self.driver.drive_to_point(my_x, my_y, my_heading, safe_patch[0], safe_patch[1], top_speed)
            elif obstacle_avoid is not None:
                turn, speed = obstacle_avoid
            else:
                push_cell = self.driver.best_immediate_safe_neighbor(my_cell, allow_risky=True)
                if push_cell is not None and push_cell != my_cell:
                    turn, speed = self.driver.drive_to_cell(my_x, my_y, my_heading, push_cell, top_speed)
                else:
                    turn, speed = self.driver.escape_drive(my_x, my_y, my_heading, top_speed)
            speed = max(speed, top_speed * 0.92)
            mode = "panic_hazard_escape"
        elif not DISABLE_ESCAPE_MODE and self.driver.escape_ticks > 0:
            escape_goal_cell = self._escape_target_cell(my_cell)
            if escape_goal_cell is not None and escape_goal_cell != self.model.to_cell(my_x, my_y):
                self.current_goal = Goal(escape_goal_cell, "escape_route", 999.0)
                if not self.driver.path or (self.driver.path and self.driver.path[-1] != escape_goal_cell) or current_tick >= self.replan_tick:
                    self.driver.path = self.planner.build_path(my_cell, escape_goal_cell, radius=26)
                    self.replan_tick = current_tick + 8
                while self.driver.path:
                    wx, wy = self.model.to_world_center(self.driver.path[0])
                    if euclidean_distance(my_x, my_y, wx, wy) < 2.5:
                        self.driver.path.pop(0)
                    else:
                        break

            if obstacle_avoid is not None:
                turn, speed = obstacle_avoid
                mode = "emergency_escape_avoid"
            elif self.driver.path:
                turn, speed = self.driver.drive_path(my_x, my_y, my_heading, top_speed)
                mode = "emergency_escape_route"
            else:
                turn, speed = self.driver.escape_drive(my_x, my_y, my_heading, top_speed)
                mode = "emergency_escape"

            if standing_on_danger and self.consecutive_danger_ticks >= 8:
                safe_patch = self._closest_non_hazard_point(my_x, my_y, sensor)
                if safe_patch is not None and safe_patch[2] <= 28.0:
                    turn, speed = self.driver.drive_to_point(my_x, my_y, my_heading, safe_patch[0], safe_patch[1], top_speed)
                    speed = max(speed, top_speed * 0.72)
                    mode = "emergency_to_safe_patch"

            if standing_on_danger and self.consecutive_danger_ticks >= 26:
                push_cell = self.driver.best_immediate_safe_neighbor(my_cell, allow_risky=True)
                if push_cell is not None and push_cell != my_cell:
                    turn, speed = self.driver.drive_to_cell(my_x, my_y, my_heading, push_cell, top_speed)
                    speed = max(speed, top_speed * 0.68)
                    mode = "emergency_push_out"
        else:
            # Combat-first: engage in range, intercept when visible, checkpoint advance otherwise.
            # Deadlock unblock: cofnij się gdy zablokowany przez inny czołg (ally lub enemy)
            should_unblock = False
            if stuck_triggered and (ally_blocking_front or enemy_blocking_front):
                if ally_blocking_front:
                    blocking_id = self._blocking_ally_id(my_x, my_y, my_heading, seen_allies)
                    if blocking_id is not None and self.my_tank_id < blocking_id:
                        should_unblock = True
                elif enemy_blocking_front:
                    should_unblock = True
            if should_unblock:
                self.driver.start_unblock()

            ammo_loaded = my_tank_status.get("ammo_loaded")
            firing_range = get_firing_range(ammo_loaded)
            enemy_in_range = self._enemy_in_firing_range(my_x, my_y, sensor, firing_range)
            closest_enemy = self._closest_enemy(my_x, my_y, sensor)

            if self.driver.unblock_ticks > 0:
                turn, speed = self.driver.unblock_drive(top_speed, add_turn=enemy_blocking_front)
                mode = "unblock"
                self.driver.path = []
                self.current_goal = None
            elif obstacle_avoid is not None:
                turn, speed = obstacle_avoid
                mode = "avoid_wall"
                self.driver.path = []
                self.current_goal = None
                self._clear_route_commit()
            elif enemy_in_range:
                mode = "engage_visible"
                ex, ey, _ = enemy_in_range
                turn, _ = self.driver.drive_to_point(my_x, my_y, my_heading, ex, ey, top_speed)
                speed = top_speed * 0.25
                self.driver.path = []
                self.current_goal = None
            elif closest_enemy is not None:
                ex, ey, _ = closest_enemy
                enemy_goal_cell = self.model.to_cell(ex, ey)
                intercept_goal = Goal(enemy_goal_cell, "intercept_enemy", 980.0)
                need_replan = (
                    not self.driver.path
                    or self.current_goal is None
                    or self.current_goal.cell != enemy_goal_cell
                    or current_tick >= self.replan_tick
                    or stuck_triggered
                )
                if need_replan:
                    self.driver.path = self.planner.build_path(my_cell, enemy_goal_cell, radius=30)
                    self.replan_tick = current_tick + 8
                    self.current_goal = intercept_goal
                while self.driver.path:
                    wx, wy = self.model.to_world_center(self.driver.path[0])
                    if euclidean_distance(my_x, my_y, wx, wy) < 2.5:
                        self.driver.path.pop(0)
                    else:
                        break
                if self.driver.path:
                    turn, speed = self.driver.drive_path(my_x, my_y, my_heading, top_speed)
                else:
                    turn, speed = self.driver.drive_to_point(my_x, my_y, my_heading, ex, ey, top_speed)
                mode = "intercept_enemy"
            else:
                # Jedź wzdłuż checkpointów do wrogiej armii (lista per zespół, indeks per czołg)
                tank_id = self.my_tank_id
                team = my_team if my_team is not None else 1
                checkpoints = self._get_checkpoints(team)
                idx = self.checkpoint_index_by_tank.get(tank_id, -1)
                if idx < 0 and checkpoints:
                    idx = min(
                        range(len(checkpoints)),
                        key=lambda i: euclidean_distance(my_x, my_y, checkpoints[i][0], checkpoints[i][1]),
                    )
                    self.checkpoint_index_by_tank[tank_id] = idx

                # Przejdź do następnego checkpointu jeśli dotarliśmy
                while idx < len(checkpoints):
                    cx, cy = checkpoints[idx]
                    if euclidean_distance(my_x, my_y, cx, cy) < self.checkpoint_arrival_radius:
                        idx += 1
                        self.checkpoint_index_by_tank[tank_id] = idx
                    else:
                        break

                if idx >= len(checkpoints):
                    # Wszystkie checkpointy przejechane - jedź do ostatniego (głęboko w strefie wroga)
                    idx = len(checkpoints) - 1
                    self.checkpoint_index_by_tank[tank_id] = idx

                if idx < len(checkpoints):
                    cx, cy = self._lane_adjusted_checkpoint(tank_id, checkpoints[idx])
                    goal_cell = self.model.to_cell(cx, cy)
                    goal = Goal(goal_cell, "checkpoint", 999.0)
                    # Checkpointy – A* preferuje ścieżki przez korytarz (obecny + następne 2)
                    self.model.checkpoint_cells = set()
                    for i in range(idx, min(idx + 3, len(checkpoints))):
                        cxi, cyi = self._lane_adjusted_checkpoint(tank_id, checkpoints[i])
                        self.model.checkpoint_cells.add(self.model.to_cell(cxi, cyi))
                    # Planowanie A* – omija przeszkody, preferuje powerupy i checkpointy
                    need_replan = (
                        not self.driver.path
                        or self.current_goal is None
                        or self.current_goal.cell != goal_cell
                        or current_tick >= self.replan_tick
                        or stuck_triggered
                    )
                    if need_replan:
                        self.driver.path = self.planner.build_path(my_cell, goal_cell, radius=28)
                        self.replan_tick = current_tick + 15
                        self.current_goal = goal
                    # Usuń osiągnięte komórki ze ścieżki
                    while self.driver.path:
                        wx, wy = self.model.to_world_center(self.driver.path[0])
                        if euclidean_distance(my_x, my_y, wx, wy) < 2.5:
                            self.driver.path.pop(0)
                        else:
                            break
                    if self.driver.path:
                        turn, speed = self.driver.drive_path(my_x, my_y, my_heading, top_speed)
                    else:
                        turn, speed = self.driver.drive_to_point(my_x, my_y, my_heading, cx, cy, top_speed)
                    if self.model.ally_occupancy_score(goal_cell) >= 0.2:
                        speed = min(speed, top_speed * 0.55)
                        mode = f"checkpoint_yield_{idx + 1}/{len(checkpoints)}"
                    else:
                        mode = f"checkpoint_{idx + 1}/{len(checkpoints)}"
                else:
                    turn, speed = 0.0, top_speed * 0.5
                    mode = "patrol"

        barrel_rotation, should_fire, _ = self.turret.update(
            my_x=my_x,
            my_y=my_y,
            my_heading=my_heading,
            current_barrel_angle=barrel_angle,
            seen_tanks=sensor.get("seen_tanks", []),
            max_barrel_rotation=max_barrel,
            ammo_stocks=ammo_stocks,
            current_ammo=str(my_tank_status.get("ammo_loaded", "") or "").upper() or None,
            seen_obstacles=sensor.get("seen_obstacles", []),
        )

        ammo_loaded = my_tank_status.get("ammo_loaded")
        firing_range = get_firing_range(ammo_loaded)
        enemy_in_range = self._enemy_in_firing_range(my_x, my_y, sensor, firing_range)

        # Gdy brak wrogów w zasięgu: niszcz zniszczalne przeszkody (drzewa, skrzynie) gdy blokują drogę
        destructible = self._closest_destructible_obstacle(my_x, my_y, sensor, max_dist=firing_range)
        obstacles_nearby = len(sensor.get("seen_obstacles", [])) >= 1
        clear_path_needed = (
            obstacle_avoid is not None
            or stuck_triggered
            or (
                destructible is not None
                and destructible[2] < 35.0
                and obstacles_nearby
                and self._obstacle_blocks_route(destructible[0], destructible[1])
            )
        )
        if not enemy_in_range and destructible is not None and clear_path_needed:
            ox, oy, _ = destructible
            abs_angle = heading_to_angle_deg(my_x, my_y, ox, oy)
            rel_angle = normalize_angle_diff(abs_angle, my_heading)
            aim_error = normalize_angle_diff(rel_angle, barrel_angle)
            barrel_rotation = self._clamp(aim_error, -max_barrel, max_barrel)
            should_fire = abs(aim_error) <= 4.0
        elif not enemy_in_range:
            should_fire = False

        ammo_loaded_now = str(my_tank_status.get("ammo_loaded", "") or "").upper()
        if enemy_in_range and ammo_loaded_now == "LONG_DISTANCE":
            # At long range prefer tighter alignment to limit wasted sniper shots.
            should_fire = should_fire and abs(barrel_rotation) <= 3.0

        if ally_blocking_front and not live_hazard_now:
            speed = min(speed, top_speed * 0.52)
            if mode.startswith("checkpoint") or mode == "patrol":
                mode = "yield_ally"

        turn, speed = self._self_preserving_command(
            my_x=my_x,
            my_y=my_y,
            my_heading=my_heading,
            turn=turn,
            speed=speed,
            sensor=sensor,
            max_heading=max_heading,
            top_speed=top_speed,
        )

        turn, speed = self._stabilize_direction_and_speed(
            current_tick=current_tick,
            mode=mode,
            standing_on_danger=standing_on_danger,
            enemies_visible=enemies_visible,
            my_x=my_x,
            my_y=my_y,
            my_heading=my_heading,
            sensor=sensor,
            top_speed=top_speed,
            turn=turn,
            speed=speed,
        )

        if live_hazard_now:
            # Panic mode: prioritize leaving damaging terrain over cruise smoothing.
            speed = max(speed, top_speed * 0.92)

        turn = self._clamp(turn, -max_heading, max_heading)
        speed = self._clamp(speed, -top_speed, top_speed)  # Ujemna prędkość = cofanie (tryb unblock)
        barrel_rotation = self._clamp(barrel_rotation, -max_barrel, max_barrel)
        self.driver.last_move_cmd = speed
        self.last_cell = my_cell

        if current_tick % 60 == 0:
            goal_txt = self.current_goal.cell if self.current_goal else None
            print(
                f"[{self.name}] tick={current_tick} mode={mode} hp={hp:.1f}/{max_hp:.1f} "
                f"goal={goal_txt} path={len(self.driver.path)} speed={speed:.2f} turn={turn:.2f}"
            )

        return ActionCommand(
            barrel_rotation_angle=barrel_rotation,
            heading_rotation_angle=turn,
            move_speed=speed,
            ammo_to_load=ammo_to_load,
            should_fire=should_fire,
        )

    def destroy(self):
        self.is_destroyed = True
        print(f"[{self.name}] destroyed")

    def end(self, damage_dealt: float, tanks_killed: int):
        print(f"[{self.name}] end damage={damage_dealt} kills={tanks_killed}")
