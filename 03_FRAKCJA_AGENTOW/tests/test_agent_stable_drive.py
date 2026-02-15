"""Tests that agent produces stable steering and speed when following a path."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def test_agent_path_following_is_stable():
    """Agent jedzie wzdłuż checkpointów – sprawdź stabilność kierunku i prędkości."""
    agent = SmartAgent(name="StableDriveTest")

    # Czołg Team 1 na ścieżce checkpointów, skierowany na wschód (kolejny checkpoint przed nami)
    # Checkpointy dla mapy advanced_road_trees: (15,95), (55,95), (95,95), (135,95), (175,95), (185,95)
    # Tank na (50, 95), heading 0 (wschód) -> jedzie do (55,95) lub (95,95)
    my_status = {
        "position": {"x": 50.0, "y": 95.0},
        "heading": 0.0,  # facing +X (wschód)
        "hp": 100.0,
        "_max_hp": 100.0,
        "_team": 1,
        "_id": "test_tank",
        "_top_speed": 3.0,
        "_barrel_spin_rate": 90.0,
        "_heading_spin_rate": 70.0,
        "_vision_range": 100.0,
    }

    sensor = {"seen_tanks": [], "seen_obstacles": [], "seen_terrains": [], "seen_powerups": []}

    turns = []
    speeds = []
    for tick in range(1, 9):
        action = agent.get_action(current_tick=tick, my_tank_status=my_status, sensor_data=sensor, enemies_remaining=0)
        turns.append(action.heading_rotation_angle)
        speeds.append(action.move_speed)

    # Turn changes should be small between consecutive ticks -> no dithering
    deltas = [abs(turns[i] - turns[i - 1]) for i in range(1, len(turns))]
    assert all(d <= 6.0 for d in deltas), f"Turn deltas too large: {deltas}"

    # Speed should remain reasonably high (agent moving toward checkpoint)
    assert all(s >= 0.5 * my_status["_top_speed"] for s in speeds[:6]), f"Speeds too low: {speeds}"