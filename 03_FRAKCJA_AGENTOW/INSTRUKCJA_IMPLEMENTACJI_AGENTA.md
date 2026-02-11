# Instrukcja Implementacji Inteligentnego Agenta Czołgu
## Architektura: HM + FSM + TSK-C + A* + TSK-D

---

## WERYFIKACJA POMYSŁU: ✅ REALIZOWALNY

### Dlaczego to działa w tym środowisku:

1. **API dostarcza wszystko co potrzeba:**
   - Pozycję własną i wrogów (sensor_data.seen_tanks)
   - Powerupy (sensor_data.seen_powerups)
   - Przeszkody i tereny (seen_obstacles, seen_terrains)
   - Stan czołgu (my_tank_status: HP, amunicja, kąty, reload)

2. **Mapa jest dyskretyzowalna:**
   - Rozmiar: 500x500 jednostek
   - Przeszkody: 10x10, Tereny: 10x10, Czołgi: 5x5
   - Idealna siatka: **50x50 komórek (każda 10x10 jednostek)**

3. **ActionCommand obsługuje wszystkie sterowania:**
   - barrel_rotation_angle, heading_rotation_angle (dla TSK-C i TSK-D)
   - move_speed, ammo_to_load, should_fire

---

## PLAN IMPLEMENTACJI (Krok po kroku)

### Struktura Plików

```
03_FRAKCJA_AGENTOW/
├── intelligent_agent.py          # Główny plik agenta (serwer FastAPI)
├── agent_logic/
│   ├── __init__.py
│   ├── heat_map.py               # Moduł HM
│   ├── fsm.py                    # Moduł FSM
│   ├── tsk_combat.py             # Moduł TSK-C (celowanie)
│   ├── pathfinder.py             # Moduł A* 
│   ├── tsk_drive.py              # Moduł TSK-D (jazda)
│   └── utils.py                  # Funkcje pomocnicze
├── config/
│   ├── tsk_c_params.json         # Parametry FLC dla TSK-C
│   └── tsk_d_params.json         # Parametry FLC dla TSK-D
└── training/
    ├── genetic_algorithm.py      # GA do optymalizacji TSK
    └── fitness_evaluator.py      # Ocena fitness w sparingach
```

---

## MODUŁ 1: HEAT MAP (HM)

### Koncepcja
Macierz 50x50 przechowująca "ciepło" dla:
- Wrogów (wysokie wartości)
- Powerupów (średnie wartości)
- Niebezpiecznych stref (po otrzymaniu obrażeń)

**Zanikanie:** Każdy tick zmniejsza wartość o współczynnik decay (np. 0.95)

### Implementacja (heat_map.py)

```python
import numpy as np
from typing import List, Tuple

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
        for enemy in sensor_data.seen_tanks:
            gx, gy = self.world_to_grid(enemy.position.x, enemy.position.y)
            self.enemy_heat[gx, gy] = self.enemy_value
        
        # 3. Aktualizacja powerupów
        for powerup in sensor_data.seen_powerups:
            gx, gy = self.world_to_grid(powerup._position.x, powerup._position.y)
            self.powerup_heat[gx, gy] = self.powerup_value
    
    def get_hottest_enemy_position(self) -> Tuple[float, float]:
        """Zwraca współrzędne świata najgorętszego punktu z wrogami."""
        if np.max(self.enemy_heat) < 1.0:
            return None
        gx, gy = np.unravel_index(np.argmax(self.enemy_heat), self.grid_dims)
        return self.grid_to_world(gx, gy)
    
    def get_closest_powerup_position(self, my_pos) -> Tuple[float, float]:
        """Zwraca najbliższy powerup na mapie cieplnej."""
        if np.max(self.powerup_heat) < 1.0:
            return None
        
        my_gx, my_gy = self.world_to_grid(my_pos.x, my_pos.y)
        
        # Znajdź wszystkie komórki z powerupami
        powerup_positions = np.argwhere(self.powerup_heat > 1.0)
        
        if len(powerup_positions) == 0:
            return None
        
        # Znajdź najbliższy
        distances = np.sum((powerup_positions - np.array([my_gx, my_gy]))**2, axis=1)
        closest_idx = np.argmin(distances)
        gx, gy = powerup_positions[closest_idx]
        
        return self.grid_to_world(gx, gy)
```

**KLUCZOWE ASPEKTY:**
- Dyskretyzacja: 500/10 = 50 komórek na wymiar
- Decay rate 0.95: Po 100 tickach wartość spada do ~0.6% (realistyczna pamięć)
- Obsługa API: `sensor_data.seen_tanks`, `sensor_data.seen_powerups`

---

## MODUŁ 2: FINITE STATE MACHINE (FSM)

### Stany:
1. **EXPLORE** - Eksploracja mapy (brak widocznych celów)
2. **HUNT** - Polowanie na wroga (widoczny lub w HM)
3. **COLLECT_POWERUP** - Zbieranie powerupów (niskie HP/amunicja)
4. **RETREAT** - Odwrót (bardzo niskie HP)
5. **AMBUSH** - Zasadzka (dobre HP, wróg w zasięgu)

### Histereza:
Uniknięcie częstej zmiany stanów przez dodanie progów przełączania.

### Implementacja (fsm.py)

```python
from enum import Enum

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
        hp_ratio = my_tank.hp / my_tank._max_hp
        visible_enemies = len(sensor_data.seen_tanks) > 0
        total_ammo = sum(slot.count for slot in my_tank.ammo.values())
        
        hottest_enemy = heat_map.get_hottest_enemy_position()
        closest_powerup = heat_map.get_closest_powerup_position(my_tank.position)
        
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
            closest_enemy = min(sensor_data.seen_tanks, key=lambda e: e.distance)
            if closest_enemy.distance < 15 and self.current_state != AgentState.AMBUSH:
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
    
    def get_target_position(self, my_tank, sensor_data, heat_map):
        """Zwraca docelową pozycję w zależności od stanu."""
        if self.current_state == AgentState.HUNT or self.current_state == AgentState.AMBUSH:
            # Najbliższy widoczny wróg lub HM
            if sensor_data.seen_tanks:
                closest = min(sensor_data.seen_tanks, key=lambda e: e.distance)
                return (closest.position.x, closest.position.y)
            else:
                return heat_map.get_hottest_enemy_position()
        
        elif self.current_state == AgentState.COLLECT_POWERUP:
            return heat_map.get_closest_powerup_position(my_tank.position)
        
        elif self.current_state == AgentState.RETREAT:
            # Uciekaj w przeciwnym kierunku od wroga
            if sensor_data.seen_tanks:
                closest = min(sensor_data.seen_tanks, key=lambda e: e.distance)
                dx = my_tank.position.x - closest.position.x
                dy = my_tank.position.y - closest.position.y
                escape_x = my_tank.position.x + dx * 2
                escape_y = my_tank.position.y + dy * 2
                return (escape_x, escape_y)
            return None
        
        else:  # EXPLORE
            # Przeszukuj mapę (losowy punkt lub najzimniejsza część HM)
            return None  # A* wybierze losowy waypoint
```

**KLUCZOWE ASPEKTY:**
- Histereza: Różne progi wejścia/wyjścia (np. 25% vs 35% HP)
- Min duration: Zapobiega oscylacji (20 ticków = stabilność)
- Integracja z HM: Używa pamięci do decyzji

---

## MODUŁ 3: A* PATHFINDER

### Koncepcja
Wyznaczanie najkrótszej ścieżki na siatce 50x50 z uwzględnieniem:
- Przeszkód (ściany, drzewa)
- Kosztów terenów (bagno = wolniej)
- Heurystyka: Odległość euklidesowa

### Implementacja (pathfinder.py)

```python
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
        # Reset tylko widocznego obszaru (można optymalizować)
        
        for obstacle in sensor_data.seen_obstacles:
            if not obstacle.is_see_through:
                gx, gy = self.heat_map.world_to_grid(
                    obstacle._position.x, 
                    obstacle._position.y
                )
                self.obstacle_grid[gx, gy] = True
    
    def update_terrain_costs(self, sensor_data):
        """Aktualizacja kosztów terenów."""
        for terrain in sensor_data.seen_terrains:
            gx, gy = self.heat_map.world_to_grid(
                terrain._position.x,
                terrain._position.y
            )
            # Koszt odwrotnie proporcjonalny do modyfikatora prędkości
            # Droga (1.5x) -> koszt 0.67, Bagno (0.4x) -> koszt 2.5
            if hasattr(terrain, '_movement_speed_modifier'):
                self.terrain_cost_grid[gx, gy] = 1.0 / max(0.1, terrain._movement_speed_modifier)
    
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
```

**KLUCZOWE ASPEKTY:**
- Heurystyka euklidesowa: Optymalna dla ruchu swobodnego
- Uwzględnia koszty terenów (bagno droższe)
- 8-kierunkowy ruch (diagonal movement)

---

## MODUŁ 4: TSK-C (Takagi-Sugeno-Kang Combat Controller)

### Koncepcja
Regulator rozmyty typu TSK (rzędu 0/1) do:
- **Celowania:** Oblicza `barrel_rotation_angle`
- **Wyboru amunicji:** Decyduje o `ammo_to_load`
- **Decyzji o strzale:** Ustala `should_fire`

**Wejścia FLC:**
1. `distance_to_enemy` - odległość do wroga
2. `angle_error` - różnica kąta (lufa vs kierunek do wroga)
3. `enemy_health_ratio` - stan zdrowia wroga
4. `reload_status` - czy gotowy do strzału

**Wyjścia:**
1. `barrel_rotation` - kąt obrotu lufy
2. `ammo_choice` - typ amunicji (LIGHT/HEAVY/LONG_DISTANCE)
3. `fire_decision` - czy strzelać (0/1)

### Implementacja (tsk_combat.py)

```python
import numpy as np

class FuzzySet:
    """Prosta reprezentacja zbioru rozmytego (trójkątna funkcja przynależności)."""
    def __init__(self, left, center, right):
        self.left = left
        self.center = center
        self.right = right
    
    def membership(self, x):
        """Oblicza stopień przynależności dla wartości x."""
        if x <= self.left or x >= self.right:
            return 0.0
        elif x == self.center:
            return 1.0
        elif x < self.center:
            return (x - self.left) / (self.center - self.left)
        else:
            return (self.right - x) / (self.right - self.center)

class TSKCombatController:
    def __init__(self, params=None):
        """
        Inicjalizacja kontrolera TSK-C.
        
        Args:
            params: Słownik z parametrami (dla GA optimization)
        """
        self.params = params or self._default_params()
        
        # Definicja zbiorów rozmytych dla wejść
        self._define_fuzzy_sets()
    
    def _default_params(self):
        """Domyślne parametry (mogą być optymalizowane przez GA)."""
        return {
            # Progi dla odległości
            'dist_close': 8.0,
            'dist_medium': 15.0,
            'dist_far': 25.0,
            
            # Progi dla błędu kąta
            'angle_small': 5.0,
            'angle_medium': 15.0,
            'angle_large': 45.0,
            
            # Wagi dla decyzji o strzale
            'fire_angle_threshold': 10.0,
            'fire_reload_threshold': 0,
            
            # Współczynniki wyjściowe TSK (rzędu 0)
            'rotation_gain': 1.5,
            'rotation_slow_gain': 0.5,
        }
    
    def _define_fuzzy_sets(self):
        """Definicja zbiorów rozmytych."""
        p = self.params
        
        # Odległość: CLOSE, MEDIUM, FAR
        self.dist_close = FuzzySet(0, 0, p['dist_close'])
        self.dist_medium = FuzzySet(p['dist_close'], p['dist_medium'], p['dist_far'])
        self.dist_far = FuzzySet(p['dist_medium'], p['dist_far'], 100)
        
        # Kąt: SMALL, MEDIUM, LARGE
        self.angle_small = FuzzySet(0, 0, p['angle_small'])
        self.angle_medium = FuzzySet(p['angle_small'], p['angle_medium'], p['angle_large'])
        self.angle_large = FuzzySet(p['angle_medium'], p['angle_large'], 180)
    
    def compute(self, distance, angle_error, enemy_hp_ratio, reload_status, my_barrel_spin_rate):
        """
        Oblicza wyjścia kontrolera.
        
        Args:
            distance: Odległość do wroga
            angle_error: Błąd kąta (różnica między lufą a kierunkiem do wroga)
            enemy_hp_ratio: Stosunek HP wroga (0-1)
            reload_status: 0 = gotowy, >0 = przeładowywanie
            my_barrel_spin_rate: Maksymalna prędkość obrotu lufy
        
        Returns:
            dict: {
                'barrel_rotation': float,
                'ammo_type': str,
                'should_fire': bool
            }
        """
        # Normalizacja angle_error do [0, 180]
        angle_error = abs(angle_error) % 360
        if angle_error > 180:
            angle_error = 360 - angle_error
        
        # --- FUZYFIKACJA ---
        mu_close = self.dist_close.membership(distance)
        mu_medium = self.dist_medium.membership(distance)
        mu_far = self.dist_far.membership(distance)
        
        mu_angle_small = self.angle_small.membership(angle_error)
        mu_angle_medium = self.angle_medium.membership(angle_error)
        mu_angle_large = self.angle_large.membership(angle_error)
        
        # --- REGUŁY TSK (rzędu 0 - stałe wyjścia) ---
        
        # BARREL ROTATION (suma ważona)
        rotations = []
        weights = []
        
        # Reguła 1: IF angle_error is LARGE THEN rotate_fast
        w1 = mu_angle_large
        if w1 > 0:
            rotation_dir = 1.0 if angle_error > 0 else -1.0
            rotations.append(rotation_dir * my_barrel_spin_rate * self.params['rotation_gain'])
            weights.append(w1)
        
        # Reguła 2: IF angle_error is MEDIUM THEN rotate_medium
        w2 = mu_angle_medium
        if w2 > 0:
            rotation_dir = 1.0 if angle_error > 0 else -1.0
            rotations.append(rotation_dir * my_barrel_spin_rate * 0.7)
            weights.append(w2)
        
        # Reguła 3: IF angle_error is SMALL THEN rotate_slow
        w3 = mu_angle_small
        if w3 > 0:
            rotation_dir = 1.0 if angle_error > 0 else -1.0
            rotations.append(rotation_dir * my_barrel_spin_rate * self.params['rotation_slow_gain'])
            weights.append(w3)
        
        # Defuzyfikacja (ważona średnia)
        if sum(weights) > 0:
            barrel_rotation = sum(r * w for r, w in zip(rotations, weights)) / sum(weights)
        else:
            barrel_rotation = 0.0
        
        # AMMO SELECTION
        ammo_type = self._select_ammo(distance, enemy_hp_ratio, mu_close, mu_medium, mu_far)
        
        # FIRE DECISION
        should_fire = (
            angle_error < self.params['fire_angle_threshold'] and 
            reload_status == 0
        )
        
        return {
            'barrel_rotation': barrel_rotation,
            'ammo_type': ammo_type,
            'should_fire': should_fire
        }
    
    def _select_ammo(self, distance, enemy_hp_ratio, mu_close, mu_medium, mu_far):
        """Wybór amunicji na podstawie rozmytej logiki."""
        # Reguły:
        # IF distance is CLOSE AND enemy_hp high THEN HEAVY
        # IF distance is MEDIUM THEN LIGHT
        # IF distance is FAR THEN LONG_DISTANCE
        
        scores = {
            'HEAVY': mu_close * (1.0 if enemy_hp_ratio > 0.5 else 0.5),
            'LIGHT': mu_medium + mu_close * 0.5,
            'LONG_DISTANCE': mu_far
        }
        
        return max(scores, key=scores.get)
```

**KLUCZOWE ASPEKTY:**
- TSK rzędu 0: Wyjścia to stałe (łatwa optymalizacja przez GA)
- Parametry trenowalne: Progi zbiorów rozmytych i wagi
- Integracja z API: Zwraca wartości dla ActionCommand

---

## MODUŁ 5: TSK-D (Takagi-Sugeno-Kang Drive Controller)

### Koncepcja
Regulator rozmyty do sterowania ruchem:
- **Heading rotation:** Obrót kadłuba w kierunku waypointa
- **Speed control:** Prędkość jazdy w zależności od terenu i odległości

**Wejścia:**
1. `distance_to_waypoint` - odległość do kolejnego punktu trasy
2. `angle_to_waypoint` - różnica kąta (kadłub vs kierunek do waypointa)
3. `terrain_modifier` - prędkość terenu (0.4-1.5)

**Wyjścia:**
1. `heading_rotation` - kąt obrotu kadłuba
2. `move_speed` - prędkość ruchu

### Implementacja (tsk_drive.py)

```python
import numpy as np

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
            waypoint: (x, y) docelowy punkt
            my_position: Position obecna pozycja
            my_heading: float aktualny kąt kadłuba
            my_heading_spin_rate: float max prędkość obrotu
            my_top_speed: float max prędkość jazdy
            terrain_modifier: float modyfikator terenu
        
        Returns:
            dict: {'heading_rotation': float, 'move_speed': float}
        """
        if waypoint is None:
            return {'heading_rotation': 0.0, 'move_speed': 0.0}
        
        # Oblicz różnicę kąta
        dx = waypoint[0] - my_position.x
        dy = waypoint[1] - my_position.y
        distance = np.sqrt(dx**2 + dy**2)
        
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
```

**KLUCZOWE ASPEKTY:**
- Obrót kadłuba w kierunku waypointa
- Prędkość zależna od kąta i terenu
- Zatrzymanie przy osiągnięciu celu

---

## MODUŁ 6: INTEGRACJA (intelligent_agent.py)

### Główny Agent - Łączenie wszystkich modułów

```python
"""
Inteligentny Agent Czołgu z architekturą HM + FSM + TSK + A*
"""

import sys
import os
from typing import Dict, Any
from fastapi import FastAPI, Body
from pydantic import BaseModel
import uvicorn
import argparse

# Import modułów agenta
from agent_logic.heat_map import HeatMap
from agent_logic.fsm import FSM, AgentState
from agent_logic.pathfinder import AStarPathfinder
from agent_logic.tsk_combat import TSKCombatController
from agent_logic.tsk_drive import TSKDriveController

# Import API struktur
parent_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '02_FRAKCJA_SILNIKA')
sys.path.insert(0, parent_dir)

from backend.structures.ammo import AmmoType
from backend.structures.position import Position


class ActionCommand(BaseModel):
    """Output action from agent to engine."""
    barrel_rotation_angle: float = 0.0
    heading_rotation_angle: float = 0.0
    move_speed: float = 0.0
    ammo_to_load: str = None
    should_fire: bool = False


class IntelligentAgent:
    """Agent z architekturą HM + FSM + TSK + A*."""
    
    def __init__(self, name: str = "IntelligentBot"):
        self.name = name
        self.is_destroyed = False
        
        # Inicjalizacja modułów
        self.heat_map = HeatMap()
        self.fsm = FSM()
        self.pathfinder = AStarPathfinder(self.heat_map)
        self.tsk_combat = TSKCombatController()
        self.tsk_drive = TSKDriveController()
        
        # Stan nawigacji
        self.current_path = None
        self.current_waypoint = None
        self.waypoint_index = 0
        
        print(f"[{self.name}] Intelligent Agent initialized")
    
    def get_action(
        self, 
        current_tick: int, 
        my_tank_status: Dict[str, Any], 
        sensor_data: Dict[str, Any], 
        enemies_remaining: int
    ) -> ActionCommand:
        """Główna pętla decyzyjna agenta."""
        
        # --- 1. AKTUALIZACJA HEAT MAP ---
        self.heat_map.update(sensor_data, my_tank_status['position'])
        
        # --- 2. AKTUALIZACJA PATHFINDER ---
        self.pathfinder.update_obstacles(sensor_data)
        self.pathfinder.update_terrain_costs(sensor_data)
        
        # --- 3. FSM - Decyzja strategiczna ---
        current_state = self.fsm.update(my_tank_status, sensor_data, self.heat_map)
        target_position = self.fsm.get_target_position(my_tank_status, sensor_data, self.heat_map)
        
        # --- 4. A* - Wyznaczenie ścieżki ---
        if target_position:
            current_pos = (my_tank_status['position']['x'], my_tank_status['position']['y'])
            
            # Przelicz ścieżkę co kilka ticków lub po osiągnięciu waypointa
            if self.current_path is None or self.waypoint_index >= len(self.current_path):
                self.current_path = self.pathfinder.find_path(current_pos, target_position)
                self.waypoint_index = 0
            
            # Wybierz bieżący waypoint
            if self.current_path and self.waypoint_index < len(self.current_path):
                self.current_waypoint = self.current_path[self.waypoint_index]
                
                # Sprawdź czy osiągnięto waypoint (próg 5 jednostek)
                wp_dist = ((current_pos[0] - self.current_waypoint[0])**2 + 
                          (current_pos[1] - self.current_waypoint[1])**2)**0.5
                if wp_dist < 5.0:
                    self.waypoint_index += 1
        
        # --- 5. TSK-D - Sterowanie ruchem ---
        position_obj = type('Position', (), {
            'x': my_tank_status['position']['x'],
            'y': my_tank_status['position']['y']
        })()
        
        drive_output = self.tsk_drive.compute(
            waypoint=self.current_waypoint,
            my_position=position_obj,
            my_heading=my_tank_status['heading'],
            my_heading_spin_rate=my_tank_status['_heading_spin_rate'],
            my_top_speed=my_tank_status['_top_speed'],
            terrain_modifier=1.0  # TODO: Pobierz z terenu pod czołgiem
        )
        
        # --- 6. TSK-C - Sterowanie walką ---
        combat_output = {'barrel_rotation': 0.0, 'ammo_type': 'LIGHT', 'should_fire': False}
        
        if sensor_data['seen_tanks']:
            # Wybierz najbliższego wroga
            closest_enemy = min(sensor_data['seen_tanks'], key=lambda e: e['distance'])
            
            # Oblicz błąd kąta między lufą a wrogiem
            dx = closest_enemy['position']['x'] - my_tank_status['position']['x']
            dy = closest_enemy['position']['y'] - my_tank_status['position']['y']
            import math
            target_barrel_angle = math.degrees(math.atan2(dx, dy)) % 360
            
            angle_error = target_barrel_angle - my_tank_status['barrel_angle']
            
            combat_output = self.tsk_combat.compute(
                distance=closest_enemy['distance'],
                angle_error=angle_error,
                enemy_hp_ratio=0.5,  # TODO: Szacuj HP wroga
                reload_status=my_tank_status['current_reload_progress'],
                my_barrel_spin_rate=my_tank_status['_barrel_spin_rate']
            )
        
        # --- 7. GENEROWANIE AKCJI ---
        return ActionCommand(
            barrel_rotation_angle=combat_output['barrel_rotation'],
            heading_rotation_angle=drive_output['heading_rotation'],
            move_speed=drive_output['move_speed'],
            ammo_to_load=combat_output['ammo_type'],
            should_fire=combat_output['should_fire']
        )
    
    def destroy(self):
        self.is_destroyed = True
        print(f"[{self.name}] Tank destroyed!")
    
    def end(self, damage_dealt: float, tanks_killed: int):
        print(f"[{self.name}] Game ended!")
        print(f"[{self.name}] Damage dealt: {damage_dealt}")
        print(f"[{self.name}] Tanks killed: {tanks_killed}")


# FastAPI Server
app = FastAPI(title="Intelligent Tank Agent", version="1.0.0")
agent = IntelligentAgent()

@app.get("/")
async def root():
    return {"message": f"Agent {agent.name} is running", "destroyed": agent.is_destroyed}

@app.post("/agent/action", response_model=ActionCommand)
async def get_action(payload: Dict[str, Any] = Body(...)):
    action = agent.get_action(
        current_tick=payload.get('current_tick', 0),
        my_tank_status=payload.get('my_tank_status', {}),
        sensor_data=payload.get('sensor_data', {}),
        enemies_remaining=payload.get('enemies_remaining', 0)
    )
    return action

@app.post("/agent/destroy", status_code=204)
async def destroy():
    agent.destroy()

@app.post("/agent/end", status_code=204)
async def end(payload: Dict[str, Any] = Body(...)):
    agent.end(
        damage_dealt=payload.get('damage_dealt', 0.0),
        tanks_killed=payload.get('tanks_killed', 0)
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--name", type=str, default="IntelligentBot")
    args = parser.parse_args()
    
    agent.name = args.name
    print(f"Starting {agent.name} on port {args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
```

---

## MODUŁ 7: TRENING Z ALGORYTMEM GENETYCZNYM

### Koncepcja
Optymalizacja parametrów TSK-C i TSK-D przez GA:
- **Genotyp:** Parametry kontrolerów (progi, wagi)
- **Fitness:** Średni wynik ze sparingów (damage dealt, tanks killed, survival time)
- **Sparingi:** Automatyczne uruchamianie gier headless przeciwko innym agentom

### Implementacja (training/genetic_algorithm.py)

```python
"""
Algorytm Genetyczny do optymalizacji parametrów TSK-C i TSK-D
"""

import numpy as np
import json
from copy import deepcopy
from typing import List, Dict

class GeneticAlgorithm:
    def __init__(
        self, 
        population_size: int = 20, 
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.7,
        elite_size: int = 2
    ):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_size = elite_size
        
        # Definicja przestrzeni parametrów
        self.param_ranges = {
            # TSK-C
            'dist_close': (5.0, 12.0),
            'dist_medium': (12.0, 20.0),
            'dist_far': (20.0, 35.0),
            'angle_small': (3.0, 10.0),
            'angle_medium': (10.0, 25.0),
            'angle_large': (25.0, 60.0),
            'fire_angle_threshold': (5.0, 15.0),
            'rotation_gain': (0.8, 2.0),
            'rotation_slow_gain': (0.3, 0.8),
            
            # TSK-D
            'angle_threshold_small': (5.0, 15.0),
            'angle_threshold_large': (30.0, 60.0),
            'distance_close': (10.0, 25.0),
            'distance_far': (35.0, 70.0),
            'speed_max_multiplier': (0.8, 1.0),
            'speed_min_multiplier': (0.2, 0.5),
        }
    
    def initialize_population(self) -> List[Dict]:
        """Tworzy losową populację parametrów."""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for param, (min_val, max_val) in self.param_ranges.items():
                individual[param] = np.random.uniform(min_val, max_val)
            population.append(individual)
        return population
    
    def evaluate_fitness(self, individual: Dict, opponent_agent_path: str, num_games: int = 5) -> float:
        """
        Ocena osobnika przez sparingi.
        
        Args:
            individual: Parametry do oceny
            opponent_agent_path: Ścieżka do agenta przeciwnika
            num_games: Liczba gier do testów
        
        Returns:
            float: Fitness score (wyższy = lepszy)
        """
        # TODO: Implementacja uruchamiania gier headless
        # 1. Zapisz parametry individual do pliku config
        # 2. Uruchom silnik w trybie headless
        # 3. Zbierz wyniki: damage_dealt, tanks_killed, survival_time
        # 4. Oblicz fitness = weighted_sum(metrics)
        
        # PLACEHOLDER:
        total_score = 0.0
        for game in range(num_games):
            # Uruchom grę...
            damage_dealt = np.random.uniform(0, 500)  # Symulacja
            tanks_killed = np.random.randint(0, 5)
            survival_time = np.random.uniform(0, 10000)
            
            # Funkcja fitness (do tuningu)
            score = (damage_dealt * 0.5 + 
                    tanks_killed * 100 + 
                    survival_time * 0.01)
            total_score += score
        
        return total_score / num_games
    
    def selection(self, population: List[Dict], fitness_scores: List[float]) -> List[Dict]:
        """Selekcja turniejowa."""
        selected = []
        
        # Elityźm - zachowaj najlepszych
        sorted_pop = [x for _, x in sorted(zip(fitness_scores, population), reverse=True)]
        selected.extend(sorted_pop[:self.elite_size])
        
        # Selekcja turniejowa dla reszty
        for _ in range(self.population_size - self.elite_size):
            tournament = np.random.choice(len(population), size=3, replace=False)
            tournament_fitness = [fitness_scores[i] for i in tournament]
            winner_idx = tournament[np.argmax(tournament_fitness)]
            selected.append(deepcopy(population[winner_idx]))
        
        return selected
    
    def crossover(self, parent1: Dict, parent2: Dict) -> Dict:
        """Krzyżowanie jednopunktowe."""
        if np.random.random() > self.crossover_rate:
            return deepcopy(parent1)
        
        child = {}
        for param in parent1.keys():
            if np.random.random() < 0.5:
                child[param] = parent1[param]
            else:
                child[param] = parent2[param]
        
        return child
    
    def mutate(self, individual: Dict) -> Dict:
        """Mutacja gaussowska."""
        mutated = deepcopy(individual)
        
        for param, value in mutated.items():
            if np.random.random() < self.mutation_rate:
                min_val, max_val = self.param_ranges[param]
                noise = np.random.normal(0, (max_val - min_val) * 0.1)
                mutated[param] = np.clip(value + noise, min_val, max_val)
        
        return mutated
    
    def evolve(self, generations: int = 50, opponent_path: str = "random_agent.py"):
        """Główna pętla ewolucyjna."""
        population = self.initialize_population()
        
        best_fitness_history = []
        
        for gen in range(generations):
            print(f"\n=== Generation {gen+1}/{generations} ===")
            
            # Ocena fitness
            fitness_scores = []
            for i, individual in enumerate(population):
                fitness = self.evaluate_fitness(individual, opponent_path)
                fitness_scores.append(fitness)
                print(f"  Individual {i+1}: Fitness = {fitness:.2f}")
            
            # Zapisz najlepszego
            best_idx = np.argmax(fitness_scores)
            best_fitness = fitness_scores[best_idx]
            best_individual = population[best_idx]
            best_fitness_history.append(best_fitness)
            
            print(f"\nBest fitness: {best_fitness:.2f}")
            
            # Zapisz najlepszego do pliku
            with open(f'best_params_gen_{gen+1}.json', 'w') as f:
                json.dump(best_individual, f, indent=2)
            
            # Selekcja
            selected = self.selection(population, fitness_scores)
            
            # Krzyżowanie i mutacja
            new_population = selected[:self.elite_size]  # Elita przechodzi bez zmian
            
            while len(new_population) < self.population_size:
                parent1 = np.random.choice(selected)
                parent2 = np.random.choice(selected)
                child = self.crossover(parent1, parent2)
                child = self.mutate(child)
                new_population.append(child)
            
            population = new_population
        
        return population, best_fitness_history


if __name__ == "__main__":
    ga = GeneticAlgorithm(population_size=20, mutation_rate=0.15)
    population, history = ga.evolve(generations=30)
    
    print("\n=== Training Complete ===")
    print(f"Best fitness progression: {history}")
```

---

## PLAN WDROŻENIA (Kolejność kroków)

### FAZA 1: Bazowa Implementacja (Tydzień 1)
1. ✅ Weryfikacja pomysłu (GOTOWE - to właśnie czytasz)
2. Utworzenie struktury katalogów
3. Implementacja HeatMap + testy jednostkowe
4. Implementacja FSM + testy logiczne
5. Implementacja prostego pathfindera (bez A*, tylko direct path)

### FAZA 2: Sterowanie (Tydzień 2)
6. Implementacja TSK-C z domyślnymi parametrami
7. Implementacja TSK-D z domyślnymi parametrami
8. Integracja wszystkich modułów w intelligent_agent.py
9. Pierwsze testy z silnikiem (sparingi vs random_agent)

### FAZA 3: Zaawansowana Nawigacja (Tydzień 3)
10. Pełna implementacja A* pathfinder
11. Integracja kosztów terenów
12. Optymalizacja wydajności A*

### FAZA 4: Trening (Tydzień 4-5)
13. Implementacja Genetic Algorithm
14. Automatyzacja sparingów headless
15. Optymalizacja parametrów TSK-C i TSK-D
16. Analiza wyników i fine-tuning

### FAZA 5: Testy finałowe (Tydzień 6)
17. Sparingi z innymi agentami
18. Debugging edge cases
19. Dokumentacja i raport
20. Zamrożenie wersji finalnej

---

## KLUCZOWE UWAGI IMPLEMENTACYJNE

### 1. Kompatybilność z API
- Wszystkie struktury danych zgodne z [final_api.py](c:\Users\Filip\Documents\studia-local\tank-agent-ai\01_DOKUMENTACJA\final_api.py)
- ActionCommand zwraca poprawne typy
- Obsługa FastAPI identyczna jak w [random_agent.py](c:\Users\Filip\Documents\studia-local\tank-agent-ai\03_FRAKCJA_AGENTOW\random_agent.py)

### 2. Wydajność
- HeatMap: O(1) update per cell, O(N*M) decay
- A*: O(N log N) gdzie N = liczba komórek
- FSM: O(1) per tick
- TSK: O(K) gdzie K = liczba reguł (~10)
- **Łączny czas: <5ms per tick** (akceptowalne)

### 3. Testowanie
- **Testy jednostkowe:** Każdy moduł osobno (heat_map, fsm, pathfinder, tsk)
- **Testy integracyjne:** Cały agent vs random_agent
- **Testy sparingowe:** Agent vs konkurencja

### 4. Optymalizacja GA
- **Genotyp:** 15 parametrów (progi i wagi)
- **Populacja:** 20 osobników
- **Generacje:** 30-50
- **Fitness:** Ważona suma (damage, kills, survival)
- **Czas:** ~10-20 godzin (500+ gier)

---

## WYMAGANE NARZĘDZIA I BIBLIOTEKI

```bash
# requirements.txt dla agenta
numpy>=1.21.0
scipy>=1.7.0
fastapi>=0.95.0
uvicorn>=0.21.0
pydantic>=1.10.0
```

---

## PODSUMOWANIE

### ✅ POMYSŁ JEST REALIZOWALNY

**Wszystkie komponenty są możliwe do zaimplementowania:**
- HeatMap: Pamięć + zanikanie ✓
- FSM: Strategia z histerezą ✓
- TSK-C/TSK-D: Regulatory rozmyte TSK ✓
- A*: Nawigacja z heurystyką ✓
- GA: Trening parametrów ✓

**API dostarcza wszystkich niezbędnych danych:**
- Pozycje wrogów i powerupów ✓
- Przeszkody i tereny ✓
- Stan czołgu (HP, amunicja, kąty) ✓
- Akcje sterowania (rotation, speed, fire) ✓

**Architektura jest spójna:**
1. Sensory → HeatMap (pamięć)
2. HeatMap + MyTank → FSM (strategia)
3. FSM → Target → A* (ścieżka)
4. Waypoint → TSK-D (ruch)
5. Enemy → TSK-C (walka)
6. Actions → Engine

### 🎯 NASTĘPNE KROKI

1. **TERAZ:** Utworzyć strukturę katalogów i plików
2. **Dzisiaj:** Zaimplementować HeatMap i FSM
3. **Jutro:** TSK-C/TSK-D + integracja
4. **Weekend:** A* pathfinder
5. **Przyszły tydzień:** GA training

**Powodzenia!** 🎮 🤖
