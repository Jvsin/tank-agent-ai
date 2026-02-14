"""Tests that agent produces stable steering and speed when following a path."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def test_agent_path_following_is_stable():
    agent = SmartAgent(name="StableDriveTest")

    # Create a straight path ahead in world cells and commit to it
    agent.driver.path = [(10, 10), (11, 10), (12, 10), (13, 10), (14, 10)]
    agent.current_goal = None
    agent.route_commit_until = 999999
    agent.route_commit_mode = "explore"

    my_status = {
        "position": {"x": 100.0, "y": 100.0},
        "heading": 0.0,  # facing +X
        "hp": 100.0,
        "_max_hp": 100.0,
        "_team": 1,
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

    # Speed should remain high (agent moving forward steadily)
    assert all(s >= 0.75 * my_status["_top_speed"] for s in speeds[:6]), f"Speeds too low: {speeds}"