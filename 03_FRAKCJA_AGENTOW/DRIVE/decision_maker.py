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
        Sprawdź czy jesteśmy na szkodliwym terenie i znajdź bezpieczne wyjście.
        
        Strategia: Szukaj BEZPIECZNEGO terenu (0 DMG) i jedź tam, nawet jeśli
        trzeba przejść przez mniej szkodliwy teren (np. dziury).
        
        Args:
            my_x, my_y: Pozycja czołgu
            sensor_data: Dane z sensorów
            my_heading: Obecny kierunek jazdy
            
        Returns:
            None lub (True, heading_rotation, speed)
        """
        seen_terrains = sensor_data.get('seen_terrains', [])
        
        # Sklasyfikuj tereny na: szkodliwe (blisko nas) i bezpieczne
        nearby_damaging = []  # Szkodliwe tereny w radius < 8m
        safe_terrains = []     # Bezpieczne tereny w radius < 40m
        
        for terrain in seen_terrains:
            # Pozycja terenu
            terrain_pos = terrain.get('position', terrain.get('_position', {}))
            if isinstance(terrain_pos, dict):
                tx, ty = terrain_pos.get('x', 0), terrain_pos.get('y', 0)
            else:
                tx, ty = getattr(terrain_pos, 'x', 0), getattr(terrain_pos, 'y', 0)
            
            # Odległość do terenu
            dist = distance_2d(my_x, my_y, tx, ty)
            
            # Czy teren zadaje obrażenia?
            deal_damage = terrain.get('dmg', terrain.get('_deal_damage', 0))
            if isinstance(deal_damage, property):
                deal_damage = terrain.get('deal_damage', 0)
            
            # Klasyfikuj
            if deal_damage > 0 and dist < 8.0:
                angle = angle_to_target(my_x, my_y, tx, ty)
                nearby_damaging.append((tx, ty, angle, dist, deal_damage))
            elif deal_damage == 0 and dist < 40.0:
                angle = angle_to_target(my_x, my_y, tx, ty)
                safe_terrains.append((tx, ty, angle, dist))
        
        # Jeśli nie ma szkodliwego terenu w pobliżu, OK
        if not nearby_damaging:
            return None
        
        # NAJWAŻNIEJSZE: Znajdź najbliższy bezpieczny teren
        target_angle = None
        
        if safe_terrains:
            # Mamy widoczny bezpieczny teren! Idź tam!
            closest_safe = min(safe_terrains, key=lambda x: x[3])  # x[3] = dist
            target_angle = closest_safe[2]  # x[2] = angle
        else:
            # Nie widać bezpiecznego terenu - uciekaj od najbardziej szkodliwych
            # Sprawdź 8 kierunków i wybierz najlepszy
            best_escape_angle = None
            best_score = -999999
            
            for check_angle in range(0, 360, 45):
                score = 0
                for tx, ty, danger_angle, danger_dist, damage in nearby_damaging:
                    # Jak bardzo ten kierunek prowadzi OD niebezpieczeństwa?
                    angle_diff = normalize_angle_diff(check_angle - danger_angle)
                    # cos(0°)=-1 (towards), cos(180°)=+1 (away)
                    direction_score = math.cos(math.radians(angle_diff))
                    
                    # Waga: bliższe i bardziej szkodliwe = ważniejsze
                    weight = damage / (danger_dist + 0.1)
                    score += direction_score * weight
                
                if score > best_score:
                    best_score = score
                    best_escape_angle = check_angle
            
            target_angle = best_escape_angle
        
        # Oblicz jak bardzo musimy się obrócić do celu
        if target_angle is not None:
            angle_diff = normalize_angle_diff(target_angle - my_heading)
            
            # Jeśli musimy się mocno obrócić (> 90°), cofaj się podczas obrotu
            if abs(angle_diff) > 90:
                heading_rot = 45.0 if angle_diff > 0 else -45.0
                return (True, heading_rot, -15.0)
            else:
                # Obróć się i jedź SZYBKO do bezpieczeństwa!
                heading_rot = max(-45.0, min(45.0, angle_diff))
                # Im lepiej wycelowany, tym szybciej jedź
                speed = 35.0 if abs(angle_diff) < 30 else 25.0
                return (True, heading_rot, speed)
        
        # Fallback - nie powinno się zdarzyć
        return (True, 0.0, -30.0)
    
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
