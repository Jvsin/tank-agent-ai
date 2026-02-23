# Agent Architecture

## Overview

The agent is a stateful, AI-driven tank controller exposed as a FastAPI HTTP server. On each game tick the engine calls `/agent/action`, which runs the agent's decision pipeline and returns a single `ActionCommand`. The codebase is split between the top-level server/orchestrator (`agent.py`) and the `agent_core/` library of subsystems.

```
agent.py                   ← HTTP server + TankAgent orchestrator
agent_core/
  checkpoints.py           ← Predefined corridor waypoints & lane offsets
  world_model.py           ← Grid-based spatial memory
  planner.py               ← A* pathfinder
  driver.py                ← Low-level motion controller
  fuzzy_turret.py          ← Fuzzy-logic turret & firing controller
  geometry.py              ← Pure math helpers
```

---

## Feature 1 – HTTP API & Agent Lifecycle

**File:** `agent.py`

| What | Lines |
|------|-------|
| `ActionCommand` Pydantic response model | [agent.py](agent.py#L16-L21) |
| `TankAgent.__init__` – state initialisation | [agent.py](agent.py#L24-L48) |
| FastAPI app & global `agent` singleton | [agent.py](agent.py#L293-L294) |
| `GET /` – liveness probe | [agent.py](agent.py#L297-L302) |
| `POST /agent/action` – main decision endpoint | [agent.py](agent.py#L305-L313) |
| `POST /agent/destroy` – destroy notification | [agent.py](agent.py#L316-L318) |
| `POST /agent/end` – end-of-game stats | [agent.py](agent.py#L321-L327) |
| CLI argument parsing & `uvicorn` startup | [agent.py](agent.py#L330-L363) |

The `get_action` method ([agent.py](agent.py#L196-L284)) is the central dispatch point; it extracts tank state, selects a movement mode, computes `turn`/`speed`, delegates to the turret, and returns an `ActionCommand`.

---

## Feature 2 – Checkpoint Navigation (default mode)

**Files:** `agent_core/checkpoints.py`, `agent.py`

The tank follows a predefined corridor of world-space waypoints until it crosses a team-specific Y threshold, after which it may switch to autonomous mode.

| What | Location |
|------|----------|
| `STATIC_CORRIDOR_CHECKPOINTS` raw grid coords | [checkpoints.py](agent_core/checkpoints.py#L11-L21) |
| Scaling to world coords (`× 10 + 5`) | [checkpoints.py](agent_core/checkpoints.py#L23-L24) |
| Mirroring checkpoints for team 2 (reversed) | [checkpoints.py](agent_core/checkpoints.py#L25-L27) |
| `lane_offset_checkpoint` – per-tank Y lane spread (±4 units based on `tank_id` hash) | [checkpoints.py](agent_core/checkpoints.py#L51-L55) |
| `build_checkpoints_to_enemy` – returns team-appropriate list | [checkpoints.py](agent_core/checkpoints.py#L38-L49) |
| `_init_checkpoints` – team detection, closest CP selection | [agent.py](agent.py#L51-L83) |
| `_current_target` – returns current waypoint world coords | [agent.py](agent.py#L85-L88) |
| Checkpoint advance loop + heading/speed logic | [agent.py](agent.py#L213-L229) |
| Autonomous-mode threshold check (`y ≤ 80` / `y ≥ 120`) | [agent.py](agent.py#L90-L97) |

---

## Feature 3 – World Model (spatial memory)

**File:** `agent_core/world_model.py`

A grid-based map (`grid_size = 10` world units per cell) that accumulates sensor observations and decays them over time.

| What | Location |
|------|----------|
| `CellState` dataclass (`safe`, `danger`, `blocked`) | [world_model.py](agent_core/world_model.py#L7-L11) |
| `WorldModel.__init__` – TTL dicts, powerup/checkpoint cell sets | [world_model.py](agent_core/world_model.py#L14-L28) |
| `to_cell` / `to_world_center` – coordinate conversion | [world_model.py](agent_core/world_model.py#L30-L33) |
| `get_state` – lazy cell creation | [world_model.py](agent_core/world_model.py#L40-L43) |
| `decay_dead_ends` – TTL countdown for dead-ends and occupancy | [world_model.py](agent_core/world_model.py#L48-L71) |
| `mark_dead_end` / `mark_ally_occupancy` / `mark_enemy_occupancy` | [world_model.py](agent_core/world_model.py#L73-L87) |
| `is_blocked_for_pathing` – blocked/danger thresholds + pothole logic | [world_model.py](agent_core/world_model.py#L95-L106) |
| `is_dangerous_cell` – danger ≥ 1.0 check | [world_model.py](agent_core/world_model.py#L108-L112) |
| `local_block_pressure` – sum of neighbour blocked/danger scores | [world_model.py](agent_core/world_model.py#L114-L123) |
| `movement_cost` – composite cost for A* edge weights | [world_model.py](agent_core/world_model.py#L125-L148) |
| World-model update from sensor data (obstacles, terrain, tanks, powerups) | [agent.py](agent.py#L99-L135) |

---

## Feature 4 – A* Pathfinder

**File:** `agent_core/planner.py`

A bounded A* search (Manhattan heuristic, 4-connectivity) that uses `WorldModel` for passability and edge weights.

| What | Location |
|------|----------|
| `AStarPlanner.__init__` | [planner.py](agent_core/planner.py#L9-L11) |
| `_heuristic` – Manhattan distance | [planner.py](agent_core/planner.py#L19-L21) |
| `build_path` – bounding box `±radius` cells, priority queue, path reconstruction | [planner.py](agent_core/planner.py#L23-L62) |
| Dead-end marking on empty path result | [agent.py](agent.py#L170-L173) |
| `path_risk` – per-cell risk score (danger, blocked, ally/enemy occupancy) | [planner.py](agent_core/planner.py#L64-L76) |
| Replan cooldown (every 30 ticks) | [agent.py](agent.py#L231-L244) |

---

## Feature 5 – Motion Driver

**File:** `agent_core/driver.py`

Translates a path (list of grid cells) into per-tick `(turn, speed)` commands, with stuck detection and escape logic.

| What | Location |
|------|----------|
| `MotionDriver.__init__` – path, stuck counters, escape state | [driver.py](agent_core/driver.py#L11-L20) |
| `drive_to_point` – angle diff → clamped turn + proportional speed | [driver.py](agent_core/driver.py#L55-L79) |
| `drive_path` – follows `self.path`, detours around dangerous cells | [driver.py](agent_core/driver.py#L81-L112) |
| `best_immediate_safe_neighbor` – scores adjacent cells (safe, danger, blocked, visit count) | [driver.py](agent_core/driver.py#L27-L43) |
| `update_stuck` – detects < 0.15 unit movement over 10 ticks | [driver.py](agent_core/driver.py#L122-L160) |
| Stuck recovery: marks cells as dead-ends (`ttl=560`), clears path | [driver.py](agent_core/driver.py#L145-L154) |
| `start_escape` / `escape_drive` – random heading escape manoeuvre | [driver.py](agent_core/driver.py#L162-L203) |
| `unblock_drive` – brief reverse with optional wiggle | [driver.py](agent_core/driver.py#L169-L178) |

---

## Feature 6 – Fuzzy Turret Controller

**File:** `agent_core/fuzzy_turret.py`

Uses `scikit-fuzzy` to implement four independent fuzzy inference systems that collectively decide barrel rotation speed, target priority, firing confidence, and idle scan speed.

### 6a – Target Selection FIS
Inputs: `distance` (4 MFs), `threat` (3 MFs). Output: `priority` (5 MFs, 0–100).
- 12 rules map (distance × threat) → priority class.
- `THREAT_WEIGHTS`: `LIGHT=3`, `HEAVY=7`, `Sniper=9`

| What | Location |
|------|----------|
| FIS definition | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L56-L116) |
| `_select_target` – runs FIS per enemy, picks highest priority | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L323-L363) |

### 6b – Rotation Speed FIS
Inputs: `angle_error` (3 MFs), `target_distance` (3 MFs). Output: `speed_factor` (5 MFs, 0–1).
- 7 rules – large error at far distance → very fast spin.

| What | Location |
|------|----------|
| FIS definition | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L118-L168) |
| `_calculate_rotation_speed` | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L365-L382) |

### 6c – Firing Decision FIS
Inputs: `aiming_error` (4 MFs), `firing_distance` (3 MFs), `vulnerability` (3 MFs). Output: `fire_confidence` (3 MFs, 0–1).
- Fire threshold: `FIRE_CONFIDENCE_THRESHOLD = 0.6`
- Cooldown: `COOLDOWN_TICKS = 10` ticks between shots.

| What | Location |
|------|----------|
| FIS definition | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L170-L261) |
| `_should_fire_fuzzy` | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L384-L414) |

### 6d – Adaptive Scan FIS
Active when no enemy is visible. Inputs: `time_unseen` (3 MFs), `scan_error` (2 MFs). Output: `scan_speed` (3 MFs).
- Prioritises scanning toward `last_seen_direction`.

| What | Location |
|------|----------|
| FIS definition | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L263-L297) |
| `_adaptive_scan` | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L416-L447) |

### 6e – Ammo & Destructible Obstacles

| What | Location |
|------|----------|
| `AMMO_SPECS` (range, damage, reload per type) | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L27-L32) |
| `select_ammo` – picks first available ammo type | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L449-L453) |
| `_select_destructible_obstacle` – closest destructible obstacle | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L299-L321) |
| `update` – main entry point, ties all FIS together | [fuzzy_turret.py](agent_core/fuzzy_turret.py#L455-L516) |

---

## Feature 7 – Geometry Utilities

**File:** `agent_core/geometry.py`

Pure, stateless math helpers used throughout all subsystems.

| Function | Description | Location |
|----------|-------------|----------|
| `to_xy(value)` | Extracts `(x, y)` from a dict or object | [geometry.py](agent_core/geometry.py#L7-L10) |
| `normalize_angle_diff(target, current)` | Returns shortest signed angle delta in (−180, 180] | [geometry.py](agent_core/geometry.py#L13-L19) |
| `heading_to_angle_deg(from, to)` | `atan2`-based absolute bearing (0–360°) | [geometry.py](agent_core/geometry.py#L22-L23) |
| `euclidean_distance(x1, y1, x2, y2)` | `math.hypot` wrapper | [geometry.py](agent_core/geometry.py#L26-L27) |

---

## Decision Flow (per tick)

```
/agent/action  (POST)
│
├─ extract position, heading, speed caps from my_tank_status
├─ lazy-init: checkpoints, FuzzyTurretController
│
├─ check mode switch threshold (y ≤ 80 / ≥ 120) → "autonomous"
│
├─ if mode == "checkpoint"
│   ├─ advance checkpoint_idx when within arrival_radius (3 units)
│   └─ heading_to_angle_deg → turn + proportional speed
│
└─ if mode == "autonomous"
    ├─ _update_world_model  (obstacles, terrain dmg, tanks, powerups)
    ├─ replan every 30 ticks
    │   ├─ _select_autonomous_goal  (enemies > powerups > advance)
    │   └─ AStarPlanner.build_path
    └─ MotionDriver.drive_path → turn + speed
│
├─ FuzzyTurretController.update
│   ├─ _select_target (FIS)
│   ├─ _calculate_rotation_speed (FIS)
│   ├─ _should_fire_fuzzy (FIS)  OR  _adaptive_scan (FIS)
│   └─ select_ammo
│
└─ return ActionCommand(heading_rotation_angle, move_speed,
                        barrel_rotation_angle, should_fire, ammo_to_load)
```
