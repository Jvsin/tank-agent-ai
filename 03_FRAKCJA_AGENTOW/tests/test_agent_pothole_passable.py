"""Regression tests for pothole passability and panic escape speed."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent
from agent_core.world_model import WorldModel


def test_pothole_cells_are_costly_but_not_hard_blocked():
    model = WorldModel(grid_size=10.0)
    cell = (10, 10)
    state = model.get_state(cell)
    state.danger = 5.5
    state.blocked = 1.2
    model.pothole_cells.add(cell)

    assert model.is_blocked_for_pathing(cell) is False
    assert model.movement_cost(cell) > 1.9


def test_agent_uses_high_speed_on_live_hazard():
    agent = SmartAgent(name="PanicHazardSpeedTest")
    my_status = {
        "_id": "tank_h1",
        "_team": 1,
        "hp": 90.0,
        "_max_hp": 100.0,
        "position": {"x": 105.0, "y": 105.0},
        "heading": 0.0,
        "barrel_angle": 0.0,
        "_top_speed": 5.0,
        "_heading_spin_rate": 70.0,
        "_barrel_spin_rate": 90.0,
        "_vision_range": 120.0,
        "ammo_loaded": "LIGHT",
    }
    sensor = {
        "seen_tanks": [],
        "seen_powerups": [],
        "seen_obstacles": [],
        "seen_terrains": [
            {
                "position": {"x": 105.0, "y": 105.0},
                "type": "Water",
                "dmg": 1,
            },
            {
                "position": {"x": 115.0, "y": 105.0},
                "type": "Grass",
                "dmg": 0,
            },
        ],
    }

    action = agent.get_action(current_tick=1, my_tank_status=my_status, sensor_data=sensor, enemies_remaining=5)
    assert action.move_speed >= my_status["_top_speed"] * 0.9
