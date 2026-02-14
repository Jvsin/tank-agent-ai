"""
Test 2: Agent powinien uciekać z pola szkodliwego.

Scenariusz:
- Czołg stoi na Water (dmg>0)
- Oczekujemy szybkiego wejścia w tryb ucieczki (move_speed > 0)
- Brak stania przez większość testu
"""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def run_test(ticks: int = 120) -> int:
    agent = SmartAgent(name="HazardEscapeTest")

    my_status = {
        "_id": "tank_test",
        "_team": 1,
        "_tank_type": "LIGHT",
        "hp": 80.0,
        "_max_hp": 80.0,
        "position": {"x": 105.0, "y": 105.0},
        "heading": 0.0,
        "barrel_angle": 0.0,
        "_top_speed": 5.0,
        "_heading_spin_rate": 70.0,
        "_barrel_spin_rate": 90.0,
    }

    move_ticks = 0
    escape_like_ticks = 0

    for tick in range(1, ticks + 1):
        sensor = {
            "seen_tanks": [],
            "seen_powerups": [],
            "seen_obstacles": [],
            "seen_terrains": [
                {
                    "position": {"x": my_status["position"]["x"], "y": my_status["position"]["y"]},
                    "type": "Water",
                    "speed_modifier": 0.7,
                    "dmg": 1,
                }
            ],
        }

        # emulacja małej utraty HP od terenu
        my_status["hp"] = max(0.0, my_status["hp"] - 0.1)

        action = agent.get_action(
            current_tick=tick,
            my_tank_status=my_status,
            sensor_data=sensor,
            enemies_remaining=5,
        )

        if abs(action.move_speed) > 0.20:
            move_ticks += 1
        if action.move_speed > 0.8:
            escape_like_ticks += 1

        # uproszczona aktualizacja stanu
        my_status["heading"] = (my_status["heading"] + action.heading_rotation_angle) % 360
        if abs(action.move_speed) > 0.01:
            import math
            dt = 1.0 / 60.0
            h = math.radians(my_status["heading"])
            my_status["position"]["x"] += math.cos(h) * action.move_speed * dt
            my_status["position"]["y"] += math.sin(h) * action.move_speed * dt

    move_ratio = move_ticks / ticks
    escape_ratio = escape_like_ticks / ticks

    print(f"[HAZARD_ESCAPE] ticks={ticks} move_ratio={move_ratio:.2f} escape_ratio={escape_ratio:.2f}")

    if move_ratio < 0.75:
        print("[HAZARD_ESCAPE] FAIL: agent za mało ucieka z hazardu")
        return 1

    if escape_ratio < 0.25:
        print("[HAZARD_ESCAPE] FAIL: agent zbyt rzadko daje mocny ruch ucieczkowy")
        return 1

    print("[HAZARD_ESCAPE] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_test())
