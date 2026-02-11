"""
Inteligentny Agent Czołgu
Architektura: HM + FSM + TSK-C + A* + TSK-D

Uruchomienie:
    python intelligent_agent.py --port 8001 --name "IntelligentBot"
"""

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

# Import modułów agenta
from agent_logic.heat_map import HeatMap
from agent_logic.fsm import FSM, AgentState
from agent_logic.pathfinder import AStarPathfinder
from agent_logic.tsk_combat import TSKCombatController
from agent_logic.tsk_drive import TSKDriveController

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
    """Agent z architekturą HM + FSM + TSK + A*."""
    
    def __init__(self, name: str = "IntelligentBot", config_path: str = None):
        self.name = name
        self.is_destroyed = False
        
        # Wczytaj konfigurację
        self.config = self._load_config(config_path)
        
        # Inicjalizacja modułów
        self.heat_map = HeatMap()
        self.fsm = FSM()
        self.pathfinder = AStarPathfinder(self.heat_map)
        
        tsk_c_params = self.config.get('tsk_c', None)
        tsk_d_params = self.config.get('tsk_d', None)
        
        self.tsk_combat = TSKCombatController(params=tsk_c_params)
        self.tsk_drive = TSKDriveController(params=tsk_d_params)
        
        # Stan nawigacji
        self.current_path = None
        self.current_waypoint = (250.0, 250.0)  # Domyślnie jedź do środka mapy
        self.waypoint_index = 0
        self.path_recalc_timer = 0
        
        print(f"[{self.name}] Intelligent Agent initialized")
        print(f"[{self.name}] Config loaded: TSK-C={tsk_c_params is not None}, TSK-D={tsk_d_params is not None}")
    
    def _load_config(self, config_path: str = None) -> Dict:
        """Wczytuje konfigurację z pliku JSON."""
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        
        # Spróbuj wczytać domyślne konfiguracje
        config = {}
        
        tsk_c_path = os.path.join(current_dir, 'config', 'tsk_c_params.json')
        if os.path.exists(tsk_c_path):
            with open(tsk_c_path, 'r') as f:
                data = json.load(f)
                config['tsk_c'] = {k: v for k, v in data.items() if k != 'description'}
        
        tsk_d_path = os.path.join(current_dir, 'config', 'tsk_d_params.json')
        if os.path.exists(tsk_d_path):
            with open(tsk_d_path, 'r') as f:
                data = json.load(f)
                config['tsk_d'] = {k: v for k, v in data.items() if k != 'description'}
        
        return config
    
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
        
        # --- 3.5: Jeśli brak celu (EXPLORE), losuj punkt na mapie ---
        if target_position is None:
            # Losowy punkt w obszarze mapy (zakładam 500x500)
            import random
            target_position = (
                random.uniform(50, 450),
                random.uniform(50, 450)
            )
        
        # --- 4. A* - Wyznaczenie ścieżki ---
        self.path_recalc_timer += 1
        
        if target_position:
            current_pos = (my_tank_status['position']['x'], my_tank_status['position']['y'])
            
            # Przelicz ścieżkę co 30 ticków lub po osiągnięciu waypointa
            should_recalc = (
                self.current_path is None or 
                self.waypoint_index >= len(self.current_path) or
                self.path_recalc_timer >= 30
            )
            
            if should_recalc:
                self.current_path = self.pathfinder.find_path(current_pos, target_position)
                self.waypoint_index = 0
                self.path_recalc_timer = 0
            
            # Wybierz bieżący waypoint
            if self.current_path and self.waypoint_index < len(self.current_path):
                self.current_waypoint = self.current_path[self.waypoint_index]
                
                # Sprawdź czy osiągnięto waypoint (próg 5 jednostek)
                wp_dist = math.sqrt(
                    (current_pos[0] - self.current_waypoint[0])**2 + 
                    (current_pos[1] - self.current_waypoint[1])**2
                )
                if wp_dist < 5.0:
                    self.waypoint_index += 1
            elif not self.current_path:
                # Jeśli pathfinder zawiódł, jedź bezpośrednio do celu
                self.current_waypoint = target_position
        
        # --- 5. TSK-D - Sterowanie ruchem ---
        drive_output = self.tsk_drive.compute(
            waypoint=self.current_waypoint,
            my_position=my_tank_status['position'],
            my_heading=my_tank_status['heading'],
            my_heading_spin_rate=my_tank_status['_heading_spin_rate'],
            my_top_speed=my_tank_status['_top_speed'],
            terrain_modifier=1.0  # TODO: Pobierz z terenu pod czołgiem
        )
        
        # --- 6. TSK-C - Sterowanie walką ---
        combat_output = {'barrel_rotation': 0.0, 'ammo_type': 'LIGHT', 'should_fire': False}
        
        if sensor_data.get('seen_tanks', []):
            # Wybierz najbliższego wroga
            enemies = sensor_data['seen_tanks']
            closest_enemy = min(enemies, key=lambda e: e.get('distance', float('inf')))
            
            # Oblicz błąd kąta między lufą a wrogiem
            dx = closest_enemy['position']['x'] - my_tank_status['position']['x']
            dy = closest_enemy['position']['y'] - my_tank_status['position']['y']
            
            target_barrel_angle = math.degrees(math.atan2(dx, dy)) % 360
            angle_error = target_barrel_angle - my_tank_status['barrel_angle']
            
            # Normalizacja angle_error
            while angle_error > 180:
                angle_error -= 360
            while angle_error < -180:
                angle_error += 360
            
            combat_output = self.tsk_combat.compute(
                distance=closest_enemy.get('distance', 50),
                angle_error=angle_error,
                enemy_hp_ratio=0.5,  # TODO: Szacuj HP wroga jeśli dostępne
                reload_status=my_tank_status.get('current_reload_progress', 0),
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
        "architecture": "HM + FSM + TSK-C + A* + TSK-D"
    }


@app.post("/agent/action", response_model=ActionCommand)
async def get_action(payload: Dict[str, Any] = Body(...)):
    """Główny endpoint - zwraca akcję agenta."""
    action = agent.get_action(
        current_tick=payload.get('current_tick', 0),
        my_tank_status=payload.get('my_tank_status', {}),
        sensor_data=payload.get('sensor_data', {}),
        enemies_remaining=payload.get('enemies_remaining', 0)
    )
    return action


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
    parser = argparse.ArgumentParser(description="Inteligentny Agent Czołgu")
    parser.add_argument("--port", type=int, default=8001, help="Port serwera")
    parser.add_argument("--name", type=str, default="IntelligentBot", help="Nazwa agenta")
    parser.add_argument("--config", type=str, default=None, help="Ścieżka do pliku konfiguracyjnego")
    args = parser.parse_args()
    
    # Inicjalizuj agenta
    agent = IntelligentAgent(name=args.name, config_path=args.config)
    
    print(f"\n{'='*70}")
    print(f"Starting {agent.name} on port {args.port}")
    print(f"Architecture: HM + FSM + TSK-C + A* + TSK-D")
    print(f"{'='*70}\n")
    
    uvicorn.run(app, host="0.0.0.0", port=args.port)
