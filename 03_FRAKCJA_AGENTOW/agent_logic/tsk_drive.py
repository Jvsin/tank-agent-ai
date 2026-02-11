"""
TSK-D (Takagi-Sugeno-Kang Drive Controller)
Kontroler rozmyty do sterowania ruchem kadłuba i prędkością.
"""

import numpy as np
from typing import Tuple, Optional


class TSKDriveController:
    def __init__(self, params=None):
        self.params = params or self._default_params()
    
    def _default_params(self):
        return {
            'angle_threshold_small': 10.0,
            'angle_threshold_large': 45.0,
            'distance_close': 15.0,
            'distance_far': 50.0,
            'rotation_gain': 1.0,
            'speed_max_multiplier': 1.0,
            'speed_min_multiplier': 0.3,
        }
    
    def compute(self, waypoint, my_position, my_heading, my_heading_spin_rate, my_top_speed, terrain_modifier=1.0):
        """
        Oblicza sterowanie ruchem.
        
        Args:
            waypoint: (x, y) docelowy punkt lub None
            my_position: Obecna pozycja (obiekt z .x, .y lub dict)
            my_heading: float aktualny kąt kadłuba
            my_heading_spin_rate: float max prędkość obrotu
            my_top_speed: float max prędkość jazdy
            terrain_modifier: float modyfikator terenu
        
        Returns:
            dict: {'heading_rotation': float, 'move_speed': float}
        """
        if waypoint is None:
            return {'heading_rotation': 0.0, 'move_speed': 0.0}
        
        # Wydobądź współrzędne pozycji
        if hasattr(my_position, 'x'):
            my_x, my_y = my_position.x, my_position.y
        elif isinstance(my_position, dict):
            my_x, my_y = my_position['x'], my_position['y']
        else:
            return {'heading_rotation': 0.0, 'move_speed': 0.0}
        
        # Oblicz różnicę kąta
        dx = waypoint[0] - my_x
        dy = waypoint[1] - my_y
        distance = np.sqrt(dx**2 + dy**2)
        
        # Jeśli jesteśmy bardzo blisko, zatrzymaj się
        if distance < 2.0:
            return {'heading_rotation': 0.0, 'move_speed': 0.0}
        
        # Kąt do celu (0-360, 0=góra, CW)
        target_angle = np.degrees(np.arctan2(dx, dy)) % 360
        
        # Błąd kąta (-180 do 180)
        angle_error = target_angle - my_heading
        while angle_error > 180:
            angle_error -= 360
        while angle_error < -180:
            angle_error += 360
        
        # --- HEADING ROTATION (prosta logika rozmyta) ---
        abs_angle_error = abs(angle_error)
        
        if abs_angle_error > self.params['angle_threshold_large']:
            # Duży błąd -> maksymalny obrót
            rotation_speed = 1.0
        elif abs_angle_error > self.params['angle_threshold_small']:
            # Średni błąd -> umiarkowany obrót
            rotation_speed = 0.6
        else:
            # Mały błąd -> wolny obrót
            rotation_speed = 0.3
        
        rotation_dir = 1.0 if angle_error > 0 else -1.0
        heading_rotation = rotation_dir * rotation_speed * my_heading_spin_rate * self.params['rotation_gain']
        
        # --- MOVE SPEED (zależny od odległości i kąta) ---
        
        # Jeśli kąt jest duży, jedź wolniej (obrót w miejscu)
        if abs_angle_error > 90:
            speed_multiplier = self.params['speed_min_multiplier']
        elif abs_angle_error > self.params['angle_threshold_large']:
            speed_multiplier = 0.5
        else:
            speed_multiplier = self.params['speed_max_multiplier']
        
        # Jeśli blisko celu, zwalniaj
        if distance < self.params['distance_close']:
            distance_multiplier = distance / self.params['distance_close']
        else:
            distance_multiplier = 1.0
        
        move_speed = my_top_speed * speed_multiplier * distance_multiplier * terrain_modifier
        
        return {
            'heading_rotation': heading_rotation,
            'move_speed': move_speed
        }
