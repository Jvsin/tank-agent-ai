from __future__ import annotations

from typing import Any, List, Tuple

from .geometry import euclidean_distance, heading_to_angle_deg, normalize_angle_diff, to_xy


class SimpleTurretController:
    def __init__(self, scan_speed: float = 22.0, track_speed: float = 36.0, aim_threshold: float = 3.0):
        self.scan_speed = scan_speed
        self.track_speed = track_speed
        self.aim_threshold = aim_threshold
        self.cooldown_ticks = 0

    def update(
        self,
        my_x: float,
        my_y: float,
        my_heading: float,
        current_barrel_angle: float,
        seen_tanks: List[Any],
        max_barrel_rotation: float,
    ) -> Tuple[float, bool]:
        if self.cooldown_ticks > 0:
            self.cooldown_ticks -= 1

        if not seen_tanks:
            rotation = max(-max_barrel_rotation, min(max_barrel_rotation, self.scan_speed))
            return rotation, False

        target_x = 0.0
        target_y = 0.0
        best_distance = float("inf")

        for tank in seen_tanks:
            x, y = to_xy(tank.get("position", {}) if isinstance(tank, dict) else getattr(tank, "position", None))
            dist = euclidean_distance(my_x, my_y, x, y)
            if dist < best_distance:
                best_distance = dist
                target_x, target_y = x, y

        absolute_angle = heading_to_angle_deg(my_x, my_y, target_x, target_y)
        relative_angle = normalize_angle_diff(absolute_angle, my_heading)
        error = normalize_angle_diff(relative_angle, current_barrel_angle)

        rotation = max(-self.track_speed, min(self.track_speed, error))
        rotation = max(-max_barrel_rotation, min(max_barrel_rotation, rotation))

        should_fire = abs(error) <= self.aim_threshold and self.cooldown_ticks == 0
        if should_fire:
            self.cooldown_ticks = 10

        return rotation, should_fire
