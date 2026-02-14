"""
Maksymalnie prosty kontroler ruchu oparty o scikit-fuzzy.

Założenia:
- Priorytet 1: przeżycie (unikaj przeszkód i nie wjeżdżaj w drzewa/ściany)
- Priorytet 2: walka (skręcaj do wroga gdy warto, uciekaj na niskim HP)
- Priorytet 3: eksploracja (stabilny patrol gdy brak kontaktu)
"""

from typing import Dict, Any, Tuple
import math
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl


class FuzzyMotionController:
    """Prosty kontroler ruchu czołgu oparty o kilka reguł fuzzy."""

    def __init__(self):
        # Patrol (gdy brak wrogów)
        self.patrol_tick = 0
        self.patrol_side = 1.0

        # Wejścia
        self.enemy_distance = ctrl.Antecedent(np.arange(0, 121, 1), "enemy_distance")
        self.hp_percent = ctrl.Antecedent(np.arange(0, 101, 1), "hp_percent")
        self.obstacle_distance = ctrl.Antecedent(np.arange(0, 31, 1), "obstacle_distance")

        # Wyjścia znormalizowane [-1, 1]
        self.speed_norm = ctrl.Consequent(np.arange(-1.0, 1.01, 0.01), "speed_norm")
        self.turn_norm = ctrl.Consequent(np.arange(-1.0, 1.01, 0.01), "turn_norm")

        # enemy_distance
        self.enemy_distance["danger"] = fuzz.trimf(self.enemy_distance.universe, [0, 0, 20])
        self.enemy_distance["close"] = fuzz.trimf(self.enemy_distance.universe, [10, 30, 55])
        self.enemy_distance["far"] = fuzz.trimf(self.enemy_distance.universe, [40, 70, 100])
        self.enemy_distance["none"] = fuzz.trimf(self.enemy_distance.universe, [80, 120, 120])

        # hp_percent
        self.hp_percent["low"] = fuzz.trimf(self.hp_percent.universe, [0, 0, 45])
        self.hp_percent["ok"] = fuzz.trimf(self.hp_percent.universe, [30, 55, 80])
        self.hp_percent["high"] = fuzz.trimf(self.hp_percent.universe, [65, 100, 100])

        # obstacle_distance
        self.obstacle_distance["danger"] = fuzz.trimf(self.obstacle_distance.universe, [0, 0, 8])
        self.obstacle_distance["near"] = fuzz.trimf(self.obstacle_distance.universe, [5, 11, 16])
        self.obstacle_distance["clear"] = fuzz.trimf(self.obstacle_distance.universe, [12, 30, 30])

        # speed_norm
        self.speed_norm["reverse"] = fuzz.trimf(self.speed_norm.universe, [-1.0, -0.8, -0.35])
        self.speed_norm["slow"] = fuzz.trimf(self.speed_norm.universe, [0.05, 0.2, 0.4])
        self.speed_norm["cruise"] = fuzz.trimf(self.speed_norm.universe, [0.35, 0.55, 0.75])
        self.speed_norm["rush"] = fuzz.trimf(self.speed_norm.universe, [0.65, 0.85, 1.0])

        # turn_norm (znak oznacza logikę: + do celu, - od celu)
        self.turn_norm["hard_away"] = fuzz.trimf(self.turn_norm.universe, [-1.0, -0.9, -0.6])
        self.turn_norm["away"] = fuzz.trimf(self.turn_norm.universe, [-0.75, -0.45, -0.15])
        self.turn_norm["neutral"] = fuzz.trimf(self.turn_norm.universe, [-0.1, 0.0, 0.1])
        self.turn_norm["toward"] = fuzz.trimf(self.turn_norm.universe, [0.2, 0.55, 0.9])

        rules = [
            # Priorytet bezpieczeństwa
            ctrl.Rule(self.obstacle_distance["danger"], (self.speed_norm["reverse"], self.turn_norm["hard_away"])),
            ctrl.Rule(self.obstacle_distance["near"], (self.speed_norm["slow"], self.turn_norm["away"])),

            # Walka / "mniejsze zło"
            ctrl.Rule(self.enemy_distance["danger"] & self.hp_percent["low"], (self.speed_norm["reverse"], self.turn_norm["away"])),
            ctrl.Rule(self.enemy_distance["close"] & (self.hp_percent["ok"] | self.hp_percent["high"]), (self.speed_norm["rush"], self.turn_norm["toward"])),
            ctrl.Rule(self.enemy_distance["far"], (self.speed_norm["cruise"], self.turn_norm["toward"])),

            # Eksploracja
            ctrl.Rule(self.enemy_distance["none"] & self.obstacle_distance["clear"], (self.speed_norm["cruise"], self.turn_norm["neutral"])),
            ctrl.Rule(self.enemy_distance["none"] & self.obstacle_distance["near"], (self.speed_norm["slow"], self.turn_norm["away"])),
        ]

        self.control_system = ctrl.ControlSystem(rules)

    def compute_motion(
        self,
        my_position: Tuple[float, float],
        my_heading: float,
        my_hp: float,
        max_hp: float,
        sensor_data: Dict[str, Any],
    ) -> Tuple[float, float]:
        enemy_dist, enemy_angle_diff, enemy_visible = self._closest_enemy(my_position, my_heading, sensor_data)
        obstacle_dist, obstacle_angle_diff = self._closest_obstacle_ahead(my_position, my_heading, sensor_data)

        hp_percent = (my_hp / max_hp) * 100.0 if max_hp > 0 else 0.0

        sim = ctrl.ControlSystemSimulation(self.control_system)
        sim.input["enemy_distance"] = min(max(enemy_dist, 0.0), 120.0)
        sim.input["hp_percent"] = min(max(hp_percent, 0.0), 100.0)
        sim.input["obstacle_distance"] = min(max(obstacle_dist, 0.0), 30.0)

        try:
            sim.compute()
            speed_norm = float(sim.output.get("speed_norm", 0.4))
            turn_norm = float(sim.output.get("turn_norm", 0.0))
        except Exception:
            speed_norm = 0.35
            turn_norm = 0.0

        # Konwersja do komend agenta (final_agent i tak clampuje do parametrów czołgu)
        move_speed = speed_norm * 40.0
        heading_rotation = 0.0

        if enemy_visible:
            # turn_norm > 0: skręcaj do wroga, turn_norm < 0: od wroga
            desired = enemy_angle_diff if turn_norm >= 0 else -enemy_angle_diff
            heading_rotation = max(-45.0, min(45.0, desired * abs(turn_norm)))

            # Mały deadzone
            if abs(heading_rotation) < 4.0:
                heading_rotation = 0.0
        else:
            # Prosta eksploracja: domyślnie jedź prosto, skręcaj tylko przy przeszkodzie
            self.patrol_tick += 1
            if self.patrol_tick % 70 == 0:
                self.patrol_side *= -1.0
            if obstacle_dist < 13.0:
                heading_rotation = self.patrol_side * 20.0
            else:
                heading_rotation = 0.0
                if move_speed < 10.0:
                    move_speed = 14.0

        # Mniejsze zło: unikaj wejścia w przeszkodę za cenę chwilowej utraty pozycji
        if obstacle_dist < 8.0 and move_speed > 0:
            move_speed = 8.0
        if obstacle_dist < 6.0:
            move_speed = -12.0
            if obstacle_angle_diff is not None:
                heading_rotation = -28.0 if obstacle_angle_diff > 0 else 28.0

        return heading_rotation, move_speed

    def _closest_enemy(
        self,
        my_position: Tuple[float, float],
        my_heading: float,
        sensor_data: Dict[str, Any],
    ) -> Tuple[float, float, bool]:
        seen_tanks = sensor_data.get("seen_tanks", [])
        if not seen_tanks:
            return 120.0, 0.0, False

        best_dist = float("inf")
        best_angle_diff = 0.0

        for tank in seen_tanks:
            tank_pos = tank.get("position", {})
            tx = tank_pos.get("x", 0.0)
            ty = tank_pos.get("y", 0.0)

            dx = tx - my_position[0]
            dy = ty - my_position[1]
            dist = math.hypot(dx, dy)
            if dist < best_dist:
                best_dist = dist
                target_angle = math.degrees(math.atan2(dx, dy)) % 360
                best_angle_diff = self._normalize_angle_diff(target_angle - my_heading)

        return min(best_dist, 120.0), best_angle_diff, True

    def _closest_obstacle_ahead(
        self,
        my_position: Tuple[float, float],
        my_heading: float,
        sensor_data: Dict[str, Any],
    ) -> Tuple[float, float | None]:
        seen_obstacles = sensor_data.get("seen_obstacles", [])
        best_dist = 30.0
        best_angle_diff = None

        for obstacle in seen_obstacles:
            obs_pos = obstacle.get("position", obstacle.get("_position", {}))
            ox = obs_pos.get("x", 0.0)
            oy = obs_pos.get("y", 0.0)

            dx = ox - my_position[0]
            dy = oy - my_position[1]
            dist = math.hypot(dx, dy)
            angle_to_obs = math.degrees(math.atan2(dx, dy)) % 360
            angle_diff = self._normalize_angle_diff(angle_to_obs - my_heading)

            # tylko przeszkody mniej więcej z przodu
            if abs(angle_diff) <= 55.0 and dist < best_dist:
                best_dist = dist
                best_angle_diff = angle_diff

        return best_dist, best_angle_diff

    def _normalize_angle_diff(self, angle: float) -> float:
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle
