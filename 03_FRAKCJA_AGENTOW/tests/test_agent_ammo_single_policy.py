"""Agent should favor a single primary ammo type."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def test_agent_requests_primary_ammo_when_available():
    agent = SmartAgent(name="AmmoPolicySwitchTest")
    my_status = {
        "position": {"x": 50.0, "y": 50.0},
        "heading": 0.0,
        "hp": 90.0,
        "_max_hp": 100.0,
        "_team": 1,
        "_id": "tank_a1",
        "_top_speed": 3.0,
        "_barrel_spin_rate": 90.0,
        "_heading_spin_rate": 70.0,
        "_vision_range": 120.0,
        "ammo_loaded": "LIGHT",
        "ammo_inventory": {"LIGHT": 10, "HEAVY": 0, "LONG_DISTANCE": 6},
    }
    sensor = {"seen_tanks": [], "seen_obstacles": [], "seen_terrains": [], "seen_powerups": []}
    action = agent.get_action(current_tick=1, my_tank_status=my_status, sensor_data=sensor, enemies_remaining=5)
    assert action.ammo_to_load == "LONG_DISTANCE"


def test_agent_keeps_primary_ammo_when_already_loaded():
    agent = SmartAgent(name="AmmoPolicyStableTest")
    my_status = {
        "position": {"x": 50.0, "y": 50.0},
        "heading": 0.0,
        "hp": 90.0,
        "_max_hp": 100.0,
        "_team": 1,
        "_id": "tank_a2",
        "_top_speed": 3.0,
        "_barrel_spin_rate": 90.0,
        "_heading_spin_rate": 70.0,
        "_vision_range": 120.0,
        "ammo_loaded": "LONG_DISTANCE",
        "ammo_inventory": {"LIGHT": 10, "HEAVY": 0, "LONG_DISTANCE": 6},
    }
    sensor = {"seen_tanks": [], "seen_obstacles": [], "seen_terrains": [], "seen_powerups": []}
    action = agent.get_action(current_tick=1, my_tank_status=my_status, sensor_data=sensor, enemies_remaining=5)
    assert action.ammo_to_load is None
