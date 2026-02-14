"""
Testy zachowania bojowego agenta.

Sprawdza:
- czy agent przechodzi z trybu ucieczki do walki, gdy widzi przeciwnika,
- czy dla widocznego przeciwnika wybiera cel ataku,
- czy realnie oddaje strzał w prostym, korzystnym scenariuszu.
"""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def _base_status() -> dict:
    return {
        "_id": "tank_test",
        "_team": 1,
        "_tank_type": "LIGHT",
        "hp": 80.0,
        "_max_hp": 80.0,
        "position": {"x": 50.0, "y": 50.0},
        "heading": 0.0,
        "barrel_angle": 0.0,
        "_top_speed": 5.0,
        "_heading_spin_rate": 70.0,
        "_barrel_spin_rate": 90.0,
        "_vision_range": 80.0,
    }


def test_break_escape_on_enemy() -> int:
    agent = SmartAgent(name="CombatBreakEscapeTest")
    status = _base_status()

    hazard_sensor = {
        "seen_tanks": [],
        "seen_powerups": [],
        "seen_obstacles": [],
        "seen_terrains": [
            {
                "position": {"x": status["position"]["x"], "y": status["position"]["y"]},
                "type": "Water",
                "dmg": 1,
                "speed_modifier": 0.7,
            }
        ],
    }

    enemy_sensor = {
        "seen_tanks": [
            {
                "id": "enemy_1",
                "team": 2,
                "tank_type": "HEAVY",
                "is_damaged": False,
                "position": {"x": 80.0, "y": 50.0},
            }
        ],
        "seen_powerups": [],
        "seen_obstacles": [],
        "seen_terrains": [],
    }

    _ = agent.get_action(
        current_tick=1,
        my_tank_status=status,
        sensor_data=hazard_sensor,
        enemies_remaining=5,
    )

    if agent.driver.escape_ticks <= 0:
        print("[COMBAT] FAIL: agent nie wszedł w tryb escape przy hazardzie")
        return 1

    action2 = agent.get_action(
        current_tick=2,
        my_tank_status=status,
        sensor_data=enemy_sensor,
        enemies_remaining=1,
    )

    if agent.driver.escape_ticks != 0:
        print("[COMBAT] FAIL: agent nie przerwał escape po wykryciu przeciwnika")
        return 1

    if abs(action2.move_speed) < 0.10:
        print("[COMBAT] FAIL: brak aktywnego ruchu po przejściu do walki")
        return 1

    if agent.current_goal is None or not agent.current_goal.mode.startswith("attack"):
        print("[COMBAT] FAIL: po wykryciu przeciwnika nie wybrano celu ataku")
        return 1

    print("[COMBAT] PASS break_escape_on_enemy")
    return 0


def test_fire_in_easy_duel() -> int:
    agent = SmartAgent(name="CombatFireTest")
    status = _base_status()

    sensor = {
        "seen_tanks": [
            {
                "id": "enemy_close",
                "team": 2,
                "tank_type": "LIGHT",
                "is_damaged": False,
                "position": {"x": 74.0, "y": 50.0},
            }
        ],
        "seen_powerups": [],
        "seen_obstacles": [],
        "seen_terrains": [],
    }

    fire_ticks = 0
    moving_ticks = 0

    for tick in range(1, 21):
        action = agent.get_action(
            current_tick=tick,
            my_tank_status=status,
            sensor_data=sensor,
            enemies_remaining=1,
        )

        status["heading"] = (status["heading"] + action.heading_rotation_angle) % 360
        status["barrel_angle"] = (status["barrel_angle"] + action.barrel_rotation_angle) % 360

        if abs(action.move_speed) > 0.15:
            moving_ticks += 1

        if action.should_fire:
            fire_ticks += 1

    if moving_ticks < 10:
        print("[COMBAT] FAIL: agent jest zbyt pasywny w prostym pojedynku")
        return 1

    if fire_ticks < 1:
        print("[COMBAT] FAIL: agent nie oddał żadnego strzału w prostym pojedynku")
        return 1

    print("[COMBAT] PASS fire_in_easy_duel")
    return 0


def run_test() -> int:
    r1 = test_break_escape_on_enemy()
    if r1 != 0:
        return r1

    r2 = test_fire_in_easy_duel()
    if r2 != 0:
        return r2

    print("[COMBAT] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_test())
