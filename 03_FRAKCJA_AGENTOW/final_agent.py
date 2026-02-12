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

# Import fuzzy controller
from fuzzy_controller import FuzzyMotionController


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


# ============================================================================
# FUZZY LOGIC AGENT
# ============================================================================

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

        # Fuzzy controller dla ruchu
        self.motion_controller = FuzzyMotionController()

        # State for barrel scanning
        self.barrel_scan_direction = 1.0  # 1.0 for right, -1.0 for left
        self.barrel_rotation_speed = 15.0

        # State for aiming before shooting
        self.aim_timer = 0  # Ticks to wait before firing
        
        print(f"[{self.name}] ✓ Agent gotowy!")
    
    def get_action(
        self, 
        current_tick: int, 
        my_tank_status: Dict[str, Any], 
        sensor_data: Dict[str, Any], 
        enemies_remaining: int
    ) -> ActionCommand:
        """Główna metoda - podejmij decyzję na podstawie fuzzy logic."""
        should_fire = False
        barrel_rotation = 0.0
        
        # ===================================================================
        # WYCIĄGNIJ DANE O CZOŁGU
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
        my_hp = my_tank_status.get('hp', 100)
        max_hp = my_tank_status.get('_max_hp', 100)
        barrel_angle = my_tank_status.get('barrel_angle', 0.0)
        
        # ===================================================================
        # FUZZY LOGIC MOTION CONTROL
        # ===================================================================
        
        heading_rotation, move_speed = self.motion_controller.compute_motion(
            my_position=my_position,
            my_heading=my_heading,
            my_hp=my_hp,
            max_hp=max_hp,
            sensor_data=sensor_data
        )
        
        # ===================================================================
        # BARREL SCANNING (skanuj celem w poszukiwaniu wroga)
        # ===================================================================
        
        if self.aim_timer > 0:
            # Celujemy - nie ruszaj lufą
            self.aim_timer -= 1
            barrel_rotation = 0.0
            
            # Strzel na końcu celowania
            if self.aim_timer == 0:
                should_fire = True
        else:
            # Skanuj lufą w lewo-prawo
            if barrel_angle > 45.0:
                self.barrel_scan_direction = -1.0  # Scan left
            elif barrel_angle < -45.0:
                self.barrel_scan_direction = 1.0  # Scan right
            barrel_rotation = self.barrel_rotation_speed * self.barrel_scan_direction
            
            # Jeśli widzimy wroga - zacznij celować
            seen_tanks = sensor_data.get('seen_tanks', [])
            if seen_tanks and len(seen_tanks) > 0:
                # Wróg w zasięgu - przygotuj się do strzału
                if random.random() < 0.2:  # 20% szansy na rozpoczęcie celowania
                    self.aim_timer = 5  # Celuj przez 5 ticków
        
        return ActionCommand(
            barrel_rotation_angle=barrel_rotation,
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
    uvicorn.run(app, host=args.host, port=args.port)
