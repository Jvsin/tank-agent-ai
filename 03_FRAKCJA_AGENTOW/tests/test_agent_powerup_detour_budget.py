"""Powerup preference should depend on context, not always-on bonus."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def _base_status(hp: float) -> dict:
    return {
        "position": {"x": 50.0, "y": 95.0},
        "heading": 0.0,
        "hp": hp,
        "_max_hp": 100.0,
        "_team": 1,
        "_id": "tank_p1",
        "_top_speed": 3.0,
        "_barrel_spin_rate": 90.0,
        "_heading_spin_rate": 70.0,
        "_vision_range": 120.0,
        "ammo_loaded": "LIGHT",
    }


def test_medkit_becomes_preferred_on_low_hp():
    agent = SmartAgent(name="PowerupPreferredLowHpTest")
    sensor = {
        "seen_tanks": [],
        "seen_obstacles": [],
        "seen_terrains": [],
        "seen_powerups": [{"position": {"x": 60.0, "y": 95.0}, "powerup_type": "Medkit"}],
    }
    agent.get_action(current_tick=1, my_tank_status=_base_status(hp=40.0), sensor_data=sensor, enemies_remaining=5)
    cell = agent.model.to_cell(60.0, 95.0)
    assert cell in agent.model.preferred_powerup_cells


def test_medkit_not_preferred_on_full_hp():
    agent = SmartAgent(name="PowerupNotPreferredFullHpTest")
    sensor = {
        "seen_tanks": [],
        "seen_obstacles": [],
        "seen_terrains": [],
        "seen_powerups": [{"position": {"x": 60.0, "y": 95.0}, "powerup_type": "Medkit"}],
    }
    agent.get_action(current_tick=1, my_tank_status=_base_status(hp=100.0), sensor_data=sensor, enemies_remaining=5)
    cell = agent.model.to_cell(60.0, 95.0)
    assert cell not in agent.model.preferred_powerup_cells
