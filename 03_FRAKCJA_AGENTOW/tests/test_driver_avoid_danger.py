"""Unit tests for MotionDriver behavior when next path cell is dangerous."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(THIS_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent_core.world_model import WorldModel
from agent_core.driver import MotionDriver
from agent_core.geometry import heading_to_angle_deg


def test_drive_path_avoids_known_dangerous_next_cell():
    wm = WorldModel(grid_size=10.0)
    driver = MotionDriver(wm)

    # my cell (5,5), facing +X (heading=0). next cell (6,5) is to the right (0°)
    my_cell = (5, 5)
    next_cell = (6, 5)

    # mark next_cell as dangerous
    s = wm.get_state(next_cell)
    s.danger = 2.0

    # set path so the immediate next node is the dangerous cell
    driver.path = [next_cell]

    # world coords centered on my_cell
    my_x, my_y = wm.to_world_center(my_cell)
    my_heading = 0.0

    turn, speed = driver.drive_path(my_x, my_y, my_heading, top_speed=3.0)

    # If driver tried to go straight into the dangerous cell, turn would be ~0
    # We expect it to avoid going straight; require a noticeable turn
    assert abs(turn) > 6.0, "Driver did not avoid driving straight into dangerous next cell"


if __name__ == '__main__':
    raise SystemExit(test_drive_path_avoids_known_dangerous_next_cell())