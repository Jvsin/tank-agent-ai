"""Verify ally-aware movement slows down to avoid friendly blocking."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def test_two_allies_facing_each_other_lower_id_reverses_after_stuck():
    """Dwa sojuszniki naprzeciw siebie: czołg z niższym ID cofa się po wykryciu deadlocku."""
    agent = SmartAgent(name="AllyDeadlockTest")
    my_status = {
        "position": {"x": 50.0, "y": 95.0},
        "heading": 0.0,
        "hp": 100.0,
        "_max_hp": 100.0,
        "_team": 1,
        "_id": "A",  # Niższe niż "ally_B" -> ten czołg ustępuje
        "_top_speed": 3.0,
        "_barrel_spin_rate": 90.0,
        "_heading_spin_rate": 70.0,
        "_vision_range": 100.0,
        "ammo_loaded": "LIGHT",
    }
    sensor = {
        "seen_tanks": [
            {"id": "ally_B", "team": 1, "position": {"x": 55.0, "y": 95.0}, "heading": 180.0}
        ],
        "seen_obstacles": [],
        "seen_terrains": [],
        "seen_powerups": [],
    }
    got_reverse = False
    for tick in range(20):
        action = agent.get_action(
            current_tick=tick, my_tank_status=my_status, sensor_data=sensor, enemies_remaining=5
        )
        if action.move_speed < 0:
            got_reverse = True
            break
    assert got_reverse, "Czołg z niższym ID powinien cofnąć się po deadlocku"


def test_agent_yields_when_ally_occupies_lane_ahead():
    agent = SmartAgent(name="AllyCollisionAvoidanceTest")
    my_status = {
        "position": {"x": 50.0, "y": 95.0},
        "heading": 0.0,
        "hp": 100.0,
        "_max_hp": 100.0,
        "_team": 1,
        "_id": "C",  # lane offset 0
        "_top_speed": 3.0,
        "_barrel_spin_rate": 90.0,
        "_heading_spin_rate": 70.0,
        "_vision_range": 100.0,
        "ammo_loaded": "LIGHT",
    }
    sensor = {
        "seen_tanks": [
            {
                "id": "ally_1",
                "team": 1,
                "position": {"x": 55.0, "y": 95.0},
                "heading": 0.0,
            }
        ],
        "seen_obstacles": [],
        "seen_terrains": [],
        "seen_powerups": [],
    }

    action = agent.get_action(current_tick=1, my_tank_status=my_status, sensor_data=sensor, enemies_remaining=5)
    assert action.move_speed <= my_status["_top_speed"] * 0.65
