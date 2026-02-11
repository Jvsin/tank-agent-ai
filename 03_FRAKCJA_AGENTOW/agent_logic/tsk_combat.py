"""
TSK-C (Takagi-Sugeno-Kang Combat Controller)
Kontroler rozmyty do celowania, wyboru amunicji i decyzji o strzale.
"""

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
        angle_error_abs = abs(angle_error) % 360
        if angle_error_abs > 180:
            angle_error_abs = 360 - angle_error_abs
        
        # Zachowaj kierunek obrotu
        rotation_dir = 1.0 if angle_error > 0 else -1.0
        
        # --- FUZYFIKACJA ---
        mu_close = self.dist_close.membership(distance)
        mu_medium = self.dist_medium.membership(distance)
        mu_far = self.dist_far.membership(distance)
        
        mu_angle_small = self.angle_small.membership(angle_error_abs)
        mu_angle_medium = self.angle_medium.membership(angle_error_abs)
        mu_angle_large = self.angle_large.membership(angle_error_abs)
        
        # --- REGUŁY TSK (rzędu 0 - stałe wyjścia) ---
        
        # BARREL ROTATION (suma ważona)
        rotations = []
        weights = []
        
        # Reguła 1: IF angle_error is LARGE THEN rotate_fast
        w1 = mu_angle_large
        if w1 > 0:
            rotations.append(rotation_dir * my_barrel_spin_rate * self.params['rotation_gain'])
            weights.append(w1)
        
        # Reguła 2: IF angle_error is MEDIUM THEN rotate_medium
        w2 = mu_angle_medium
        if w2 > 0:
            rotations.append(rotation_dir * my_barrel_spin_rate * 0.7)
            weights.append(w2)
        
        # Reguła 3: IF angle_error is SMALL THEN rotate_slow
        w3 = mu_angle_small
        if w3 > 0:
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
            angle_error_abs < self.params['fire_angle_threshold'] and 
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
