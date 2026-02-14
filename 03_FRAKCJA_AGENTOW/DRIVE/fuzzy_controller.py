"""
PROSTY KONTROLER RUCHU CZOŁGU - LOGIKA ROZMYTA (FUZZY LOGIC)
=============================================================

Ten moduł używa logiki rozmytej (fuzzy logic) do podejmowania decyzji o ruchu czołgu.
Zamiast ostrych warunków (if distance < 10), używamy stopniowych przejść.

Przykład:
    "Jeśli wróg jest BLISKO i moje HP jest WYSOKIE, to jedź SZYBKO do przodu"
    
    BLISKO nie oznacza konkretnej liczby, ale funkcję przynależności:
    - 5m = 100% blisko
    - 15m = 50% blisko
    - 30m = 0% blisko
"""

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl 
from typing import Dict, Any, Tuple, Optional
import math


class FuzzyMotionController:
    """
    Kontroler ruchu czołgu używający logiki rozmytej.
    
    WEJŚCIA (co widzimy):
        - odległość do najbliższego wroga
        - procent HP czołgu
        - odległość do najbliższej przeszkody przed czołgiem
        
    WYJŚCIA (co robimy):
        - zmiana kierunku jazdy (heading)
        - prędkość ruchu
    """
    
    def __init__(self):
        """Inicjalizacja systemu rozmytego - definiujemy zmienne i reguły."""
        print("[FuzzyController] Inicjalizacja...")
        
        # Stan eksploracji (gdy nie ma wrogów)
        self.exploration_heading_offset = 0.0  # Losowy offset eksploracji
        self.exploration_timer = 0  # Co ile ticków zmieniać kierunek
        
        # ===================================================================
        # KROK 1: DEFINICJA ZMIENNYCH WEJŚCIOWYCH (Antecedent)
        # ===================================================================
        
        # Odległość do wroga (0-100 metrów)
        self.enemy_distance = ctrl.Antecedent(np.arange(0, 101, 1), 'enemy_distance')
        
        # HP czołgu (0-100%)
        self.hp_percent = ctrl.Antecedent(np.arange(0, 101, 1), 'hp_percent')
        
        # Odległość do przeszkody (0-50 metrów)
        self.obstacle_distance = ctrl.Antecedent(np.arange(0, 51, 1), 'obstacle_distance')
        
        # ===================================================================
        # KROK 2: DEFINICJA ZMIENNYCH WYJŚCIOWYCH (Consequent)
        # ===================================================================
        
        # Docelowa prędkość (-50 do +50, gdzie minus = cofanie)
        self.target_speed = ctrl.Consequent(np.arange(-50, 51, 1), 'target_speed')
        
        # Siła skrętu w stronę wroga (-1.0 = odwróć się, 0 = nie zmieniaj, +1.0 = skręć do wroga)
        self.turn_to_enemy = ctrl.Consequent(np.arange(-1, 1.1, 0.1), 'turn_to_enemy')
        
        # ===================================================================
        # KROK 3: FUNKCJE PRZYNALEŻNOŚCI (membership functions)
        # Definiujemy co oznacza "blisko", "średnio", "daleko" itd.
        # ===================================================================
        
        # --- Odległość do wroga ---
        self.enemy_distance['very_close'] = fuzz.trimf(self.enemy_distance.universe, [0, 0, 15])
        self.enemy_distance['close'] = fuzz.trimf(self.enemy_distance.universe, [10, 20, 35])
        self.enemy_distance['medium'] = fuzz.trimf(self.enemy_distance.universe, [30, 45, 60])
        self.enemy_distance['far'] = fuzz.trimf(self.enemy_distance.universe, [55, 100, 100])
        
        # --- HP czołgu ---
        self.hp_percent['critical'] = fuzz.trimf(self.hp_percent.universe, [0, 0, 25])
        self.hp_percent['low'] = fuzz.trimf(self.hp_percent.universe, [20, 40, 60])
        self.hp_percent['high'] = fuzz.trimf(self.hp_percent.universe, [55, 75, 100])
        self.hp_percent['full'] = fuzz.trimf(self.hp_percent.universe, [80, 100, 100])
        
        # --- Przeszkoda przed czołgiem ---
        self.obstacle_distance['collision'] = fuzz.trimf(self.obstacle_distance.universe, [0, 0, 5])
        self.obstacle_distance['very_close'] = fuzz.trimf(self.obstacle_distance.universe, [3, 8, 12])
        self.obstacle_distance['safe'] = fuzz.trimf(self.obstacle_distance.universe, [10, 50, 50])
        
        # --- Prędkość (wyjście) ---
        self.target_speed['fast_reverse'] = fuzz.trimf(self.target_speed.universe, [-50, -40, -20])
        self.target_speed['slow_reverse'] = fuzz.trimf(self.target_speed.universe, [-30, -15, 0])
        self.target_speed['stop'] = fuzz.trimf(self.target_speed.universe, [-5, 0, 5])  # Wąski zakres!
        self.target_speed['slow_forward'] = fuzz.trimf(self.target_speed.universe, [5, 18, 32])  # Uniesiony od 0
        self.target_speed['fast_forward'] = fuzz.trimf(self.target_speed.universe, [25, 40, 50])
        
        # --- Skręt w stronę wroga (wyjście) ---
        self.turn_to_enemy['turn_away'] = fuzz.trimf(self.turn_to_enemy.universe, [-1, -1, -0.3])
        self.turn_to_enemy['slight_away'] = fuzz.trimf(self.turn_to_enemy.universe, [-0.5, -0.2, 0])
        self.turn_to_enemy['neutral'] = fuzz.trimf(self.turn_to_enemy.universe, [-0.2, 0, 0.2])
        self.turn_to_enemy['slight_toward'] = fuzz.trimf(self.turn_to_enemy.universe, [0, 0.3, 0.6])
        self.turn_to_enemy['turn_toward'] = fuzz.trimf(self.turn_to_enemy.universe, [0.5, 1, 1])
        
        # ===================================================================
        # KROK 4: REGUŁY DECYZYJNE (to jest mózg systemu!)
        # ===================================================================
        
        rules = []
        
        # --- REGUŁY BEZPIECZEŃSTWA (najwyższy priorytet) ---
        
        # R1: Przeszkoda tuż przed nami → STOP natychmiast!
        rules.append(ctrl.Rule(
            self.obstacle_distance['collision'],
            (self.target_speed['stop'], self.turn_to_enemy['neutral'])
        ))
        
        # R2: Przeszkoda bardzo blisko → zwalniaj
        rules.append(ctrl.Rule(
            self.obstacle_distance['very_close'],
            (self.target_speed['slow_forward'], self.turn_to_enemy['neutral'])
        ))
        
        # --- REGUŁY WALKI (gdy wróg w zasięgu) ---
        
        # R3: Wróg bardzo blisko + HP wysokie → ATAK! Jedź do przodu, celuj
        rules.append(ctrl.Rule(
            self.enemy_distance['very_close'] & (self.hp_percent['high'] | self.hp_percent['full']),
            (self.target_speed['fast_forward'], self.turn_to_enemy['turn_toward'])
        ))
        
        # R4: Wróg bardzo blisko + HP krytyczne → UCIECZKA! Cofaj i odwróć się
        rules.append(ctrl.Rule(
            self.enemy_distance['very_close'] & self.hp_percent['critical'],
            (self.target_speed['fast_reverse'], self.turn_to_enemy['turn_away'])
        ))
        
        # R5: Wróg blisko + HP niskie → ostrożnie, lekko się wycofaj
        rules.append(ctrl.Rule(
            self.enemy_distance['close'] & self.hp_percent['low'],
            (self.target_speed['slow_reverse'], self.turn_to_enemy['slight_away'])
        ))
        
        # R6: Wróg blisko + HP wysokie → jedź do przodu, atakuj
        rules.append(ctrl.Rule(
            self.enemy_distance['close'] & (self.hp_percent['high'] | self.hp_percent['full']),
            (self.target_speed['fast_forward'], self.turn_to_enemy['turn_toward'])
        ))
        
        # R7: Wróg w średniej odległości → jedź powoli do przodu, celuj
        rules.append(ctrl.Rule(
            self.enemy_distance['medium'],
            (self.target_speed['slow_forward'], self.turn_to_enemy['slight_toward'])
        ))
        
        # R8: Wróg daleko → jedź spokojnie, lekko celuj
        rules.append(ctrl.Rule(
            self.enemy_distance['far'],
            (self.target_speed['slow_forward'], self.turn_to_enemy['slight_toward'])
        ))
        
        # --- REGUŁA DOMYŚLNA ---
        
        # R9: Gdy nic się nie dzieje → patrol (wolno do przodu)
        rules.append(ctrl.Rule(
            self.enemy_distance['far'] & self.obstacle_distance['safe'],
            (self.target_speed['slow_forward'], self.turn_to_enemy['neutral'])
        ))
        
        # ===================================================================
        # KROK 5: STWÓRZ SYSTEM KONTROLNY
        # ===================================================================
        
        self.control_system = ctrl.ControlSystem(rules)
        self.controller = ctrl.ControlSystemSimulation(self.control_system)
        
        print("[FuzzyController] ✓ System gotowy! Zdefiniowano", len(rules), "reguł.")
    
    def compute_motion(
        self,
        my_position: Tuple[float, float],
        my_heading: float,
        my_hp: float,
        max_hp: float,
        sensor_data: Dict[str, Any]
    ) -> Tuple[float, float]:
        """
        Główna metoda - oblicza jak czołg powinien się poruszać.
        
        Args:
            my_position: Moja pozycja (x, y)
            my_heading: Mój obecny kierunek w stopniach (0-360)
            my_hp: Aktualne HP
            max_hp: Maksymalne HP
            sensor_data: Dane z sensorów (seen_tanks, seen_obstacles, etc.)
            
        Returns:
            (heading_rotation, move_speed) - kąt obrotu i prędkość
        """
        
        # ===================================================================
        # KROK 1: EKSTRAKCJA DANYCH Z SENSORÓW
        # ===================================================================
        
        # Znajdź najbliższego wroga
        closest_enemy_dist = 100.0  # Domyślnie daleko
        enemy_angle = 0.0  # Kąt do wroga
        enemies_visible = False  # Flaga czy widzimy wrogów
        
        seen_tanks = sensor_data.get('seen_tanks', [])
        if seen_tanks:
            enemies_visible = True
            min_dist = float('inf')
            closest_enemy = None
            
            for tank in seen_tanks:
                # Oblicz odległość
                tank_pos = tank.get('position', {})
                if isinstance(tank_pos, dict):
                    tx, ty = tank_pos.get('x', 0), tank_pos.get('y', 0)
                else:
                    tx, ty = getattr(tank_pos, 'x', 0), getattr(tank_pos, 'y', 0)
                
                dx = tx - my_position[0]
                dy = ty - my_position[1]
                dist = math.sqrt(dx*dx + dy*dy)
                
                if dist < min_dist:
                    min_dist = dist
                    closest_enemy = (tx, ty)
                    # Oblicz kąt do wroga (0=north, CW)
                    enemy_angle = math.degrees(math.atan2(dx, dy)) % 360
            
            closest_enemy_dist = min_dist
        
        # Znajdź najbliższą przeszkodę PRZED czołgiem
        obstacle_dist = 50.0  # Domyślnie bezpiecznie
        
        seen_obstacles = sensor_data.get('seen_obstacles', [])
        for obstacle in seen_obstacles:
            # Pozycja przeszkody
            obs_pos = obstacle.get('position', obstacle.get('_position', {}))
            if isinstance(obs_pos, dict):
                ox, oy = obs_pos.get('x', 0), obs_pos.get('y', 0)
            else:
                ox, oy = getattr(obs_pos, 'x', 0), getattr(obs_pos, 'y', 0)
            
            dx = ox - my_position[0]
            dy = oy - my_position[1]
            dist = math.sqrt(dx*dx + dy*dy)
            
            # Sprawdź czy przeszkoda jest PRZED nami (w kierunku heading)
            angle_to_obs = math.degrees(math.atan2(dx, dy)) % 360
            angle_diff = self._normalize_angle_diff(angle_to_obs - my_heading)
            
            # Jeśli przeszkoda jest w przedziale ±60° przed nami
            if abs(angle_diff) < 60 and dist < obstacle_dist:
                obstacle_dist = dist
        
        # Oblicz procent HP
        hp_percent = (my_hp / max_hp) * 100.0 if max_hp > 0 else 0.0
        
        # ===================================================================
        # KROK 2: USTAW WEJŚCIA DO SYSTEMU ROZMYTEGO
        # ===================================================================
        
        self.controller.input['enemy_distance'] = min(closest_enemy_dist, 100.0)
        self.controller.input['hp_percent'] = max(0.0, min(100.0, hp_percent))
        self.controller.input['obstacle_distance'] = min(obstacle_dist, 50.0)
        
        # ===================================================================
        # KROK 3: WYKONAJ WNIOSKOWANIE ROZMYTE
        # ===================================================================
        
        try:
            self.controller.compute()
        except Exception as e:
            print(f"[FuzzyController] Błąd obliczeń: {e}")
            # Wartości awaryjne
            return 0.0, 10.0
        
        # ===================================================================
        # KROK 4: POBIERZ WYJŚCIA
        # ===================================================================
        
        speed_output = self.controller.output['target_speed']
        turn_factor = self.controller.output['turn_to_enemy']
        
        # ===================================================================
        # KROK 5: PRZELICZ NA RZECZYWISTE KOMENDY
        # ===================================================================
        
        # ===================================================================
        # KROK 6: TRYB EKSPLORACJI (gdy nie ma wrogów w zasięgu)
        # ===================================================================
        
        if not enemies_visible:
            # EKSPLORACJA - jedź prosto z losowymi skrętami
            self.exploration_timer -= 1
            
            if self.exploration_timer <= 0:
                # Co 30-60 ticków zmień kierunek eksploracji
                import random
                self.exploration_heading_offset = random.uniform(-20.0, 20.0)
                self.exploration_timer = random.randint(30, 60)
            
            # Jedź prosto, a skręcaj tylko gdy przeszkoda jest blisko
            if obstacle_dist > 15.0:
                heading_rotation = 0.0
            else:
                heading_rotation = max(-15.0, min(15.0, self.exploration_heading_offset))
            move_speed = 30.0  # Stała prędkość eksploracji
            
        else:
            # NORMALNY TRYB - reaguj na wroga
            # Oblicz różnicę kąta między naszym heading a kierunkiem do wroga
            angle_diff = self._normalize_angle_diff(enemy_angle - my_heading)
            abs_angle_diff = abs(angle_diff)
            
            # Skręt: turn_factor * angle_diff
            # Jeśli turn_factor = 1.0 → skręcamy maksymalnie w stronę wroga
            # Jeśli turn_factor = -1.0 → skręcamy maksymalnie od wroga
            # Jeśli turn_factor = 0.0 → nie skręcamy
            heading_rotation = turn_factor * min(45.0, max(-45.0, angle_diff))
            # Deadzone przeciwko "kręceniu się" przy małym błędzie
            if abs_angle_diff < 6.0:
                heading_rotation = 0.0
            
            move_speed = speed_output
            
            # ZAWSZE JAKIŚ SENSOWNY RUCH - nie stój w miejscu!
            # Wyjątek: celowanie do wroga z bliska (można stanąć i celować)
            can_stand_still = (closest_enemy_dist < 30.0 and hp_percent > 30.0)
            
            if abs(move_speed) < 5.0 and not can_stand_still:
                # Brak sensownej prędkości i nie celujemy - jedź do przodu eksplorując
                move_speed = 20.0
                if obstacle_dist < 15.0:
                    # Przeszkoda przed nami - jedź wolniej
                    move_speed = 12.0
            
            # Ogranicz przypadkowe cofanie, gdy nie ma realnej potrzeby odwrotu
            if move_speed < 0:
                should_retreat = (closest_enemy_dist < 12.0 and hp_percent < 35.0)
                if not should_retreat and obstacle_dist > 10.0:
                    # Nie ma powodu do cofania - jedź do przodu
                    move_speed = 15.0
        
        return heading_rotation, move_speed
    
    def _normalize_angle_diff(self, angle: float) -> float:
        """
        Normalizuje różnicę kątów do zakresu [-180, 180].
        Przykład: 350° - 10° = -20° (a nie 340°)
        """
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle
