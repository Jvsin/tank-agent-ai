"""
Przykładowy skrypt do szybkiego testowania modułów agenta
"""

import sys
import os

# Dodaj ścieżki
current_dir = os.path.dirname(__file__)
sys.path.insert(0, current_dir)

from agent_logic.heat_map import HeatMap
from agent_logic.fsm import FSM, AgentState
from agent_logic.pathfinder import AStarPathfinder
from agent_logic.tsk_combat import TSKCombatController
from agent_logic.tsk_drive import TSKDriveController


def test_heat_map():
    print("\n=== TEST: Heat Map ===")
    hm = HeatMap()
    
    # Symuluj sensor data
    sensor_data = {
        'seen_tanks': [
            {'position': {'x': 100, 'y': 100}, 'distance': 50}
        ],
        'seen_powerups': [
            {'position': {'x': 200, 'y': 200}}
        ],
        'seen_obstacles': [],
        'seen_terrains': []
    }
    
    my_pos = {'x': 50, 'y': 50}
    
    hm.update(sensor_data, my_pos)
    
    hottest = hm.get_hottest_enemy_position()
    closest_powerup = hm.get_closest_powerup_position(my_pos)
    
    print(f"Hottest enemy: {hottest}")
    print(f"Closest powerup: {closest_powerup}")
    print("✅ Heat Map działa!")


def test_fsm():
    print("\n=== TEST: FSM ===")
    fsm = FSM()
    hm = HeatMap()
    
    # Symuluj dane czołgu
    my_tank = {
        'hp': 50,
        '_max_hp': 100,
        'ammo': {
            'LIGHT': {'count': 5},
            'HEAVY': {'count': 2}
        },
        'position': {'x': 50, 'y': 50}
    }
    
    sensor_data = {
        'seen_tanks': [
            {'position': {'x': 100, 'y': 100}, 'distance': 10}
        ],
        'seen_powerups': [],
        'seen_obstacles': [],
        'seen_terrains': []
    }
    
    state = fsm.update(my_tank, sensor_data, hm)
    print(f"FSM State: {state}")
    
    target = fsm.get_target_position(my_tank, sensor_data, hm)
    print(f"Target position: {target}")
    print("✅ FSM działa!")


def test_pathfinder():
    print("\n=== TEST: A* Pathfinder ===")
    hm = HeatMap()
    pf = AStarPathfinder(hm)
    
    start = (50, 50)
    goal = (200, 200)
    
    path = pf.find_path(start, goal)
    
    if path:
        print(f"Znaleziono ścieżkę: {len(path)} waypoints")
        print(f"Start: {path[0]}")
        print(f"Goal: {path[-1]}")
        print("✅ Pathfinder działa!")
    else:
        print("❌ Nie znaleziono ścieżki")


def test_tsk_combat():
    print("\n=== TEST: TSK-C ===")
    tsk_c = TSKCombatController()
    
    result = tsk_c.compute(
        distance=12.0,
        angle_error=15.0,
        enemy_hp_ratio=0.7,
        reload_status=0,
        my_barrel_spin_rate=30.0
    )
    
    print(f"Barrel rotation: {result['barrel_rotation']:.2f}")
    print(f"Ammo type: {result['ammo_type']}")
    print(f"Should fire: {result['should_fire']}")
    print("✅ TSK-C działa!")


def test_tsk_drive():
    print("\n=== TEST: TSK-D ===")
    tsk_d = TSKDriveController()
    
    waypoint = (200, 200)
    my_pos = {'x': 50, 'y': 50}
    
    result = tsk_d.compute(
        waypoint=waypoint,
        my_position=my_pos,
        my_heading=45.0,
        my_heading_spin_rate=20.0,
        my_top_speed=10.0,
        terrain_modifier=1.0
    )
    
    print(f"Heading rotation: {result['heading_rotation']:.2f}")
    print(f"Move speed: {result['move_speed']:.2f}")
    print("✅ TSK-D działa!")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TESTY MODUŁÓW AGENTA")
    print("="*70)
    
    try:
        test_heat_map()
        test_fsm()
        test_pathfinder()
        test_tsk_combat()
        test_tsk_drive()
        
        print("\n" + "="*70)
        print("✅ WSZYSTKIE TESTY PRZESZŁY POMYŚLNIE!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ BŁĄD: {e}")
        import traceback
        traceback.print_exc()
