"""
Utilities - Funkcje pomocnicze dla agenta
"""

import numpy as np
from typing import Tuple, Any


def calculate_angle_to_target(from_x: float, from_y: float, to_x: float, to_y: float) -> float:
    """
    Oblicza kąt od pozycji źródłowej do docelowej.
    
    Args:
        from_x, from_y: Pozycja źródłowa
        to_x, to_y: Pozycja docelowa
    
    Returns:
        Kąt w stopniach (0-360, 0=góra, CW)
    """
    dx = to_x - from_x
    dy = to_y - from_y
    angle = np.degrees(np.arctan2(dx, dy)) % 360
    return angle


def normalize_angle_error(angle_error: float) -> float:
    """
    Normalizuje błąd kąta do zakresu (-180, 180].
    
    Args:
        angle_error: Różnica kątów
    
    Returns:
        Znormalizowana różnica (-180, 180]
    """
    while angle_error > 180:
        angle_error -= 360
    while angle_error <= -180:
        angle_error += 360
    return angle_error


def calculate_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Oblicza odległość euklidesową między dwoma punktami."""
    return np.sqrt((x2 - x1)**2 + (y2 - y1)**2)


def extract_position_tuple(obj: Any) -> Tuple[float, float]:
    """
    Wydobywa współrzędne (x, y) z różnych typów obiektów.
    
    Args:
        obj: Obiekt z pozycją (może być obiektem, dictem, lub tuple)
    
    Returns:
        Krotka (x, y)
    """
    if isinstance(obj, tuple) and len(obj) == 2:
        return obj
    elif hasattr(obj, 'x') and hasattr(obj, 'y'):
        return (obj.x, obj.y)
    elif hasattr(obj, 'position'):
        pos = obj.position
        if hasattr(pos, 'x') and hasattr(pos, 'y'):
            return (pos.x, pos.y)
        elif isinstance(pos, dict):
            return (pos['x'], pos['y'])
    elif isinstance(obj, dict):
        if 'position' in obj:
            pos = obj['position']
            return (pos['x'], pos['y'])
        elif 'x' in obj and 'y' in obj:
            return (obj['x'], obj['y'])
    
    raise ValueError(f"Cannot extract position from object: {type(obj)}")


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Ogranicza wartość do zakresu [min_val, max_val]."""
    return max(min_val, min(value, max_val))
