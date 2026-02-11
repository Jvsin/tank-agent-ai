"""
Finite State Machine (FSM)
Zarządza strategicznymi stanami agenta z histerezą.
"""

from enum import Enum
from typing import Optional, Tuple


class AgentState(Enum):
    EXPLORE = 1
    HUNT = 2
    COLLECT_POWERUP = 3
    RETREAT = 4
    AMBUSH = 5


class FSM:
    def __init__(self):
        self.current_state = AgentState.EXPLORE
        self.state_timer = 0  # Zapobiega zbyt szybkim zmianom
        self.min_state_duration = 20  # Minimalny czas w stanie (ticki)
        
        # Progi histerezowe
        self.hp_retreat_threshold = 0.25  # Odwrót poniżej 25% HP
        self.hp_safe_threshold = 0.35     # Powrót do normalności powyżej 35%
        self.ammo_low_threshold = 3       # Zbieraj amunicję poniżej 3 sztuk
    
    def update(self, my_tank, sensor_data, heat_map) -> AgentState:
        """Aktualizacja stanu FSM."""
        self.state_timer += 1
        
        # Zabezpieczenie przed zbyt częstymi zmianami
        if self.state_timer < self.min_state_duration:
            return self.current_state
        
        # Oblicz kluczowe metryki
        hp_ratio = self._get_hp_ratio(my_tank)
        visible_enemies = self._count_visible_enemies(sensor_data)
        total_ammo = self._count_total_ammo(my_tank)
        
        hottest_enemy = heat_map.get_hottest_enemy_position()
        closest_powerup = heat_map.get_closest_powerup_position(
            my_tank if hasattr(my_tank, 'position') else my_tank.get('position')
        )
        
        # LOGIKA PRZEJŚĆ (z histerezą)
        
        # PRIORYTET 1: RETREAT (krytyczne HP)
        if hp_ratio < self.hp_retreat_threshold:
            if self.current_state != AgentState.RETREAT:
                self._change_state(AgentState.RETREAT)
        
        # Powrót z RETREAT dopiero przy bezpiecznym HP
        elif self.current_state == AgentState.RETREAT and hp_ratio > self.hp_safe_threshold:
            self._change_state(AgentState.EXPLORE)
        
        # PRIORYTET 2: AMBUSH (widoczny wróg + dobre HP)
        elif visible_enemies and hp_ratio > 0.5:
            # Sprawdź czy wróg jest w dobrym zasięgu (< 15 jednostek)
            closest_enemy_dist = self._get_closest_enemy_distance(sensor_data)
            if closest_enemy_dist and closest_enemy_dist < 15 and self.current_state != AgentState.AMBUSH:
                self._change_state(AgentState.AMBUSH)
        
        # PRIORYTET 3: HUNT (wróg widoczny lub w HM)
        elif visible_enemies or hottest_enemy:
            if self.current_state not in [AgentState.HUNT, AgentState.AMBUSH]:
                self._change_state(AgentState.HUNT)
        
        # PRIORYTET 4: COLLECT_POWERUP (niska amunicja lub HP)
        elif (total_ammo < self.ammo_low_threshold or hp_ratio < 0.6) and closest_powerup:
            if self.current_state != AgentState.COLLECT_POWERUP:
                self._change_state(AgentState.COLLECT_POWERUP)
        
        # DOMYŚLNIE: EXPLORE
        else:
            if self.current_state not in [AgentState.EXPLORE, AgentState.HUNT]:
                self._change_state(AgentState.EXPLORE)
        
        return self.current_state
    
    def _change_state(self, new_state: AgentState):
        """Zmiana stanu z resetem timera."""
        print(f"FSM: {self.current_state.name} -> {new_state.name}")
        self.current_state = new_state
        self.state_timer = 0
    
    def get_target_position(self, my_tank, sensor_data, heat_map) -> Optional[Tuple[float, float]]:
        """Zwraca docelową pozycję w zależności od stanu."""
        if self.current_state == AgentState.HUNT or self.current_state == AgentState.AMBUSH:
            # Najbliższy widoczny wróg lub HM
            closest = self._get_closest_enemy(sensor_data)
            if closest:
                return self._extract_position(closest)
            else:
                return heat_map.get_hottest_enemy_position()
        
        elif self.current_state == AgentState.COLLECT_POWERUP:
            my_pos = my_tank if hasattr(my_tank, 'position') else my_tank.get('position')
            return heat_map.get_closest_powerup_position(my_pos)
        
        elif self.current_state == AgentState.RETREAT:
            # Uciekaj w przeciwnym kierunku od wroga
            closest = self._get_closest_enemy(sensor_data)
            if closest:
                my_pos = self._extract_position(my_tank if hasattr(my_tank, 'position') else my_tank.get('position'))
                enemy_pos = self._extract_position(closest)
                dx = my_pos[0] - enemy_pos[0]
                dy = my_pos[1] - enemy_pos[1]
                escape_x = my_pos[0] + dx * 2
                escape_y = my_pos[1] + dy * 2
                return (escape_x, escape_y)
            return None
        
        else:  # EXPLORE
            # Przeszukuj mapę
            return None  # A* wybierze losowy waypoint
    
    def _get_hp_ratio(self, my_tank) -> float:
        """Pobiera stosunek HP (0-1)."""
        if hasattr(my_tank, 'hp'):
            return my_tank.hp / my_tank._max_hp
        elif isinstance(my_tank, dict):
            return my_tank.get('hp', 100) / my_tank.get('_max_hp', 100)
        return 1.0
    
    def _count_visible_enemies(self, sensor_data) -> int:
        """Liczy widocznych wrogów."""
        if hasattr(sensor_data, 'seen_tanks'):
            return len(sensor_data.seen_tanks)
        elif isinstance(sensor_data, dict):
            return len(sensor_data.get('seen_tanks', []))
        return 0
    
    def _count_total_ammo(self, my_tank) -> int:
        """Liczy całkowitą amunicję."""
        if hasattr(my_tank, 'ammo'):
            return sum(slot.count for slot in my_tank.ammo.values())
        elif isinstance(my_tank, dict) and 'ammo' in my_tank:
            return sum(slot.get('count', 0) for slot in my_tank['ammo'].values())
        return 10  # Domyślna wartość
    
    def _get_closest_enemy(self, sensor_data):
        """Zwraca najbliższego wroga."""
        enemies = []
        if hasattr(sensor_data, 'seen_tanks'):
            enemies = sensor_data.seen_tanks
        elif isinstance(sensor_data, dict):
            enemies = sensor_data.get('seen_tanks', [])
        
        if not enemies:
            return None
        
        if hasattr(enemies[0], 'distance'):
            return min(enemies, key=lambda e: e.distance)
        elif isinstance(enemies[0], dict) and 'distance' in enemies[0]:
            return min(enemies, key=lambda e: e['distance'])
        return enemies[0]
    
    def _get_closest_enemy_distance(self, sensor_data) -> Optional[float]:
        """Zwraca odległość do najbliższego wroga."""
        closest = self._get_closest_enemy(sensor_data)
        if not closest:
            return None
        if hasattr(closest, 'distance'):
            return closest.distance
        elif isinstance(closest, dict):
            return closest.get('distance')
        return None
    
    def _extract_position(self, obj) -> Tuple[float, float]:
        """Wydobywa pozycję z obiektu."""
        if hasattr(obj, 'position'):
            pos = obj.position
            if hasattr(pos, 'x'):
                return (pos.x, pos.y)
            elif isinstance(pos, dict):
                return (pos['x'], pos['y'])
        elif isinstance(obj, dict):
            if 'position' in obj:
                pos = obj['position']
                return (pos['x'], pos['y'])
            elif 'x' in obj and 'y' in obj:
                return (obj['x'], obj['y'])
        return (0, 0)
