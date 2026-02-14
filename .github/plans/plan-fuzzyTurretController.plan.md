# Plan: Fuzzy Logic Turret Controller

Replace the current proportional turret controller with a scikit-fuzzy-based system that intelligently prioritizes targets by threat level, adapts rotation speed dynamically, makes nuanced firing decisions based on multiple factors, and performs context-aware scanning when idle. The fuzzy controller will process sensor data from the agent's `get_action` method to make decisions about target selection, barrel rotation, and firing timing.

## Steps

### 1. Create fuzzy controller module

Create `03_FRAKCJA_AGENTOW/agent_core/fuzzy_turret.py`

- Define `FuzzyTurretController` class matching the interface of `SimpleTurretController` in `turret.py`
- Constructor signature: `__init__(self, max_barrel_spin_rate: float, vision_range: float, aim_threshold: float = 2.5)`
- Same `update()` method signature: returns `Tuple[float, bool]` (rotation, should_fire)
- Include internal state: `cooldown_ticks`, `last_seen_direction`, `enemy_position_history`

### 2. Implement fuzzy inference system for target selection

- Create membership functions using `skfuzzy.trimf` and `skfuzzy.trapmf`:
  - Input: **distance** (0-150 units) → {very_close, close, medium, far}
  - Input: **threat_level** (0-10 scale) → {low, medium, high} based on tank type mapping (Light=3, Heavy=7, Sniper=9)
  - Output: **target_priority** (0-100) → {ignore, low, medium, high, critical}
- Define rules (8-12 rules):
  - "IF distance is very_close AND threat is high THEN priority is critical"
  - "IF distance is far AND threat is low THEN priority is low"
  - Design rules to prefer closer dangerous enemies over distant weak ones
- Use `skfuzzy.control.ControlSystem` and `ControlSystemSimulation` for evaluation
- Method: `_select_target(self, my_x, my_y, seen_tanks) -> Optional[SeenTank]`

### 3. Implement fuzzy inference system for rotation speed

- Create membership functions:
  - Input: **angle_error** (0-180°) → {small, medium, large}
  - Input: **target_distance** (0-150 units) → {close, medium, far}
  - Output: **rotation_speed_factor** (0-1.0) → {very_slow, slow, medium, fast, very_fast}
- Define rules (6-8 rules):
  - "IF error is small THEN speed is very_slow" (precision aiming)
  - "IF error is large AND distance is far THEN speed is fast" (quick acquisition)
  - "IF error is medium AND distance is close THEN speed is medium" (tracking)
- Method: `_calculate_rotation_speed(self, angle_error, distance) -> float`
- Multiply result by `max_barrel_spin_rate` to respect tank-specific limits

### 4. Implement fuzzy inference system for firing decision

- Create membership functions:
  - Input: **aiming_error** (0-10°) → {perfect, good, acceptable, poor}
  - Input: **target_distance** (0-150 units) → {optimal, suboptimal, extreme} (based on assumed ammo range ~50 units)
  - Input: **target_vulnerability** (0-1 scale) → {resilient, normal, vulnerable} (from `is_damaged` flag + distance)
  - Output: **fire_confidence** (0-1.0) → {no, maybe, yes}
- Define rules (10-15 rules):
  - "IF aiming_error is perfect AND distance is optimal THEN confidence is yes"
  - "IF aiming_error is poor OR distance is extreme THEN confidence is no"
  - "IF target_vulnerability is vulnerable AND aiming_error is acceptable THEN confidence is yes"
- Method: `_should_fire_fuzzy(self, angle_error, distance, is_damaged) -> bool`
- Return True if fire_confidence > 0.6 and cooldown_ticks == 0

### 5. Implement adaptive scanning behavior

- Create membership functions:
  - Input: **time_since_last_seen** (0-100 ticks) → {recent, moderate, long}
  - Input: **scan_direction_error** (0-180°) → {aligned, misaligned} (current vs. last known enemy direction)
  - Output: **scan_speed_factor** (0-1.0) → {slow, medium, fast}
- Define rules (4-6 rules):
  - "IF time_since_last_seen is recent AND direction_error is misaligned THEN speed is fast" (return to last known)
  - "IF time_since_last_seen is long THEN speed is medium" (standard sweep)
- Method: `_adaptive_scan(self, current_barrel_angle, max_rotation) -> float`
- Store `last_seen_direction` when enemies disappear, track ticks since

### 6. Integrate fuzzy systems in main update method

- In `update()` method flow:
  - If `seen_tanks` empty → call `_adaptive_scan()` and return `(rotation, False)`
  - Else → call `_select_target()` to choose best enemy
  - Calculate angle to target using `heading_to_angle_deg()` from `geometry.py`
  - Compute angle error with `normalize_angle_diff()`
  - Call `_calculate_rotation_speed(angle_error, distance)` → get speed factor
  - Apply rotation: `rotation = speed_factor * max_barrel_spin_rate * sign(error)`
  - Clamp rotation to `max_barrel_rotation` parameter
  - Call `_should_fire_fuzzy(angle_error, distance, target.is_damaged)` → get fire decision
  - Decrement `cooldown_ticks` if > 0; set to 10 when firing
- Return final `(rotation, should_fire)` tuple

### 7. Update agent integration

Update `03_FRAKCJA_AGENTOW/agent_core/agent.py`

- Import `FuzzyTurretController` instead of `SimpleTurretController`
- In `__init__` (around line 32), replace:
  ```python
  self.turret = FuzzyTurretController(
      max_barrel_spin_rate=tank_capabilities.get("_barrel_spin_rate", 90.0),
      vision_range=tank_capabilities.get("_vision_range", 70.0),
      aim_threshold=2.5
  )
  ```
- Pass tank capabilities from `my_tank_status` (available on first tick)
- No changes needed to `get_action` turret call site (same interface)

### 8. Add configuration and tuning parameters

- Create constants in `fuzzy_turret.py`:
  - `THREAT_WEIGHTS = {"LIGHT": 3, "HEAVY": 7, "Sniper": 9}` (tank type mapping)
  - `OPTIMAL_ENGAGEMENT_RANGE = 50.0` (units, for firing decision)
  - `COOLDOWN_TICKS = 10` (internal firing lockout)
  - `AIMING_THRESHOLD_TIGHT = 2.5` (degrees, for fuzzy "perfect" aim)
- Add docstrings explaining fuzzy variable ranges and rule rationale

### 9. Add dependencies

Update `03_FRAKCJA_AGENTOW/requirements.txt`

- Add `scikit-fuzzy>=0.4.2`
- Add `numpy>=1.21.0` (dependency of scikit-fuzzy, likely already present)

## Verification

### 1. Unit tests

Create `03_FRAKCJA_AGENTOW/tests/test_fuzzy_turret.py`

- Test target selection with multiple enemies (verify closest dangerous enemy chosen over distant weak)
- Test rotation speed scaling (verify fast rotation for large errors, slow for small)
- Test firing logic (verify fires only when aimed well at reasonable distance)
- Test scanning (verify returns to last known enemy direction)
- Mock SeenTank objects with various properties

### 2. Integration test

Run existing agent test suite

- Execute `tests/run_agent_tests.py`
- Verify `test_agent_real_map_survival.py` - should maintain or improve combat effectiveness
- Check logs in `logs/` for firing rate and hit statistics

### 3. Manual testing

Use headless runner

- Run `02_FRAKCJA_SILNIKA/run_agents.py` with fuzzy agent
- Observe turret behavior against different tank types on various maps (open.csv, semi-open.csv)
- Verify smooth tracking, appropriate firing decisions, and scanning when idle

### 4. Performance baseline

Compare with SimpleTurretController

- Run 10 matches on `road_trees.csv` map
- Measure: kill count, accuracy (hits/shots), survival time, wasted ammo
- Fuzzy controller should show improved target prioritization (focus dangerous enemies)

## Decisions

- **Target prioritization**: Distance + threat level (tank type) - chose over simpler distance-only to handle multiple enemy scenarios intelligently
- **Adaptive rotation**: Dynamic speed based on angle error and distance - chose over fixed speeds for smoother tracking and faster acquisition
- **Firing criteria**: Angle error + distance + vulnerability - chose to avoid wasting shots at poor angles or extreme ranges
- **Scanning mode**: Fuzzy adaptive based on last known enemy position - chose over simple sweep to improve re-acquisition speed
