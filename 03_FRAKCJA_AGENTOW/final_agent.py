"""
Fuzzy Logic Tank Agent
Agent czołgu używający logiki rozmytej do podejmowania decyzji

Ten agent wykorzystuje scikit-fuzzy do inteligentnego poruszania się:
- Omija przeszkody
- Atakuje wrogów gdy ma dużo HP
- Ucieka gdy HP jest niskie
- Używa logiki rozmytej zamiast ostrych warunków

Usage:
    python final_agent.py --port 8001
    
To run multiple agents:
    python final_agent.py --port 8001  # Tank 1
    python final_agent.py --port 8002  # Tank 2
    ...
"""

import argparse
import sys
import os
import math
import random
import heapq

# Add paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
controller_dir = os.path.join(os.path.dirname(current_dir), '02_FRAKCJA_SILNIKA', 'controller')
sys.path.insert(0, controller_dir)

parent_dir = os.path.join(os.path.dirname(current_dir), '02_FRAKCJA_SILNIKA')
sys.path.insert(0, parent_dir)

from typing import Dict, Any, Optional, Tuple, List
from fastapi import FastAPI, Body
from pydantic import BaseModel
import uvicorn

# Import modułów jazdy z DRIVE
from DRIVE import DecisionMaker, FuzzyMotionController
from DRIVE.barrel_controller import BarrelController, BarrelMode


# ============================================================================
# ACTION COMMAND MODEL
# ============================================================================

class ActionCommand(BaseModel):
    """Output action from agent to engine."""
    barrel_rotation_angle: float = 0.0
    heading_rotation_angle: float = 0.0
    move_speed: float = 0.0
    ammo_to_load: str = None
    should_fire: bool = False


ACTION_LOG_EVERY = 60  # Globalna stała - log co 60 ticków (1 sekunda)


class FuzzyAgent:
    """
    Agent używający logiki rozmytej (fuzzy logic) do podejmowania decyzji.
    
    - Ruch czołgu kontrolowany przez FuzzyMotionController
    - Proste skanowanie celu lufą
    - Inteligentne decyzje na podstawie odległości wroga i HP
    """
    
    def __init__(self, name: str = "FuzzyBot"):
        self.name = name
        self.is_destroyed = False
        print(f"[{self.name}] Agent inicjalizowany...")

        # Fuzzy controller dla ruchu (walka/eksploracja)
        self.motion_controller = FuzzyMotionController()
        
        # Decision maker (hierarchia priorytetów)
        self.decision_maker = DecisionMaker()

        # Barrel controller - ciągłe skanowanie 360° jak wiatrak
        self.barrel_controller = BarrelController(
            scan_speed=20.0,      # Szybkie skanowanie (silnik ograniczy do ~1.5°/tick)
            track_speed=35.0,     # Bardzo szybkie śledzenie wroga
            aim_threshold=3.0,    # Celuj z dokładnością ±3°
            aim_ticks=2,          # Celuj przez 2 ticki przed strzałem
            fire_cooldown=15      # 15 ticków między strzałami
        )
        
        # Stan HP do wykrywania obrażeń od terenu
        self.last_hp = None
        self.damage_taken_recently = 0
        self.escape_direction = None  # Kierunek ucieczki gdy na szkodliwym terenie

        # Lekka pamięć mapy: znane przeszkody/szkodliwe miejsca
        self.obstacle_memory: List[Dict[str, float]] = []
        self.last_position: Optional[Tuple[float, float]] = None
        self.last_move_speed_cmd: float = 0.0
        self.stuck_ticks: int = 0

        # Pamięć eksploracji mapy (siatka)
        self.grid_size: float = 10.0
        self.visit_counts: Dict[Tuple[int, int], int] = {}
        self.dead_end_cells: Dict[Tuple[int, int], float] = {}

        # Pamięć skanowania mapy (agregacja wiedzy)
        self.cell_memory: Dict[Tuple[int, int], Dict[str, float]] = {}
        self.current_goal_cell: Optional[Tuple[int, int]] = None
        self.goal_refresh_tick: int = 0
        self.current_path: List[Tuple[int, int]] = []
        self.path_refresh_tick: int = 0
        
        print(f"[{self.name}] ✓ Agent gotowy - prosta i skuteczna logika!")

    def _extract_xy(self, obj: Any) -> Tuple[float, float]:
        if isinstance(obj, dict):
            return float(obj.get("x", 0.0)), float(obj.get("y", 0.0))
        return float(getattr(obj, "x", 0.0)), float(getattr(obj, "y", 0.0))

    def _cell_key(self, x: float, y: float) -> Tuple[int, int]:
        return int(x // self.grid_size), int(y // self.grid_size)

    def _cell_center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        return (cell[0] + 0.5) * self.grid_size, (cell[1] + 0.5) * self.grid_size

    def _update_visit_memory(self, x: float, y: float) -> None:
        key = self._cell_key(x, y)
        self.visit_counts[key] = self.visit_counts.get(key, 0) + 1

    def _memory_entry(self, cell: Tuple[int, int]) -> Dict[str, float]:
        if cell not in self.cell_memory:
            self.cell_memory[cell] = {
                "safe": 0.0,
                "danger": 0.0,
                "blocked": 0.0,
                "last_seen": 0.0,
            }
        return self.cell_memory[cell]

    def _record_scan_memory(self, sensor_data: Dict[str, Any], current_tick: int) -> None:
        # Obstacle memory
        for obstacle in sensor_data.get("seen_obstacles", []):
            pos = obstacle.get("position", obstacle.get("_position", {})) if isinstance(obstacle, dict) else getattr(obstacle, "position", getattr(obstacle, "_position", None))
            ox, oy = self._extract_xy(pos)
            cell = self._cell_key(ox, oy)
            entry = self._memory_entry(cell)
            entry["blocked"] += 1.0
            entry["last_seen"] = float(current_tick)

        # Terrain memory
        for terrain in sensor_data.get("seen_terrains", []):
            if isinstance(terrain, dict):
                dmg = float(terrain.get("deal_damage", terrain.get("_deal_damage", terrain.get("dmg", 0))) or 0)
                pos = terrain.get("position", terrain.get("_position", {}))
            else:
                dmg = float(getattr(terrain, "deal_damage", getattr(terrain, "_deal_damage", 0)) or 0)
                pos = getattr(terrain, "position", getattr(terrain, "_position", None))

            tx, ty = self._extract_xy(pos)
            cell = self._cell_key(tx, ty)
            entry = self._memory_entry(cell)
            if dmg > 0:
                entry["danger"] += 1.0
            else:
                entry["safe"] += 0.4
            entry["last_seen"] = float(current_tick)

    def _cell_is_reachable(self, cell: Tuple[int, int]) -> bool:
        if cell in self.dead_end_cells:
            return False
        entry = self.cell_memory.get(cell)
        if not entry:
            return True
        if entry["blocked"] >= 1.5:
            return False
        if entry["danger"] > entry["safe"] + 1.0:
            return False
        return True

    def _movement_cost(self, cell: Tuple[int, int]) -> float:
        entry = self.cell_memory.get(cell, {"safe": 0.0, "danger": 0.0, "blocked": 0.0})
        visits = float(self.visit_counts.get(cell, 0))
        danger = float(entry.get("danger", 0.0))
        blocked = float(entry.get("blocked", 0.0))

        # Kara za ryzyko i za kręcenie się po tych samych miejscach
        return 1.0 + 1.5 * danger + 2.5 * blocked + 0.2 * min(visits, 10.0)

    def _neighbors4(self, cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        x, y = cell
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    def _astar_path(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        search_radius: int = 14,
    ) -> List[Tuple[int, int]]:
        if start == goal:
            return [start]

        min_x = start[0] - search_radius
        max_x = start[0] + search_radius
        min_y = start[1] - search_radius
        max_y = start[1] + search_radius

        def in_bounds(cell: Tuple[int, int]) -> bool:
            return min_x <= cell[0] <= max_x and min_y <= cell[1] <= max_y

        def heuristic(a: Tuple[int, int], b: Tuple[int, int]) -> float:
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        open_heap: List[Tuple[float, Tuple[int, int]]] = []
        heapq.heappush(open_heap, (0.0, start))

        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {start: 0.0}

        while open_heap:
            _, current = heapq.heappop(open_heap)
            if current == goal:
                path: List[Tuple[int, int]] = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            for neighbor in self._neighbors4(current):
                if not in_bounds(neighbor):
                    continue
                if not self._cell_is_reachable(neighbor):
                    continue

                step_cost = self._movement_cost(neighbor)
                tentative = g_score[current] + step_cost
                if tentative < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative
                    f_score = tentative + heuristic(neighbor, goal)
                    heapq.heappush(open_heap, (f_score, neighbor))

        return []

    def _cell_score(self, cell: Tuple[int, int], my_cell: Tuple[int, int]) -> float:
        entry = self.cell_memory.get(cell, {"safe": 0.0, "danger": 0.0, "blocked": 0.0})
        visits = float(self.visit_counts.get(cell, 0))
        if cell in self.dead_end_cells:
            return -1e6

        dx = cell[0] - my_cell[0]
        dy = cell[1] - my_cell[1]
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return -1e3

        novelty = 1.0 / (1.0 + visits)
        safety = entry.get("safe", 0.0) - 2.0 * entry.get("danger", 0.0) - 3.0 * entry.get("blocked", 0.0)

        # preferujemy średni dystans (nie za blisko, nie za daleko)
        dist_pref = -abs(dist - 4.0)
        return 5.0 * novelty + 2.0 * safety + 0.5 * dist_pref

    def _enemy_positions(self, sensor_data: Dict[str, Any]) -> List[Tuple[float, float]]:
        positions: List[Tuple[float, float]] = []
        for tank in sensor_data.get("seen_tanks", []):
            pos = tank.get("position", {}) if isinstance(tank, dict) else getattr(tank, "position", None)
            tx, ty = self._extract_xy(pos)
            positions.append((tx, ty))
        return positions

    def _distance_cell_to_nearest_enemy(self, cell: Tuple[int, int], enemies: List[Tuple[float, float]]) -> float:
        if not enemies:
            return 99.0
        cx, cy = self._cell_center(cell)
        return min(math.hypot(cx - ex, cy - ey) for ex, ey in enemies)

    def _is_survival_mode(self, my_hp: float, max_hp: float) -> bool:
        hp_ratio = (my_hp / max_hp) if max_hp > 0 else 0.0
        return hp_ratio < 0.6 or self.damage_taken_recently > 0

    def _select_survival_goal_cell(
        self,
        my_x: float,
        my_y: float,
        sensor_data: Dict[str, Any],
    ) -> Optional[Tuple[int, int]]:
        my_cell = self._cell_key(my_x, my_y)
        enemies = self._enemy_positions(sensor_data)

        candidates: List[Tuple[int, int]] = []
        for dx in range(-10, 11):
            for dy in range(-10, 11):
                cell = (my_cell[0] + dx, my_cell[1] + dy)
                if self._cell_is_reachable(cell):
                    candidates.append(cell)

        if not candidates:
            return None

        def survival_score(cell: Tuple[int, int]) -> float:
            entry = self.cell_memory.get(cell, {"safe": 0.0, "danger": 0.0, "blocked": 0.0})
            danger = float(entry.get("danger", 0.0))
            blocked = float(entry.get("blocked", 0.0))
            safe = float(entry.get("safe", 0.0))
            visits = float(self.visit_counts.get(cell, 0))

            dx = cell[0] - my_cell[0]
            dy = cell[1] - my_cell[1]
            dist = math.hypot(dx, dy)
            enemy_dist = self._distance_cell_to_nearest_enemy(cell, enemies)

            # Survival: unikaj szkód i ścian, trzymaj dystans od wrogów, nie stój w miejscu
            return (
                4.0 * safe
                - 6.0 * danger
                - 7.0 * blocked
                + 0.2 * enemy_dist
                + 0.8 * min(dist, 8.0)
                - 0.2 * min(visits, 10.0)
            )

        best_cell = max(candidates, key=survival_score)
        if survival_score(best_cell) < -1.0:
            return None
        return best_cell

    def _select_best_goal_cell(self, my_x: float, my_y: float, current_tick: int) -> Optional[Tuple[int, int]]:
        my_cell = self._cell_key(my_x, my_y)

        # Utrzymuj stary cel przez chwilę, żeby nie skakać co tick
        if self.current_goal_cell and current_tick < self.goal_refresh_tick:
            if self._cell_is_reachable(self.current_goal_cell):
                return self.current_goal_cell

        candidates: List[Tuple[int, int]] = []

        # 1) znane komórki z pamięci
        for cell in self.cell_memory.keys():
            if self._cell_is_reachable(cell):
                candidates.append(cell)

        # 2) lokalny frontier (nieodwiedzone sąsiedztwo)
        for dx in range(-8, 9):
            for dy in range(-8, 9):
                cell = (my_cell[0] + dx, my_cell[1] + dy)
                if self.visit_counts.get(cell, 0) == 0 and self._cell_is_reachable(cell):
                    candidates.append(cell)

        if not candidates:
            self.current_goal_cell = None
            return None

        best_cell = max(candidates, key=lambda c: self._cell_score(c, my_cell))

        if self._cell_score(best_cell, my_cell) < -2.0:
            self.current_goal_cell = None
            return None

        self.current_goal_cell = best_cell
        self.goal_refresh_tick = current_tick + 35
        return best_cell

    def _update_path_to_goal(
        self,
        my_x: float,
        my_y: float,
        goal_cell: Tuple[int, int],
        current_tick: int,
    ) -> None:
        start = self._cell_key(my_x, my_y)

        need_replan = False
        if not self.current_path:
            need_replan = True
        elif current_tick >= self.path_refresh_tick:
            need_replan = True
        elif self.current_path[-1] != goal_cell:
            need_replan = True

        if need_replan:
            self.current_path = self._astar_path(start, goal_cell)
            self.path_refresh_tick = current_tick + 20

        # Usuń już osiągnięte waypointy
        while self.current_path:
            wx, wy = self._cell_center(self.current_path[0])
            if math.hypot(wx - my_x, wy - my_y) < 2.5:
                self.current_path.pop(0)
            else:
                break

    def _steer_along_path(
        self,
        my_x: float,
        my_y: float,
        my_heading: float,
        top_speed: float,
    ) -> Tuple[float, float]:
        if not self.current_path:
            return 0.0, max(0.5, top_speed * 0.4)

        waypoint = self.current_path[0]
        wx, wy = self._cell_center(waypoint)
        dx = wx - my_x
        dy = wy - my_y

        target_angle = math.degrees(math.atan2(dx, dy)) % 360
        angle_diff = target_angle - my_heading
        while angle_diff > 180:
            angle_diff -= 360
        while angle_diff < -180:
            angle_diff += 360

        heading_rotation = max(-15.0, min(15.0, angle_diff))

        # Gdy duży błąd kąta, prawie zatrzymaj się, żeby nie driftować
        if abs(angle_diff) > 45:
            move_speed = top_speed * 0.2
        elif abs(angle_diff) > 20:
            move_speed = top_speed * 0.45
        else:
            move_speed = top_speed * 0.9

        return heading_rotation, move_speed

    def _steer_to_goal_cell(
        self,
        my_x: float,
        my_y: float,
        my_heading: float,
        goal_cell: Tuple[int, int],
        top_speed: float,
    ) -> Tuple[float, float]:
        gx, gy = self._cell_center(goal_cell)
        dx = gx - my_x
        dy = gy - my_y
        distance = math.hypot(dx, dy)

        if distance < 2.0:
            return 0.0, 0.0

        target_angle = math.degrees(math.atan2(dx, dy)) % 360
        angle_diff = target_angle - my_heading
        while angle_diff > 180:
            angle_diff -= 360
        while angle_diff < -180:
            angle_diff += 360

        heading_rotation = max(-18.0, min(18.0, angle_diff))

        # Jedź prosto gdy kąt mały, zwolnij gdy trzeba mocno skręcać
        if abs(angle_diff) < 10:
            move_speed = top_speed
        elif abs(angle_diff) < 25:
            move_speed = top_speed * 0.7
        else:
            move_speed = top_speed * 0.45

        return heading_rotation, move_speed

    def _is_current_cell_dangerous(self, my_x: float, my_y: float, sensor_data: Dict[str, Any]) -> bool:
        # 1) Bezpośrednio z aktualnego skanu terenu (najpewniejsze)
        for terrain in sensor_data.get("seen_terrains", []):
            if isinstance(terrain, dict):
                dmg = float(terrain.get("deal_damage", terrain.get("_deal_damage", terrain.get("dmg", 0))) or 0)
                pos = terrain.get("position", terrain.get("_position", {}))
            else:
                dmg = float(getattr(terrain, "deal_damage", getattr(terrain, "_deal_damage", 0)) or 0)
                pos = getattr(terrain, "position", getattr(terrain, "_position", None))

            if dmg <= 0:
                continue

            tx, ty = self._extract_xy(pos)
            if math.hypot(tx - my_x, ty - my_y) <= self.grid_size * 0.75:
                return True

        # 2) Z pamięci komórki
        cell = self._cell_key(my_x, my_y)
        entry = self.cell_memory.get(cell)
        if entry and entry.get("danger", 0.0) > entry.get("safe", 0.0):
            return True

        return False

    def _decay_dead_ends(self) -> None:
        kept: Dict[Tuple[int, int], float] = {}
        for cell, ttl in self.dead_end_cells.items():
            next_ttl = ttl - 1.0
            if next_ttl > 0:
                kept[cell] = next_ttl
        self.dead_end_cells = kept

    def _mark_dead_end(self, x: float, y: float, ttl: int = 520) -> None:
        cell = self._cell_key(x, y)
        self.dead_end_cells[cell] = max(self.dead_end_cells.get(cell, 0.0), float(ttl))

    def _inject_exploration_avoidance(self, sensor_data: Dict[str, Any], my_x: float, my_y: float) -> None:
        current_obstacles = sensor_data.get("seen_obstacles", [])
        memory_obstacles: List[Dict[str, Any]] = []

        # 1) Twarde unikanie: komórki oznaczone jako ślepy zaułek
        for cell in self.dead_end_cells.keys():
            cx, cy = self._cell_center(cell)
            if math.hypot(cx - my_x, cy - my_y) <= 55.0:
                memory_obstacles.append({"position": {"x": cx, "y": cy}, "_dead_end": True})

        sensor_data["seen_obstacles"] = current_obstacles + memory_obstacles

    def _add_memory_point(self, x: float, y: float, ttl: int = 240) -> None:
        # Nie duplikuj punktów bardzo blisko siebie
        for point in self.obstacle_memory:
            if math.hypot(point["x"] - x, point["y"] - y) < 4.0:
                point["ttl"] = max(point["ttl"], float(ttl))
                return
        self.obstacle_memory.append({"x": x, "y": y, "ttl": float(ttl)})

    def _remember_visible_obstacles(self, sensor_data: Dict[str, Any]) -> None:
        for obstacle in sensor_data.get("seen_obstacles", []):
            pos = obstacle.get("position", obstacle.get("_position", {})) if isinstance(obstacle, dict) else getattr(obstacle, "position", getattr(obstacle, "_position", None))
            ox, oy = self._extract_xy(pos)
            self._add_memory_point(ox, oy, ttl=360)

    def _remember_damaging_terrains(self, sensor_data: Dict[str, Any]) -> None:
        for terrain in sensor_data.get("seen_terrains", []):
            if isinstance(terrain, dict):
                dmg = terrain.get("deal_damage", terrain.get("_deal_damage", terrain.get("dmg", 0)))
                pos = terrain.get("position", terrain.get("_position", {}))
            else:
                dmg = getattr(terrain, "deal_damage", getattr(terrain, "_deal_damage", 0))
                pos = getattr(terrain, "position", getattr(terrain, "_position", None))

            if float(dmg or 0) > 0:
                tx, ty = self._extract_xy(pos)
                self._add_memory_point(tx, ty, ttl=220)

    def _inject_memory_obstacles(self, sensor_data: Dict[str, Any], my_x: float, my_y: float) -> None:
        current_obstacles = sensor_data.get("seen_obstacles", [])
        memory_as_obstacles: List[Dict[str, Any]] = []

        for point in self.obstacle_memory:
            # Używaj tylko pamięci relatywnie blisko czołgu
            if math.hypot(point["x"] - my_x, point["y"] - my_y) <= 45.0:
                memory_as_obstacles.append({"position": {"x": point["x"], "y": point["y"]}, "_memory": True})

        sensor_data["seen_obstacles"] = current_obstacles + memory_as_obstacles

    def _decay_memory(self) -> None:
        kept: List[Dict[str, float]] = []
        for point in self.obstacle_memory:
            point["ttl"] -= 1.0
            if point["ttl"] > 0:
                kept.append(point)
        self.obstacle_memory = kept

    def _remember_collision_ahead(self, my_x: float, my_y: float, my_heading: float, ttl: int = 280) -> None:
        heading_rad = math.radians(my_heading)
        # Zapamiętaj punkt przed czołgiem, gdzie prawdopodobnie była przeszkoda
        px = my_x + math.sin(heading_rad) * 8.0
        py = my_y + math.cos(heading_rad) * 8.0
        self._add_memory_point(px, py, ttl=ttl)

    def _update_stuck_state(self, my_x: float, my_y: float, enemies_visible: bool, my_heading: float) -> None:
        if self.last_position is None:
            self.last_position = (my_x, my_y)
            self.stuck_ticks = 0
            return

        moved = math.hypot(my_x - self.last_position[0], my_y - self.last_position[1])
        trying_to_move = self.last_move_speed_cmd > 0.4

        if trying_to_move and moved < 0.15 and not enemies_visible:
            self.stuck_ticks += 1
        else:
            self.stuck_ticks = max(0, self.stuck_ticks - 1)

        if self.stuck_ticks >= 12:
            self._remember_collision_ahead(my_x, my_y, my_heading, ttl=260)
            self._mark_dead_end(my_x, my_y, ttl=520)
            self.stuck_ticks = 0

        self.last_position = (my_x, my_y)
    
    def get_action(
        self, 
        current_tick: int, 
        my_tank_status: Dict[str, Any], 
        sensor_data: Dict[str, Any], 
        enemies_remaining: int
    ) -> ActionCommand:
        """
        Główna metoda - HIERARCHIA DECYZJI.
        
        Sprawdzamy reguły od najważniejszych:
        1. Bezpośrednie zagrożenie (damaging terrain)
        2. Kolizja z przeszkodą
        3. Powerup w pobliżu (jeśli brak wrogów)
        4. Fuzzy logic (walka/eksploracja)
        """
        ACTION_LOG_EVERY = 60  # Zmniejszony spam - log co sekundę
        REQUEST_LOG_EVERY = 120  # Jeszcze rzadziej
        
        def clamp(value: float, min_value: float, max_value: float) -> float:
            return max(min_value, min(value, max_value))

        if REQUEST_LOG_EVERY > 0 and current_tick % REQUEST_LOG_EVERY == 0:
            print(f"[{self.name}] Request tick={current_tick}")

        should_fire = False
        barrel_rotation = 0.0
        
        # ===================================================================
        # EKSTRAKCJA DANYCH O CZOŁGU
        # ===================================================================
        # Pozycja
        pos = my_tank_status.get('position', {})
        if isinstance(pos, dict):
            my_x = pos.get('x', 0.0)
            my_y = pos.get('y', 0.0)
        else:
            my_x = getattr(pos, 'x', 0.0)
            my_y = getattr(pos, 'y', 0.0)
        
        my_position = (my_x, my_y)
        my_heading = my_tank_status.get('heading', 0.0)
        my_team = my_tank_status.get('_team')
        my_hp = my_tank_status.get('hp', 100)
        max_hp = my_tank_status.get('_max_hp', 100)
        barrel_angle = my_tank_status.get('barrel_angle', 0.0)
        max_heading = float(my_tank_status.get('_heading_spin_rate', 30.0) or 30.0)
        max_barrel = float(my_tank_status.get('_barrel_spin_rate', 30.0) or 30.0)
        top_speed = float(my_tank_status.get('_top_speed', 3.0) or 3.0)
        
        # ===================================================================
        # FILTROWANIE SOJUSZNIKÓW Z DANYCH SENSORÓW
        # ===================================================================
        filtered_sensor_data = dict(sensor_data)
        seen_tanks = sensor_data.get('seen_tanks', [])
        if my_team is not None:
            filtered_sensor_data['seen_tanks'] = [
                tank for tank in seen_tanks
                if tank.get('team') is None or tank.get('team') != my_team
            ]
        else:
            filtered_sensor_data['seen_tanks'] = seen_tanks

        # Aktualizuj pamięć mapy i domiksuj ją do aktualnych obserwacji
        self._update_visit_memory(my_x, my_y)
        self._record_scan_memory(filtered_sensor_data, current_tick)
        self._decay_memory()
        self._decay_dead_ends()
        self._remember_visible_obstacles(filtered_sensor_data)
        self._remember_damaging_terrains(filtered_sensor_data)
        self._inject_memory_obstacles(filtered_sensor_data, my_x, my_y)
        self._inject_exploration_avoidance(filtered_sensor_data, my_x, my_y)

        enemies_visible = len(filtered_sensor_data.get('seen_tanks', [])) > 0
        self._update_stuck_state(my_x, my_y, enemies_visible, my_heading)

        strategic_goal_cell: Optional[Tuple[int, int]] = None
        goal_mode = "none"
        if self._is_survival_mode(my_hp, max_hp):
            strategic_goal_cell = self._select_survival_goal_cell(my_x, my_y, filtered_sensor_data)
            goal_mode = "survival"
        elif not enemies_visible:
            strategic_goal_cell = self._select_best_goal_cell(my_x, my_y, current_tick)
            goal_mode = "explore"
        else:
            self.current_path = []
        
        # ===================================================================
        # DETEKCJA SZKODLIWEGO TERENU - Po stracie HP
        # ===================================================================
        # NAJPROSTSZE: Jeśli tracimy HP bez wroga = zawróć i uciekaj!
        is_escaping_damage = False
        
        if self.last_hp is not None:
            hp_lost = self.last_hp - my_hp
            if hp_lost > 0.01:  # obrażenia terenu są małe per tick
                # Tracimy HP!
                if len(filtered_sensor_data.get('seen_tanks', [])) == 0:
                    # Zapamiętaj miejsce potencjalnej kolizji lub szkodliwego terenu
                    self._remember_collision_ahead(my_x, my_y, my_heading, ttl=340)

                    # Brak wrogów - teren nas zabija!
                    self.damage_taken_recently = 60  # Pamiętaj przez sekundę
                    
                    # Wybierz kierunek ucieczki TYLKO RAZ gdy wykrywasz szkodę
                    if self.escape_direction is None:
                        # Zawróć: obróć się o 120-180° (losowo żeby nie zawracać w to samo miejsce)
                        turn_amount = random.choice([120, 135, 150, 165, 180, -120, -135, -150, -165, -180])
                        self.escape_direction = (my_heading + turn_amount) % 360
                        print(f"[{self.name}] 🚨 SZKODLIWY TEREN! HP {my_hp:.1f} (strata {hp_lost:.1f}) - Zawracam o {turn_amount}°!")

        # Natychmiastowa ucieczka jeśli STOIMY na szkodliwym polu (bez czekania na duży spadek HP)
        if len(filtered_sensor_data.get('seen_tanks', [])) == 0:
            if self._is_current_cell_dangerous(my_x, my_y, filtered_sensor_data):
                self.damage_taken_recently = max(self.damage_taken_recently, 45)
                if self.escape_direction is None:
                    turn_amount = random.choice([120, 135, 150, 165, 180, -120, -135, -150, -165, -180])
                    self.escape_direction = (my_heading + turn_amount) % 360
        
        self.last_hp = my_hp
        
        # Czy uciekamy?
        if self.damage_taken_recently > 0:
            self.damage_taken_recently -= 1
            is_escaping_damage = True
            
            # Jak HP wraca do normy, resetuj
            if my_hp > 0.8 * max_hp and self.damage_taken_recently < 20:
                self.escape_direction = None
                self.damage_taken_recently = 0
                is_escaping_damage = False
        else:
            self.escape_direction = None

        # ===================================================================
        # HIERARCHIA DECYZJI (PRIORYTET OD NAJWYŻSZEGO)
        # ===================================================================
        
        heading_rotation = 0.0
        move_speed = 0.0
        decision_source = "none"
        
        try:
            # --- PRIORYTET 0: UCIECZKA Z SZKODLIWEGO TERENU (NAJWYŻSZY!) ---
            if is_escaping_damage and self.escape_direction is not None:
                # Jedź w wybranym kierunku ucieczki pełną prędkością
                angle_diff = (self.escape_direction - my_heading + 360) % 360
                if angle_diff > 180:
                    angle_diff -= 360
                
                # Obróć się w stronę ucieczki
                heading_rotation = max(-45.0, min(45.0, angle_diff))
                move_speed = 40.0  # MAKSYMALNA PRĘDKOŚĆ!
                decision_source = "EMERGENCY_ESCAPE"
                result = True
                
                if current_tick % 30 == 0:
                    print(f"[{self.name}] 🏃 UCIECZKA! Kierunek {self.escape_direction:.0f}°, HP {my_hp:.1f}/{max_hp:.1f}")
            else:
                result = None
            
            # --- PRIORYTET 1: SZKODLIWY TEREN (tylko z vision API) ---
            if not result:
                result = self.decision_maker.check_damaging_terrain(my_x, my_y, filtered_sensor_data, my_heading)
                if result:
                    _, heading_rotation, move_speed = result
                    decision_source = "damaging_terrain"
            
            # --- PRIORYTET 2: KOLIZJA Z PRZESZKODĄ ---
            if not result:
                result = self.decision_maker.check_imminent_collision(
                    my_x, my_y, my_heading, filtered_sensor_data
                )
                if result:
                    _, heading_rotation, move_speed = result
                    self._remember_collision_ahead(my_x, my_y, my_heading, ttl=420)
                    self._mark_dead_end(my_x, my_y, ttl=580)
                    decision_source = "collision_avoidance"

            # --- PRIORYTET 3: STRATEGICZNA EKSPLORACJA PO ZAPISACH SKANÓW ---
            if not result and strategic_goal_cell is not None:
                if strategic_goal_cell is not None:
                    self._update_path_to_goal(
                        my_x=my_x,
                        my_y=my_y,
                        goal_cell=strategic_goal_cell,
                        current_tick=current_tick,
                    )
                    heading_rotation, move_speed = self._steer_along_path(
                        my_x=my_x,
                        my_y=my_y,
                        my_heading=my_heading,
                        top_speed=top_speed,
                    )
                    if goal_mode == "survival":
                        decision_source = "survival_path"
                    else:
                        decision_source = "strategic_explore"
                    result = True

            if not result and not enemies_visible:
                # Brak dobrego celu -> skanuj i delikatnie przepychaj eksplorację do przodu
                heading_rotation, move_speed = 0.0, max(0.4, top_speed * 0.35)
                decision_source = "explore_fallback"
                result = True

            # --- PRIORYTET 4: POWERUP W POBLIŻU ---
            if not result:
                result = self.decision_maker.check_nearby_powerup(
                    my_x, my_y, my_heading, filtered_sensor_data
                )
                if result:
                    _, heading_rotation, move_speed = result
                    decision_source = "powerup_collection"

            # --- PRIORYTET 5: FUZZY LOGIC (WALKA/EKSPLORACJA) ---
            if not result:
                heading_rotation, move_speed = self.motion_controller.compute_motion(
                    my_position=my_position,
                    my_heading=my_heading,
                    my_hp=my_hp,
                    max_hp=max_hp,
                    sensor_data=filtered_sensor_data
                )
                decision_source = "fuzzy_logic"
        except Exception as exc:
            print(f"[{self.name}] get_action error: {exc}")
            heading_rotation = 0.0
            move_speed = 0.0
            decision_source = "error"

        heading_rotation = clamp(heading_rotation, -max_heading, max_heading)
        move_speed = clamp(move_speed, -top_speed, top_speed)
        
        # Debug info (opcjonalnie)
        if ACTION_LOG_EVERY > 0 and current_tick % ACTION_LOG_EVERY == 0:
            barrel_status = self.barrel_controller.get_status()
            print(
                f"[{self.name}] Tick {current_tick}: Decision={decision_source}, "
                f"Speed={move_speed:.2f}, Turn={heading_rotation:.2f}, Barrel={barrel_status}"
            )
        
        # ===================================================================
        # BARREL CONTROLLER - SKANOWANIE 360° ORAZ CELOWANIE I STRZELANIE
        # ===================================================================
        
        # Użyj inteligentnego sterownika lufy
        barrel_rotation, should_fire = self.barrel_controller.update(
            my_x=my_x,
            my_y=my_y,
            my_heading=my_heading,
            current_barrel_angle=barrel_angle,
            seen_tanks=filtered_sensor_data.get('seen_tanks', []),
            max_barrel_rotation=max_barrel
        )
        
        self.last_move_speed_cmd = move_speed

        return ActionCommand(
            barrel_rotation_angle=clamp(barrel_rotation, -max_barrel, max_barrel),
            heading_rotation_angle=heading_rotation,
            move_speed=move_speed,
            should_fire=should_fire
        )
    
    def destroy(self):
        """Called when tank is destroyed."""
        self.is_destroyed = True
        print(f"[{self.name}] Tank destroyed!")
    
    def end(self, damage_dealt: float, tanks_killed: int):
        """Called when game ends."""
        print(f"[{self.name}] Game ended!")
        print(f"[{self.name}] Damage dealt: {damage_dealt}")
        print(f"[{self.name}] Tanks killed: {tanks_killed}")


# ============================================================================
# FASTAPI SERVER
# ============================================================================

app = FastAPI(
    title="Fuzzy Logic Tank Agent",
    description="Intelligent tank agent using fuzzy logic for decision making",
    version="1.0.0"
)

# Global agent instance
agent = FuzzyAgent()


@app.get("/")
async def root():
    return {"message": f"Agent {agent.name} is running", "destroyed": agent.is_destroyed}


@app.post("/agent/action", response_model=ActionCommand)
async def get_action(payload: Dict[str, Any] = Body(...)):
    """Main endpoint called each tick by the engine."""
    action = agent.get_action(
        current_tick=payload.get('current_tick', 0),
        my_tank_status=payload.get('my_tank_status', {}),
        sensor_data=payload.get('sensor_data', {}),
        enemies_remaining=payload.get('enemies_remaining', 0)
    )
    return action


@app.post("/agent/destroy", status_code=204)
async def destroy():
    """Called when the tank is destroyed."""
    agent.destroy()


@app.post("/agent/end", status_code=204)
async def end(payload: Dict[str, Any] = Body(...)):
    """Called when the game ends."""
    agent.end(
        damage_dealt=payload.get('damage_dealt', 0.0),
        tanks_killed=payload.get('tanks_killed', 0)
    )


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run fuzzy logic tank agent")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8001, help="Port number")
    parser.add_argument("--name", type=str, default=None, help="Agent name")
    args = parser.parse_args()
    
    if args.name:
        agent.name = args.name
    else:
        agent.name = f"FuzzyBot_{args.port}"
    
    print(f"Starting {agent.name} on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", access_log=False)
