"""
Inteligentny Agent Czołgu - Szkielet
Architektura: TSK-C (tylko walka, bez logiki jazdy)

Uruchomienie:
    python intelligent_agent.py --port 8001 --name "IntelligentBot"
"""

print("="*60)
print("INTELLIGENT AGENT START!")
print("="*60)

import sys
import os
import json
import math
import argparse
from typing import Dict, Any
from fastapi import FastAPI, Body
from pydantic import BaseModel
import uvicorn

# Dodaj ścieżki do importu
current_dir = os.path.dirname(__file__)
sys.path.insert(0, current_dir)

parent_dir = os.path.join(os.path.dirname(current_dir), '02_FRAKCJA_SILNIKA')
sys.path.insert(0, parent_dir)

# Import modułów agenta - tylko combat
from agent_logic.tsk_combat import TSKCombatController

# Import API struktur (opcjonalnie)
try:
    from backend.structures.ammo import AmmoType
    from backend.structures.position import Position
except ImportError:
    print("[WARNING] Could not import backend structures, using dicts")


class ActionCommand(BaseModel):
    """Output action from agent to engine."""
    barrel_rotation_angle: float = 0.0
    heading_rotation_angle: float = 0.0
    move_speed: float = 0.0
    ammo_to_load: str = None
    should_fire: bool = False


class IntelligentAgent:
    """Agent - szkielet z komunikacją API i TSK-C (combat)."""
    
    def __init__(self, name: str = "IntelligentBot", config_path: str = None):
        self.name = name
        self.is_destroyed = False
        
        # Wczytaj konfigurację
        self.config = self._load_config(config_path)
        
        # Inicjalizacja tylko combat controller
        tsk_c_params = self.config.get('tsk_c', None)
        self.tsk_combat = TSKCombatController(params=tsk_c_params)
        
        print(f"[{self.name}] Intelligent Agent initialized")
        print(f"[{self.name}] Config loaded: TSK-C={tsk_c_params is not None}")
    
    def _load_config(self, config_path: str = None) -> Dict:
        """Wczytuje konfigurację z pliku JSON."""
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        
        # Spróbuj wczytać domyślną konfigurację TSK-C
        config = {}
        
        tsk_c_path = os.path.join(current_dir, 'config', 'tsk_c_params.json')
        if os.path.exists(tsk_c_path):
            with open(tsk_c_path, 'r') as f:
                data = json.load(f)
                config['tsk_c'] = {k: v for k, v in data.items() if k != 'description'}
        
        return config
    
    def get_action(
        self, 
        current_tick: int, 
        my_tank_status: Dict[str, Any], 
        sensor_data: Dict[str, Any], 
        enemies_remaining: int
    ) -> ActionCommand:
        """Główna pętla decyzyjna agenta - szkielet bez logiki jazdy."""
        
        # DEBUG
        if current_tick == 0:
            print(f"[{self.name}] Pierwsza akcja!")
            print(f"[{self.name}] Position: {my_tank_status.get('position')}")
        
        # =================================================================
        # RUCH - PLACEHOLDER (czołg stoi w miejscu)
        # =================================================================
        heading_rotation = 0.0
        move_speed = 0.0
        
        # Tutaj będzie implementowana logika jazdy
        # TODO: Dodaj tutaj nową logikę nawigacji
        
        # =================================================================
        # WALKA - TSK-C (Combat Controller)
        # =================================================================
        combat_output = {
            'barrel_rotation': 0.0, 
            'ammo_type': 'LIGHT', 
            'should_fire': False
        }
        
        seen_tanks = sensor_data.get('seen_tanks', [])
        
        if seen_tanks:
            # Wybierz najbliższego wroga
            closest_enemy = min(seen_tanks, key=lambda e: e.get('distance', float('inf')))
            
            # Oblicz błąd kąta między lufą a wrogiem
            enemy_pos = closest_enemy.get('position', {'x': 250, 'y': 250})
            my_pos = my_tank_status.get('position', {'x': 250, 'y': 250})
            dx = enemy_pos.get('x', 250) - my_pos.get('x', 250)
            dy = enemy_pos.get('y', 250) - my_pos.get('y', 250)
            
            target_barrel_angle = math.degrees(math.atan2(dx, dy)) % 360
            angle_error = target_barrel_angle - my_tank_status.get('barrel_angle', 0)
            
            # Normalizacja angle_error do zakresu [-180, 180]
            while angle_error > 180:
                angle_error -= 360
            while angle_error < -180:
                angle_error += 360
            
            # Wywołaj TSK-C
            combat_output = self.tsk_combat.compute(
                distance=closest_enemy.get('distance', 50),
                angle_error=angle_error,
                enemy_hp_ratio=0.5,  # TODO: Szacuj HP wroga jeśli dostępne
                reload_status=my_tank_status.get('_reload_timer', 0),
                my_barrel_spin_rate=my_tank_status.get('_barrel_spin_rate', 90.0)
            )
            
            # DEBUG walki co sekundę
            if current_tick % 60 == 0:
                print(f"[{self.name}] COMBAT: enemy_dist={closest_enemy.get('distance', 0):.1f}, "
                      f"angle_err={abs(angle_error):.1f}°, fire={combat_output['should_fire']}")
        
        # =================================================================
        # GENEROWANIE AKCJI
        # =================================================================
        if current_tick % 60 == 0:
            print(f"[{self.name}] Tick {current_tick}: Enemies={enemies_remaining}, "
                  f"Speed={move_speed:.1f}, Heading_rot={heading_rotation:.1f}")
        
        return ActionCommand(
            barrel_rotation_angle=combat_output['barrel_rotation'],
            heading_rotation_angle=heading_rotation,
            move_speed=move_speed,
            ammo_to_load=combat_output['ammo_type'],
            should_fire=combat_output['should_fire']
        )
    
    def destroy(self):
        """Wywoływane gdy czołg zostaje zniszczony."""
        self.is_destroyed = True
        print(f"[{self.name}] Tank destroyed!")
    
    def end(self, damage_dealt: float, tanks_killed: int):
        """Wywoływane na koniec gry."""
        print(f"[{self.name}] Game ended!")
        print(f"[{self.name}] Damage dealt: {damage_dealt}")
        print(f"[{self.name}] Tanks killed: {tanks_killed}")


# ============================================================================
# FastAPI Server
# ============================================================================

app = FastAPI(title="Intelligent Tank Agent", version="1.0.0")
agent = None  # Zostanie zainicjalizowany w main


@app.get("/")
async def root():
    return {
        "message": f"Agent {agent.name} is running", 
        "destroyed": agent.is_destroyed,
        "architecture": "Skeleton - API Communication + TSK-C (Combat only)"
    }


@app.post("/agent/action", response_model=ActionCommand)
async def get_action(payload: Dict[str, Any] = Body(...)):
    """Główny endpoint - zwraca akcję agenta."""
    try:
        action = agent.get_action(
            current_tick=payload.get('current_tick', 0),
            my_tank_status=payload.get('my_tank_status', {}),
            sensor_data=payload.get('sensor_data', {}),
            enemies_remaining=payload.get('enemies_remaining', 0)
        )
        return action
    except Exception as e:
        print(f"[API ERROR] CRASH w get_action: {e}")
        import traceback
        traceback.print_exc()
        # Zwróć bezpieczną akcję (czołg stoi w miejscu)
        return ActionCommand()


@app.post("/agent/destroy", status_code=204)
async def destroy():
    """Endpoint wywoływany gdy czołg zostaje zniszczony."""
    agent.destroy()


@app.post("/agent/end", status_code=204)
async def end(payload: Dict[str, Any] = Body(...)):
    """Endpoint wywoływany na koniec gry."""
    agent.end(
        damage_dealt=payload.get('damage_dealt', 0.0),
        tanks_killed=payload.get('tanks_killed', 0)
    )


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inteligentny Agent Czołgu - Szkielet")
    parser.add_argument("--port", type=int, default=8001, help="Port serwera")
    parser.add_argument("--name", type=str, default="IntelligentBot", help="Nazwa agenta")
    parser.add_argument("--config", type=str, default=None, help="Ścieżka do pliku konfiguracyjnego")
    args = parser.parse_args()
    
    # Inicjalizuj agenta
    agent = IntelligentAgent(name=args.name, config_path=args.config)
    
    print(f"\n{'='*70}")
    print(f"Starting {agent.name} on port {args.port}")
    print(f"Architecture: Skeleton - API Communication + TSK-C (Combat only)")
    print(f"Movement logic: PLACEHOLDER (tank stands still)")
    print(f"{'='*70}\n")
    
    uvicorn.run(app, host="0.0.0.0", port=args.port)
