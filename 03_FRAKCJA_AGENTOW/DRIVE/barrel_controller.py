"""
BARREL CONTROLLER - Sterownik lufy z ciągłym skanowaniem 360°
==============================================================

Ten moduł kontroluje obrót lufy czołgu:
- Tryb SCAN: Ciągłe skanowanie 360° jak wiatrak (gdy nie ma wroga)
- Tryb TRACK: Śledzenie wykrytego wroga
- Tryb AIM: Precyzyjne celowanie przed strzałem
- Tryb FIRE: Oddanie strzału

To rozwiązuje problem widzenia - lufa kręci się ciągle, więc czołg widzi wszystko dookoła.
"""

import math
from typing import Dict, Any, Optional, Tuple
from enum import Enum


class BarrelMode(Enum):
    """Tryby pracy lufy."""
    SCAN = "scan"      # Skanowanie 360° w kółko
    TRACK = "track"    # Śledzenie wroga
    AIM = "aim"        # Celowanie przed strzałem
    FIRE = "fire"      # Strzelanie


def normalize_angle_diff(angle: float) -> float:
    """Normalizuj różnicę kątów do zakresu [-180, 180]."""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def calculate_angle_to_target(from_x: float, from_y: float, to_x: float, to_y: float, my_heading: float) -> float:
    """
    Oblicz kąt WZGLĘDEM KADŁUBA do celu.
    
    Args:
        from_x, from_y: Pozycja czołgu
        to_x, to_y: Pozycja celu
        my_heading: Kierunek kadłuba (0=N, 90=E)
        
    Returns:
        Kąt względem kadłuba (0 = do przodu, + = prawo, - = lewo)
    """
    dx = to_x - from_x
    dy = to_y - from_y
    # Kąt absolutny do celu (0=E, 90=N w standardowym układzie matematycznym)
    angle_to_target = math.degrees(math.atan2(dy, dx))
    
    # Konwersja do układu gry (0=N, 90=E)
    # W grze: 0° = north, rośnie clockwise
    # W math: 0° = east, rośnie counter-clockwise
    game_angle = 90 - angle_to_target  # Konwersja
    
    # Względem kadłuba
    relative_angle = normalize_angle_diff(game_angle - my_heading)
    return relative_angle


class BarrelController:
    """
    Inteligentny sterownik lufy z ciągłym skanowaniem 360°.
    
    Strategia:
    - Jeśli nie ma wroga -> SCAN (kręć się w kółko)
    - Jeśli wykryto wroga -> TRACK (obróć lufę w jego stronę)
    - Jeśli wycelowano -> AIM (zatrzymaj się i precyzyjnie celuj)
    - Jeśli gotowy -> FIRE (strzel!)
    """
    
    def __init__(
        self, 
        scan_speed: float = 20.0,      # Prędkość skanowania [°/tick]
        track_speed: float = 30.0,     # Prędkość śledzenia wroga [°/tick]
        aim_threshold: float = 5.0,    # Dokładność celowania [°]
        aim_ticks: int = 2,            # Ile ticków celować przed strzałem
        fire_cooldown: int = 10        # Cooldown między strzałami [ticks]
    ):
        self.scan_speed = scan_speed
        self.track_speed = track_speed
        self.aim_threshold = aim_threshold
        self.aim_ticks = aim_ticks
        self.fire_cooldown = fire_cooldown
        
        # Stan
        self.mode = BarrelMode.SCAN
        self.aim_timer = 0
        self.cooldown_timer = 0
        self.target_id = None
        self.target_last_angle = 0.0
        
        print(f"[BarrelController] Inicjalizacja - Skan: {scan_speed}°/tick, Śledzenie: {track_speed}°/tick")
    
    def update(
        self,
        my_x: float,
        my_y: float,
        my_heading: float,
        current_barrel_angle: float,
        seen_tanks: list,
        max_barrel_rotation: float = 45.0
    ) -> Tuple[float, bool]:
        """
        Aktualizuj sterownik lufy.
        
        Args:
            my_x, my_y: Pozycja mojego czołgu
            my_heading: Kierunek kadłuba [°]
            current_barrel_angle: Obecny kąt lufy względem kadłuba [°]
            seen_tanks: Lista widzianych wrogów
            max_barrel_rotation: Max obrót lufy w jednym ticku [°]
            
        Returns:
            (barrel_rotation_command, should_fire)
        """
        # Cooldown po strzale
        if self.cooldown_timer > 0:
            self.cooldown_timer -= 1
        
        # Znajdź najbliższego wroga
        closest_enemy = self._find_closest_enemy(my_x, my_y, seen_tanks)
        
        # Maszyna stanów
        barrel_rotation = 0.0
        should_fire = False
        
        if closest_enemy is None:
            # BRAK WROGA -> SKANUJ 360°
            self.mode = BarrelMode.SCAN
            self.target_id = None
            self.aim_timer = 0
            
            # Kręć się w kółko jak wiatrak
            barrel_rotation = self.scan_speed
            
        else:
            # WYKRYTO WROGA!
            enemy_pos = closest_enemy.get('position', {})
            enemy_x = enemy_pos.get('x', 0)
            enemy_y = enemy_pos.get('y', 0)
            
            # Oblicz kąt do wroga WZGLĘDEM KADŁUBA
            angle_to_enemy = calculate_angle_to_target(my_x, my_y, enemy_x, enemy_y, my_heading)
            
            # Błąd celowania = różnica między kątem lufy a kątem do wroga
            aiming_error = normalize_angle_diff(angle_to_enemy - current_barrel_angle)
            
            # Czy jesteśmy wycelowani?
            is_aimed = abs(aiming_error) < self.aim_threshold
            
            if not is_aimed:
                # TRYB TRACK: Obracaj lufę w stronę wroga
                self.mode = BarrelMode.TRACK
                self.aim_timer = 0
                
                # Obróć w stronę wroga z prędkością track_speed
                rotation_needed = aiming_error
                barrel_rotation = max(-self.track_speed, min(self.track_speed, rotation_needed))
                
            else:
                # WYCELOWANO! -> TRYB AIM
                if self.aim_timer < self.aim_ticks:
                    self.mode = BarrelMode.AIM
                    self.aim_timer += 1
                    barrel_rotation = 0.0  # Zatrzymaj lufę
                else:
                    # GOTOWY DO STRZAŁU! -> TRYB FIRE
                    if self.cooldown_timer == 0:
                        self.mode = BarrelMode.FIRE
                        should_fire = True
                        self.cooldown_timer = self.fire_cooldown
                        self.aim_timer = 0
                    else:
                        # W cooldownie, kontynuuj śledzenie
                        self.mode = BarrelMode.TRACK
                        rotation_needed = aiming_error
                        barrel_rotation = max(-self.track_speed, min(self.track_speed, rotation_needed))
        
        # Ogranicz do max_barrel_rotation
        barrel_rotation = max(-max_barrel_rotation, min(max_barrel_rotation, barrel_rotation))
        
        return barrel_rotation, should_fire
    
    def _find_closest_enemy(self, my_x: float, my_y: float, seen_tanks: list) -> Optional[Dict[str, Any]]:
        """Znajdź najbliższego widocznego wroga."""
        if not seen_tanks:
            return None
        
        closest = None
        min_distance = float('inf')
        
        for tank in seen_tanks:
            pos = tank.get('position', {})
            tx = pos.get('x', 0)
            ty = pos.get('y', 0)
            
            dist = math.sqrt((tx - my_x)**2 + (ty - my_y)**2)
            
            if dist < min_distance:
                min_distance = dist
                closest = tank
        
        return closest
    
    def get_status(self) -> str:
        """Zwróć aktualny status dla debugowania."""
        status = f"Mode: {self.mode.value}"
        if self.mode == BarrelMode.AIM:
            status += f" ({self.aim_timer}/{self.aim_ticks})"
        if self.cooldown_timer > 0:
            status += f" [Cooldown: {self.cooldown_timer}]"
        return status
