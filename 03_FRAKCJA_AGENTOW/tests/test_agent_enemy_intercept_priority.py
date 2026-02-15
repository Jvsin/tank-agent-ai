"""Ensure visible enemies outside firing range trigger intercept mode."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def test_agent_intercepts_visible_enemy_out_of_range():
    agent = SmartAgent(name="EnemyInterceptPriorityTest")
    my_status = {
        "position": {"x": 50.0, "y": 50.0},
        "heading": 0.0,
        "hp": 90.0,
        "_max_hp": 100.0,
        "_team": 1,
        "_id": "tank_i1",
        "_top_speed": 3.0,
        "_barrel_spin_rate": 90.0,
        "_heading_spin_rate": 70.0,
        "_vision_range": 120.0,
        "ammo_loaded": "LIGHT",
    }
    sensor = {
        "seen_tanks": [
            {
                "id": "enemy_1",
                "team": 2,
                "tank_type": "LIGHT",
                "position": {"x": 130.0, "y": 50.0},
                "is_damaged": False,
                "heading": 180.0,
            }
        ],
        "seen_obstacles": [],
        "seen_terrains": [],
        "seen_powerups": [],
    }

    agent.get_action(current_tick=5, my_tank_status=my_status, sensor_data=sensor, enemies_remaining=5)
    assert agent.current_goal is not None
    assert agent.current_goal.mode == "intercept_enemy"
