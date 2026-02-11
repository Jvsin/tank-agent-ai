"""
A* Pathfinder
Wyznacza najkrótszą ścieżkę z uwzględnieniem przeszkód i terenów.
"""

import numpy as np
from heapq import heappush, heappop
from typing import List, Tuple, Optional


class AStarPathfinder:
    def __init__(self, heat_map):
        """
        Args:
            heat_map: Referencja do obiektu HeatMap dla współdzielenia siatki
        """
        self.heat_map = heat_map
        self.grid_dims = heat_map.grid_dims
        
        # Mapa przeszkód (True = blokada)
        self.obstacle_grid = np.zeros(self.grid_dims, dtype=bool)
        
        # Mapa kosztów terenów (wartości 1.0-3.0)
        self.terrain_cost_grid = np.ones(self.grid_dims, dtype=np.float32)
    
    def update_obstacles(self, sensor_data, map_info=None):
        """Aktualizacja siatki przeszkód na podstawie widocznych obiektów."""
        # Reset tylko widocznego obszaru (opcjonalna optymalizacja)
        
        obstacles = []
        if hasattr(sensor_data, 'seen_obstacles'):
            obstacles = sensor_data.seen_obstacles
        elif isinstance(sensor_data, dict):
            obstacles = sensor_data.get('seen_obstacles', [])
        
        for obstacle in obstacles:
            is_blocking = True
            if hasattr(obstacle, 'is_see_through'):
                is_blocking = not obstacle.is_see_through
            elif isinstance(obstacle, dict):
                is_blocking = not obstacle.get('is_see_through', False)
            
            if is_blocking:
                pos = None
                if hasattr(obstacle, '_position'):
                    pos = (obstacle._position.x, obstacle._position.y)
                elif isinstance(obstacle, dict) and 'position' in obstacle:
                    pos = (obstacle['position']['x'], obstacle['position']['y'])
                
                if pos:
                    gx, gy = self.heat_map.world_to_grid(*pos)
                    self.obstacle_grid[gx, gy] = True
    
    def update_terrain_costs(self, sensor_data):
        """Aktualizacja kosztów terenów."""
        terrains = []
        if hasattr(sensor_data, 'seen_terrains'):
            terrains = sensor_data.seen_terrains
        elif isinstance(sensor_data, dict):
            terrains = sensor_data.get('seen_terrains', [])
        
        for terrain in terrains:
            pos = None
            modifier = 1.0
            
            if hasattr(terrain, '_position'):
                pos = (terrain._position.x, terrain._position.y)
                modifier = getattr(terrain, '_movement_speed_modifier', 1.0)
            elif isinstance(terrain, dict):
                if 'position' in terrain:
                    pos = (terrain['position']['x'], terrain['position']['y'])
                modifier = terrain.get('movement_speed_modifier', 1.0)
            
            if pos:
                gx, gy = self.heat_map.world_to_grid(*pos)
                # Koszt odwrotnie proporcjonalny do modyfikatora prędkości
                self.terrain_cost_grid[gx, gy] = 1.0 / max(0.1, modifier)
    
    def find_path(
        self, 
        start_pos: Tuple[float, float], 
        goal_pos: Tuple[float, float]
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Algorytm A* dla znalezienia ścieżki.
        
        Returns:
            Lista współrzędnych świata [(x1,y1), (x2,y2), ...] lub None
        """
        if goal_pos is None:
            return None
        
        # Konwersja na siatkę
        start_grid = self.heat_map.world_to_grid(*start_pos)
        goal_grid = self.heat_map.world_to_grid(*goal_pos)
        
        # Sprawdź czy cel jest osiągalny
        if self.obstacle_grid[goal_grid]:
            # Znajdź najbliższą wolną komórkę
            goal_grid = self._find_nearest_free_cell(goal_grid)
            if goal_grid is None:
                return None
        
        # A* search
        open_set = []
        heappush(open_set, (0, start_grid))
        
        came_from = {}
        g_score = {start_grid: 0}
        f_score = {start_grid: self._heuristic(start_grid, goal_grid)}
        
        while open_set:
            _, current = heappop(open_set)
            
            if current == goal_grid:
                # Rekonstrukcja ścieżki
                path_grid = self._reconstruct_path(came_from, current)
                # Konwersja na współrzędne świata
                path_world = [self.heat_map.grid_to_world(gx, gy) for gx, gy in path_grid]
                return path_world
            
            # Sprawdź sąsiadów
            for neighbor in self._get_neighbors(current):
                if self.obstacle_grid[neighbor]:
                    continue
                
                # Koszt ruchu (bazowy 1.0 + koszt terenu)
                move_cost = 1.0 * self.terrain_cost_grid[neighbor]
                tentative_g = g_score[current] + move_cost
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + self._heuristic(neighbor, goal_grid)
                    f_score[neighbor] = f
                    heappush(open_set, (f, neighbor))
        
        return None  # Brak ścieżki
    
    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Heurystyka euklidesowa."""
        return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)
    
    def _get_neighbors(self, pos: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Zwraca sąsiednie komórki (8-kierunkowe)."""
        x, y = pos
        neighbors = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.grid_dims[0] and 0 <= ny < self.grid_dims[1]:
                    neighbors.append((nx, ny))
        return neighbors
    
    def _reconstruct_path(self, came_from, current):
        """Rekonstrukcja ścieżki od startu do celu."""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
    
    def _find_nearest_free_cell(self, blocked_cell):
        """Znajduje najbliższą wolną komórkę."""
        for radius in range(1, 20):
            for dx in range(-radius, radius+1):
                for dy in range(-radius, radius+1):
                    nx = blocked_cell[0] + dx
                    ny = blocked_cell[1] + dy
                    if (0 <= nx < self.grid_dims[0] and 
                        0 <= ny < self.grid_dims[1] and
                        not self.obstacle_grid[nx, ny]):
                        return (nx, ny)
        return None
