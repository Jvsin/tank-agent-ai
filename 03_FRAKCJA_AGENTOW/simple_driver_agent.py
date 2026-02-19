"""
Simple checkpoint-following agent.

Drives from checkpoint to checkpoint along STATIC_CORRIDOR_CHECKPOINTS.
No shooting, no turret rotation -- pure navigation.

Usage:
    python simple_driver_agent.py --port 8001
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Body, FastAPI
from pydantic import BaseModel
import uvicorn

from agent_core.checkpoints import STATIC_CORRIDOR_CHECKPOINTS, lane_offset_checkpoint
from agent_core.fuzzy_turret import FuzzyTurretController
from agent_core.geometry import euclidean_distance, heading_to_angle_deg, normalize_angle_diff, to_xy


class ActionCommand(BaseModel):
    barrel_rotation_angle: float = 0.0
    heading_rotation_angle: float = 0.0
    move_speed: float = 0.0
    ammo_to_load: Optional[str] = None
    should_fire: bool = False


class SimpleDriverAgent:
    def __init__(self, name: str = "SimpleDriver"):
        self.name = name
        self.is_destroyed = False

        self.checkpoints: Optional[List[Tuple[float, float]]] = None
        self.checkpoint_idx: int = 0
        self.tank_id: str = "default"
        self.team: Optional[int] = None
        self.arrival_radius: float = 15.0
        self.turret: Optional[FuzzyTurretController] = None

        print(f"[{self.name}] online")

    def _init_checkpoints(self, my_tank_status: Dict[str, Any], x: float) -> None:
        """Build the checkpoint list on the first tick based on team / position."""
        self.team = my_tank_status.get("_team")
        if self.team is None:
            self.team = 2 if x > 100.0 else 1

        if self.team == 2:
            self.checkpoints = list(reversed(STATIC_CORRIDOR_CHECKPOINTS))
        else:
            self.checkpoints = list(STATIC_CORRIDOR_CHECKPOINTS)

        self.tank_id = str(my_tank_status.get("_id", "default"))
        self.checkpoint_idx = 0
        print(f"[{self.name}] team={self.team} start_cp=0/{len(self.checkpoints)}")

    def _current_target(self) -> Tuple[float, float]:
        assert self.checkpoints is not None
        cp = self.checkpoints[self.checkpoint_idx]
        return lane_offset_checkpoint(self.tank_id, cp)

    def get_action(
        self,
        current_tick: int,
        my_tank_status: Dict[str, Any],
        sensor_data: Dict[str, Any],
        enemies_remaining: int,
    ) -> ActionCommand:
        x, y = to_xy(my_tank_status.get("position", {}))
        heading = float(my_tank_status.get("heading", 0.0) or 0.0)
        top_speed = float(my_tank_status.get("_top_speed", 3.0) or 3.0)
        max_heading = float(my_tank_status.get("_heading_spin_rate", 30.0) or 30.0)
        barrel_angle = float(my_tank_status.get("barrel_angle", 0.0) or 0.0)
        max_barrel = float(my_tank_status.get("_barrel_spin_rate", 30.0) or 30.0)
        vision_range = float(my_tank_status.get("_vision_range", 70.0) or 70.0)

        if self.checkpoints is None:
            self._init_checkpoints(my_tank_status, x)

        if self.turret is None:
            self.turret = FuzzyTurretController(
                max_barrel_spin_rate=max_barrel,
                vision_range=vision_range,
            )

        assert self.checkpoints is not None

        # --- Ally / enemy split ---
        seen = sensor_data.get("seen_tanks", [])
        enemies = [t for t in seen if t.get("team") != self.team]

        # --- Checkpoint movement ---
        while self.checkpoint_idx < len(self.checkpoints) - 1:
            tx, ty = self._current_target()
            if euclidean_distance(x, y, tx, ty) < self.arrival_radius:
                self.checkpoint_idx += 1
            else:
                break

        tx, ty = self._current_target()
        desired = heading_to_angle_deg(x, y, tx, ty)
        diff = normalize_angle_diff(desired, heading)
        turn = max(-max_heading, min(diff, max_heading))

        if abs(diff) > 45.0:
            speed = top_speed * 0.3
        elif abs(diff) > 20.0:
            speed = top_speed * 0.6
        else:
            speed = top_speed

        # --- Ammo inventory ---
        ammo_stocks: Dict[str, int] = {}
        raw_ammo = my_tank_status.get("ammo", {})
        if isinstance(raw_ammo, dict):
            for key, val in raw_ammo.items():
                if isinstance(val, dict):
                    ammo_stocks[key] = int(val.get("count", 0) or 0)
                else:
                    ammo_stocks[key] = int(val or 0)
        current_ammo = str(my_tank_status.get("ammo_loaded", "") or "").upper() or None

        # --- Turret ---
        barrel_rotation, should_fire, ammo_to_load = self.turret.update(
            my_x=x,
            my_y=y,
            my_heading=heading,
            current_barrel_angle=barrel_angle,
            seen_tanks=enemies,
            max_barrel_rotation=max_barrel,
            ammo_stocks=ammo_stocks,
            current_ammo=current_ammo,
        )

        if current_tick % 60 == 0:
            dist = euclidean_distance(x, y, tx, ty)
            print(
                f"[{self.name}] tick={current_tick} cp={self.checkpoint_idx + 1}/{len(self.checkpoints)} "
                f"dist={dist:.1f} speed={speed:.2f} turn={turn:.1f} enemies={len(enemies)} ammo={current_ammo}"
            )

        return ActionCommand(
            heading_rotation_angle=turn,
            move_speed=speed,
            barrel_rotation_angle=barrel_rotation,
            should_fire=should_fire,
            ammo_to_load=ammo_to_load,
        )

    def destroy(self):
        self.is_destroyed = True
        print(f"[{self.name}] destroyed")

    def end(self, damage_dealt: float, tanks_killed: int):
        print(f"[{self.name}] end damage={damage_dealt} kills={tanks_killed}")


app = FastAPI(title="Simple Driver Agent", version="1.0.0")
agent = SimpleDriverAgent()


@app.get("/")
async def root():
    return {"message": f"Agent {agent.name} is running", "destroyed": agent.is_destroyed}


@app.post("/agent/action", response_model=ActionCommand)
async def get_action(payload: Dict[str, Any] = Body(...)):
    return agent.get_action(
        current_tick=payload.get("current_tick", 0),
        my_tank_status=payload.get("my_tank_status", {}),
        sensor_data=payload.get("sensor_data", {}),
        enemies_remaining=payload.get("enemies_remaining", 0),
    )


@app.post("/agent/destroy", status_code=204)
async def destroy():
    agent.destroy()


@app.post("/agent/end", status_code=204)
async def end(payload: Dict[str, Any] = Body(...)):
    agent.end(
        damage_dealt=payload.get("damage_dealt", 0.0),
        tanks_killed=payload.get("tanks_killed", 0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run simple checkpoint driver agent")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--name", type=str, default=None)
    args = parser.parse_args()

    if args.name:
        agent.name = args.name
    else:
        agent.name = f"SimpleDriver_{args.port}"

    print(f"Starting {agent.name} on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", access_log=False)
