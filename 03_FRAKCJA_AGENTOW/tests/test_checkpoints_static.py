"""Tests for static checkpoint corridor and team direction."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent_core.checkpoints import STATIC_CORRIDOR_CHECKPOINTS, build_checkpoints_to_enemy  # noqa: E402


def test_team1_uses_static_corridor_order():
    cps = build_checkpoints_to_enemy(team=1, start_x=40.0, start_y=40.0)
    assert cps == STATIC_CORRIDOR_CHECKPOINTS
    assert cps[0][0] < cps[-1][0]
    mid_y = cps[len(cps) // 2][1]
    assert cps[0][1] < mid_y
    assert cps[-1][1] < mid_y


def test_team2_uses_reversed_corridor_order():
    cps = build_checkpoints_to_enemy(team=2, start_x=180.0, start_y=40.0)
    assert cps == list(reversed(STATIC_CORRIDOR_CHECKPOINTS))
    assert cps[0][0] > cps[-1][0]
