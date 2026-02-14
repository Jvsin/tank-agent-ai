"""
Test 1: Agent nie powinien stać bez potrzeby.

Scenariusz:
- Brak wrogów, brak przeszkód, brak powerupów
- Oczekujemy, że agent będzie eksplorował (move_speed > 0 przez większość ticków)
"""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from final_agent import SmartAgent


def run_test(ticks: int = 180) -> int:
    agent = SmartAgent(name="NoIdleTest")

    my_status = {
        "_id": "tank_test",
        "_team": 1,
        "_tank_type": "LIGHT",
        "hp": 80,
        "_max_hp": 80,
        "position": {"x": 35.0, "y": 35.0},
        "heading": 0.0,
        "barrel_angle": 0.0,
        "_top_speed": 5.0,
        "_heading_spin_rate": 70.0,
        "_barrel_spin_rate": 90.0,
    }

    sensor = {
        "seen_tanks": [],
        "seen_powerups": [],
        "seen_obstacles": [],
        "seen_terrains": [],
    }

    move_ticks = 0
    spin_ticks = 0
    direction_flips = 0
    last_turn_sign = 0

    for tick in range(1, ticks + 1):
        action = agent.get_action(
            current_tick=tick,
            my_tank_status=my_status,
            sensor_data=sensor,
            enemies_remaining=5,
        )

        if abs(action.move_speed) > 0.15:
            move_ticks += 1
        if abs(action.heading_rotation_angle) > 20.0:
            spin_ticks += 1

        if abs(action.heading_rotation_angle) >= 2.0:
            current_sign = 1 if action.heading_rotation_angle > 0 else -1
            if last_turn_sign != 0 and current_sign != last_turn_sign:
                direction_flips += 1
            last_turn_sign = current_sign

        # uproszczona aktualizacja pozycji/heading dla kolejnego ticku
        my_status["heading"] = (my_status["heading"] + action.heading_rotation_angle) % 360
        if abs(action.move_speed) > 0.01:
            # zgodnie z fizyką silnika: x += cos(heading)*speed*dt, y += sin(heading)*speed*dt
            import math
            dt = 1.0 / 60.0
            h = math.radians(my_status["heading"])
            my_status["position"]["x"] += math.cos(h) * action.move_speed * dt
            my_status["position"]["y"] += math.sin(h) * action.move_speed * dt

    move_ratio = move_ticks / ticks
    spin_ratio = spin_ticks / ticks
    flips_per_minute_equiv = direction_flips * (60.0 / max(1.0, ticks / 60.0))

    print(
        f"[NO_IDLE] ticks={ticks} move_ticks={move_ticks} move_ratio={move_ratio:.2f} "
        f"spin_ratio={spin_ratio:.2f} direction_flips={direction_flips} "
        f"flips_per_minute_equiv={flips_per_minute_equiv:.1f}"
    )

    # Agent powinien aktywnie jechać, a nie stać.
    if move_ratio < 0.70:
        print("[NO_IDLE] FAIL: za dużo bezczynności")
        return 1

    # Nie powinien stale wykonywać bardzo dużych skrętów.
    if spin_ratio > 0.55:
        print("[NO_IDLE] FAIL: zbyt częste duże skręty")
        return 1

    if direction_flips > 28:
        print("[NO_IDLE] FAIL: zbyt częsta zmiana kierunku skrętu (drżenie)")
        return 1

    print("[NO_IDLE] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_test())
