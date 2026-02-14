"""
DECISION MAKER - HIERARCHIA REGUŁ DECYZYJNYCH
==============================================

Ten moduł zawiera hierarchiczny system decyzyjny dla czołgu.
Sprawdza reguły od najważniejszych do najmniej ważnych.
Pierwsza pasująca reguła wygrywa.

HIERARCHIA PRIORYTETÓW:
1. Szkodliwy teren (100) - Uciekaj natychmiast!
2. Kolizja z przeszkodą (99) - Stop i skręć!
3. Powerup w pobliżu (50) - Zbierz jeśli bezpiecznie
"""

from typing import Dict, Any, Optional, Tuple
import math


# ============================================================================
# FUNKCJE POMOCNICZE
# ============================================================================

def distance_2d(x1: float, y1: float, x2: float, y2: float) -> float:
    """Oblicz odległość między dwoma punktami."""
    dx = x2 - x1
    dy = y2 - y1
    return math.sqrt(dx*dx + dy*dy)


def angle_to_target(from_x: float, from_y: float, to_x: float, to_y: float) -> float:
    """Oblicz kąt do celu (w stopniach) zgodny z silnikiem (0=north, CW)."""
    dx = to_x - from_x
    dy = to_y - from_y
    return math.degrees(math.atan2(dx, dy)) % 360


def normalize_angle_diff(angle: float) -> float:
    """Normalizuj różnicę kątów do zakresu [-180, 180]."""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


# ============================================================================
# DECISION MAKER - HIERARCHICZNY SYSTEM DECYZYJNY
# ============================================================================

class DecisionMaker:
    """
    Hierarchiczny system decyzyjny dla czołgu.
    
    Sprawdza reguły od najważniejszych do najmniej ważnych.
    Pierwsza pasująca reguła wygrywa i zwraca decyzję.
    
    Każda metoda zwraca:
    - None jeśli reguła nie pasuje
    - (True, heading_rotation, speed) jeśli reguła pasuje
    """
    
    # =======================================================================
    # REGUŁA 1: BEZPOŚREDNIE ZAGROŻENIE - SZKODLIWY TEREN (PRIORYTET 100)
    # =======================================================================
    
    @staticmethod
    def check_damaging_terrain(
        my_x: float,
        my_y: float,
        sensor_data: Dict[str, Any],
        my_heading: float = 0.0
    ) -> Optional[Tuple[bool, float, float]]:
        """
        ULTRA PROSTA logika omijania WIDZIANYCH szkodliwych terenów.
        
        Jeśli widzisz szkodliwy teren PRZED SOBĄ - skręć od niego.
        Nie próbuj uciekać globalnie, tylko omijaj lokalne zagrożenia.
        
        Args:
            my_x, my_y: Pozycja czołgu
            sensor_data: Dane z sensorów
            my_heading: Obecny kierunek jazdy
            
        Returns:
            None lub (True, heading_rotation, speed)
        """
        seen_terrains = sensor_data.get('seen_terrains', [])
        
        # Znajdź szkodliwe tereny PRZED NAMI (±60°, do 20m)
        dangerous_ahead = []
        
        for terrain in seen_terrains:
            terrain_pos = terrain.get('position', terrain.get('_position', {}))
            if isinstance(terrain_pos, dict):
                tx, ty = terrain_pos.get('x', 0), terrain_pos.get('y', 0)
            else:
                tx, ty = getattr(terrain_pos, 'x', 0), getattr(terrain_pos, 'y', 0)
            
            dist = distance_2d(my_x, my_y, tx, ty)
            
            # Zbyt daleko? Ignoruj
            if dist > 20.0:
                continue
            
            deal_damage = terrain.get('dmg', terrain.get('_deal_damage', 0))
            if isinstance(deal_damage, property):
                deal_damage = terrain.get('deal_damage', 0)
            
            # Szkodliwy?
            if deal_damage > 0:
                # Kąt do terenu
                angle_to_terrain = angle_to_target(my_x, my_y, tx, ty)
                angle_diff = normalize_angle_diff(angle_to_terrain - my_heading)
                
                # Przed nami? (w stożku ±60°)
                if abs(angle_diff) < 60:
                    dangerous_ahead.append((tx, ty, angle_diff, dist, deal_damage))
        
        if not dangerous_ahead:
            return None
        
        # Mamy zagrożenie przed sobą! Skręć od niego
        # Znajdź najbliższe zagrożenie
        closest = min(dangerous_ahead, key=lambda x: x[3])  # x[3] = dist
        _, _, angle_to_closest, dist_to_closest, _ = closest
        
        # Skręć w PRZECIWNĄ stronę
        if angle_to_closest > 0:
            # Zagrożenie po prawej - skręć w lewo
            turn = -35.0
        else:
            # Zagrożenie po lewej - skręć w prawo
            turn = 35.0
        
        # Im bliżej, tym wolniej jedź (lub się zatrzymaj)
        if dist_to_closest < 8:
            speed = 10.0  # Bardzo blisko - wolno
        elif dist_to_closest < 15:
            speed = 20.0  # Średnio blisko
        else:
            speed = 30.0  # Daleko - normalnie
        
        import random
        if random.random() < 0.03:
            print(f"[TERRAIN] Omijam szkodliwy teren {dist_to_closest:.1f}m z {angle_to_closest:.0f}° - skręcam {turn:.0f}°")
        
        return (True, turn, speed)
    
    # =======================================================================
    # REGUŁA 2: KOLIZJA Z PRZESZKODĄ (PRIORYTET 99)
    # =======================================================================
    
    @staticmethod
    def check_imminent_collision(
        my_x: float,
        my_y: float,
        my_heading: float,
        sensor_data: Dict[str, Any]
    ) -> Optional[Tuple[bool, float, float]]:
        """
        Sprawdź czy za chwilę uderzymy w przeszkodę.
        
        Args:
            my_x, my_y: Pozycja czołgu
            my_heading: Obecny kierunek jazdy
            sensor_data: Dane z sensorów
            
        Returns:
            None lub (True, heading_rotation, speed)
        """
        seen_obstacles = sensor_data.get('seen_obstacles', [])
        
        for obstacle in seen_obstacles:
            # Pozycja przeszkody
            obs_pos = obstacle.get('position', obstacle.get('_position', {}))
            if isinstance(obs_pos, dict):
                ox, oy = obs_pos.get('x', 0), obs_pos.get('y', 0)
            else:
                ox, oy = getattr(obs_pos, 'x', 0), getattr(obs_pos, 'y', 0)
            
            # Odległość do przeszkody
            dist = distance_2d(my_x, my_y, ox, oy)
            
            # Kierunek do przeszkody
            angle_to_obs = angle_to_target(my_x, my_y, ox, oy)
            angle_diff = normalize_angle_diff(angle_to_obs - my_heading)
            
            # Jeśli przeszkoda BARDZO blisko (< 10m) i PRZED nami (±45°)
            if dist < 10.0 and abs(angle_diff) < 45:
                # Cofnij się i skręć, żeby wyjść z kolizji
                if angle_diff > 0:
                    turn = -30.0  # Skręć w lewo (od przeszkody)
                else:
                    turn = 30.0   # Skręć w prawo (od przeszkody)
                return (True, turn, -15.0)  # Cofnij się lekko
        
        return None
    
    # =======================================================================
    # REGUŁA 3: POWERUP W POBLIŻU (PRIORYTET 50)
    # =======================================================================
    
    @staticmethod
    def check_nearby_powerup(
        my_x: float,
        my_y: float,
        my_heading: float,
        sensor_data: Dict[str, Any]
    ) -> Optional[Tuple[bool, float, float]]:
        """
        Sprawdź czy jest powerup blisko i nie ma wrogów.
        
        Args:
            my_x, my_y: Pozycja czołgu
            my_heading: Obecny kierunek jazdy
            sensor_data: Dane z sensorów
            
        Returns:
            None lub (True, heading_rotation, speed)
        """
        seen_powerups = sensor_data.get('seen_powerups', [])
        seen_tanks = sensor_data.get('seen_tanks', [])
        
        # Jeśli są wrogowie - nie zbieraj powerupów, walcz!
        if seen_tanks and len(seen_tanks) > 0:
            return None
        
        # Znajdź najbliższy powerup
        closest_powerup = None
        min_dist = 20.0  # Max 20m żeby się opłacało
        
        for powerup in seen_powerups:
            # Pozycja powerupa
            pu_pos = powerup.get('position', powerup.get('_position', {}))
            if isinstance(pu_pos, dict):
                px, py = pu_pos.get('x', 0), pu_pos.get('y', 0)
            else:
                px, py = getattr(pu_pos, 'x', 0), getattr(pu_pos, 'y', 0)
            
            dist = distance_2d(my_x, my_y, px, py)
            
            if dist < min_dist:
                min_dist = dist
                closest_powerup = (px, py)
        
        # Jeśli znaleziono powerup w zasięgu
        if closest_powerup:
            # Jedź w jego stronę
            target_angle = angle_to_target(my_x, my_y, closest_powerup[0], closest_powerup[1])
            angle_diff = normalize_angle_diff(target_angle - my_heading)
            
            # Skręć w stronę powerupa (max ±45°)
            heading_rot = max(-45.0, min(45.0, angle_diff))
            
            # Jedź szybko jeśli jesteś dobrze wycelowany
            if abs(angle_diff) < 30:
                speed = 35.0
            else:
                speed = 20.0
            
            return (True, heading_rot, speed)
        
        return None
