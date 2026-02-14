from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from .driver import MotionDriver
from .geometry import euclidean_distance, to_xy
from .goal_selector import Goal, GoalSelector
from .planner import AStarPlanner
from .turret import SimpleTurretController
from .world_model import WorldModel


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
        self.turret = SimpleTurretController(scan_speed=22.0, track_speed=36.0, aim_threshold=3.0)

        self.current_goal: Optional[Goal] = None
        self.replan_tick: int = 0
        self.last_hp: Optional[float] = None

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

    def _update_world(self, my_x: float, my_y: float, sensor: Dict[str, Any]) -> None:
        me = self.model.to_cell(my_x, my_y)
        self.model.increment_visit(me)

        for obstacle in sensor.get("seen_obstacles", []):
            pos = obstacle.get("position", obstacle.get("_position", {})) if isinstance(obstacle, dict) else getattr(obstacle, "position", getattr(obstacle, "_position", None))
            ox, oy = self._xy(pos)
            self.model.get_state(self.model.to_cell(ox, oy)).blocked += 1.0

        for terrain in sensor.get("seen_terrains", []):
            pos = terrain.get("position", terrain.get("_position", {})) if isinstance(terrain, dict) else getattr(terrain, "position", getattr(terrain, "_position", None))
            tx, ty = self._xy(pos)
            cell = self.model.to_cell(tx, ty)
            damage = self._terrain_damage(terrain)
            terrain_type = str(terrain.get("type", "")).lower() if isinstance(terrain, dict) else str(getattr(terrain, "terrain_type", getattr(terrain, "_terrain_type", ""))).lower()
            state = self.model.get_state(cell)
            if damage > 0:
                danger_boost = 2.5 if ("water" in terrain_type or "pothole" in terrain_type) else 1.3
                state.danger += danger_boost
                state.blocked += 0.8
            else:
                state.safe += 0.35

    def _standing_on_danger(self, my_x: float, my_y: float, sensor: Dict[str, Any]) -> bool:
        me = self.model.to_cell(my_x, my_y)
        if self.model.get_state(me).danger >= 1.0:
            return True

        for terrain in sensor.get("seen_terrains", []):
            damage = self._terrain_damage(terrain)
            if damage <= 0:
                continue
            pos = terrain.get("position", terrain.get("_position", {})) if isinstance(terrain, dict) else getattr(terrain, "position", getattr(terrain, "_position", None))
            tx, ty = self._xy(pos)
            if euclidean_distance(my_x, my_y, tx, ty) <= self.model.grid_size * 0.8:
                return True
        return False

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

        hp = float(my_tank_status.get("hp", 100.0) or 100.0)
        max_hp = float(my_tank_status.get("_max_hp", 100.0) or 100.0)
        hp_ratio = hp / max_hp if max_hp > 0 else 0.0

        top_speed = float(my_tank_status.get("_top_speed", 3.0) or 3.0)
        max_heading = float(my_tank_status.get("_heading_spin_rate", 30.0) or 30.0)
        max_barrel = float(my_tank_status.get("_barrel_spin_rate", 30.0) or 30.0)
        barrel_angle = float(my_tank_status.get("barrel_angle", 0.0) or 0.0)

        sensor = dict(sensor_data)
        seen_tanks = sensor_data.get("seen_tanks", [])
        if my_team is not None:
            sensor["seen_tanks"] = [tank for tank in seen_tanks if tank.get("team") is None or tank.get("team") != my_team]
        else:
            sensor["seen_tanks"] = seen_tanks

        self.model.decay_dead_ends()
        self._update_world(my_x, my_y, sensor)

        enemies_visible = len(sensor.get("seen_tanks", [])) > 0
        self.driver.update_stuck(my_x, my_y, enemies_visible, my_heading)

        if self.last_hp is not None:
            hp_lost = self.last_hp - hp
            if 0.01 < hp_lost < 5.0 and not enemies_visible:
                cell = self.model.to_cell(my_x, my_y)
                self.model.get_state(cell).danger += 3.0
                self.model.mark_dead_end(cell, ttl=600.0)
                self.driver.start_escape(my_heading)
        self.last_hp = hp

        mode = "idle"
        if self._standing_on_danger(my_x, my_y, sensor):
            cell = self.model.to_cell(my_x, my_y)
            self.model.get_state(cell).danger += 2.0
            self.model.mark_dead_end(cell, ttl=600.0)
            self.driver.start_escape(my_heading)

        if self.driver.escape_ticks > 0:
            self.driver.path = []
            self.current_goal = None
            turn, speed = self.driver.escape_drive(my_x, my_y, my_heading, top_speed)
            mode = "emergency_escape"
        else:
            near_powerup = self._closest_powerup_position(my_x, my_y, sensor)
            if near_powerup is not None and near_powerup[2] <= 15.0 and not self._standing_on_danger(my_x, my_y, sensor):
                turn, speed = self.driver.drive_to_point(my_x, my_y, my_heading, near_powerup[0], near_powerup[1], top_speed)
                mode = "pickup_direct"
                self.driver.path = []
                self.current_goal = None
            else:
                goal = self.goal_selector.choose_goal(
                    my_x=my_x,
                    my_y=my_y,
                    hp_ratio=hp_ratio,
                    sensor=sensor,
                    standing_on_danger_fn=self._standing_on_danger,
                    to_cell_fn=lambda mode, pos: self._xy(pos),
                    powerup_type_fn=self._powerup_type_text,
                )
                if goal is not None:
                    self._update_path(my_x, my_y, goal, current_tick)
                    if goal.mode == "attack" and not self.driver.path:
                        safe = self.goal_selector.nearest_safe_cell(self.model.to_cell(my_x, my_y))
                        if safe is not None:
                            safe_goal = Goal(safe, "reposition_safe", 650.0)
                            self._update_path(my_x, my_y, safe_goal, current_tick)
                            goal = safe_goal
                    mode = goal.mode

                turn, speed = self.driver.drive_path(my_x, my_y, my_heading, top_speed)

                if goal is not None and not self.driver.path:
                    turn, speed = self.driver.drive_to_cell(my_x, my_y, my_heading, goal.cell, top_speed)
                    mode = f"{mode}_direct"

        barrel_rotation, should_fire = self.turret.update(
            my_x=my_x,
            my_y=my_y,
            my_heading=my_heading,
            current_barrel_angle=barrel_angle,
            seen_tanks=sensor.get("seen_tanks", []),
            max_barrel_rotation=max_barrel,
        )

        turn = self._clamp(turn, -max_heading, max_heading)
        speed = self._clamp(speed, -top_speed, top_speed)
        barrel_rotation = self._clamp(barrel_rotation, -max_barrel, max_barrel)
        self.driver.last_move_cmd = speed

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
            should_fire=should_fire,
        )

    def destroy(self):
        self.is_destroyed = True
        print(f"[{self.name}] destroyed")

    def end(self, damage_dealt: float, tanks_killed: int):
        print(f"[{self.name}] end damage={damage_dealt} kills={tanks_killed}")
