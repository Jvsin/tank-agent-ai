"""
Heat Map (HM) - Mapa Cieplna
Przechowuje informacje o wrogach, powerupach i niebezpiecznych strefach.
"""

import numpy as np
from typing import List, Tuple, Optional


class HeatMap:
    def __init__(self, map_size: Tuple[int, int] = (500, 500), grid_size: int = 10):
        """
        Args:
            map_size: Rozmiar mapy w jednostkach (500, 500)
            grid_size: Rozmiar jednej komórki siatki (10)
        """
        self.map_size = map_size
        self.grid_size = grid_size
        self.grid_dims = (map_size[0] // grid_size, map_size[1] // grid_size)  # (50, 50)
        
        # Mapy cieplne dla różnych typów obiektów
        self.enemy_heat = np.zeros(self.grid_dims, dtype=np.float32)
        self.powerup_heat = np.zeros(self.grid_dims, dtype=np.float32)
        self.danger_heat = np.zeros(self.grid_dims, dtype=np.float32)
        
        # Parametry zanikania
        self.decay_rate = 0.95
        self.enemy_value = 100.0
        self.powerup_value = 50.0
        self.danger_value = 80.0
    
    def world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Konwersja współrzędnych świata na indeksy siatki."""
        grid_x = int(x // self.grid_size)
        grid_y = int(y // self.grid_size)
        return (
            max(0, min(grid_x, self.grid_dims[0] - 1)),
            max(0, min(grid_y, self.grid_dims[1] - 1))
        )
    
    def grid_to_world(self, grid_x: int, grid_y: int) -> Tuple[float, float]:
        """Konwersja indeksów siatki na współrzędne świata (centrum komórki)."""
        return (
            (grid_x + 0.5) * self.grid_size,
            (grid_y + 0.5) * self.grid_size
        )
    
    def update(self, sensor_data, my_position):
        """Aktualizacja mapy cieplnej na podstawie danych sensorycznych."""
        # 1. Zanikanie (decay)
        self.enemy_heat *= self.decay_rate
        self.powerup_heat *= self.decay_rate
        self.danger_heat *= self.decay_rate
        
        # 2. Aktualizacja pozycji wrogów
        if hasattr(sensor_data, 'seen_tanks'):
            for enemy in sensor_data.seen_tanks:
                if hasattr(enemy, 'position'):
                    gx, gy = self.world_to_grid(enemy.position.x, enemy.position.y)
                    self.enemy_heat[gx, gy] = self.enemy_value
        elif isinstance(sensor_data, dict) and 'seen_tanks' in sensor_data:
            for enemy in sensor_data['seen_tanks']:
                gx, gy = self.world_to_grid(enemy['position']['x'], enemy['position']['y'])
                self.enemy_heat[gx, gy] = self.enemy_value
        
        # 3. Aktualizacja powerupów
        if hasattr(sensor_data, 'seen_powerups'):
            for powerup in sensor_data.seen_powerups:
                if hasattr(powerup, '_position'):
                    gx, gy = self.world_to_grid(powerup._position.x, powerup._position.y)
                    self.powerup_heat[gx, gy] = self.powerup_value
        elif isinstance(sensor_data, dict) and 'seen_powerups' in sensor_data:
            for powerup in sensor_data['seen_powerups']:
                if 'position' in powerup:
                    gx, gy = self.world_to_grid(powerup['position']['x'], powerup['position']['y'])
                    self.powerup_heat[gx, gy] = self.powerup_value
    
    def get_hottest_enemy_position(self) -> Optional[Tuple[float, float]]:
        """Zwraca współrzędne świata najgorętszego punktu z wrogami."""
        if np.max(self.enemy_heat) < 1.0:
            return None
        gx, gy = np.unravel_index(np.argmax(self.enemy_heat), self.grid_dims)
        return self.grid_to_world(gx, gy)
    
    def get_closest_powerup_position(self, my_pos) -> Optional[Tuple[float, float]]:
        """Zwraca najbliższy powerup na mapie cieplnej."""
        if np.max(self.powerup_heat) < 1.0:
            return None
        
        # Obsługa różnych typów my_pos
        if hasattr(my_pos, 'x'):
            my_gx, my_gy = self.world_to_grid(my_pos.x, my_pos.y)
        elif isinstance(my_pos, dict):
            my_gx, my_gy = self.world_to_grid(my_pos['x'], my_pos['y'])
        else:
            return None
        
        # Znajdź wszystkie komórki z powerupami
        powerup_positions = np.argwhere(self.powerup_heat > 1.0)
        
        if len(powerup_positions) == 0:
            return None
        
        # Znajdź najbliższy
        distances = np.sum((powerup_positions - np.array([my_gx, my_gy]))**2, axis=1)
        closest_idx = np.argmin(distances)
        gx, gy = powerup_positions[closest_idx]
        
        return self.grid_to_world(gx, gy)
    
    def add_danger_zone(self, x: float, y: float):
        """Dodaje strefę niebezpieczną (np. po otrzymaniu obrażeń)."""
        gx, gy = self.world_to_grid(x, y)
        self.danger_heat[gx, gy] = self.danger_value
