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

import random
import argparse
import sys
import os

# Add paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
controller_dir = os.path.join(os.path.dirname(current_dir), '02_FRAKCJA_SILNIKA', 'controller')
sys.path.insert(0, controller_dir)

parent_dir = os.path.join(os.path.dirname(current_dir), '02_FRAKCJA_SILNIKA')
sys.path.insert(0, parent_dir)

from typing import Dict, Any
from fastapi import FastAPI, Body
from pydantic import BaseModel
import uvicorn
import random

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
        
        print(f"[{self.name}] ✓ Agent gotowy - prosta i skuteczna logika!")
    
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
        
        # ===================================================================
        # DETEKCJA SZKODLIWEGO TERENU - Po stracie HP
        # ===================================================================
        # NAJPROSTSZE: Jeśli tracimy HP bez wroga = zawróć i uciekaj!
        is_escaping_damage = False
        
        if self.last_hp is not None:
            hp_lost = self.last_hp - my_hp
            if hp_lost > 0.5:  # Tracisz co najmniej 0.5 HP
                # Tracimy HP!
                if len(filtered_sensor_data.get('seen_tanks', [])) == 0:
                    # Brak wrogów - teren nas zabija!
                    self.damage_taken_recently = 60  # Pamiętaj przez sekundę
                    
                    # Wybierz kierunek ucieczki TYLKO RAZ gdy wykrywasz szkodę
                    if self.escape_direction is None:
                        # Zawróć: obróć się o 120-180° (losowo żeby nie zawracać w to samo miejsce)
                        import random
                        turn_amount = random.choice([120, 135, 150, 165, 180, -120, -135, -150, -165, -180])
                        self.escape_direction = (my_heading + turn_amount) % 360
                        print(f"[{self.name}] 🚨 SZKODLIWY TEREN! HP {my_hp:.1f} (strata {hp_lost:.1f}) - Zawracam o {turn_amount}°!")
        
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
                    decision_source = "collision_avoidance"

            # --- PRIORYTET 3: POWERUP W POBLIŻU ---
            if not result:
                result = self.decision_maker.check_nearby_powerup(
                    my_x, my_y, my_heading, filtered_sensor_data
                )
                if result:
                    _, heading_rotation, move_speed = result
                    decision_source = "powerup_collection"

            # --- PRIORYTET 4: FUZZY LOGIC (WALKA/EKSPLORACJA) ---
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
