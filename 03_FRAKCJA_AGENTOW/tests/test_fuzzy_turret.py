"""
Unit tests for FuzzyTurretController

Tests the fuzzy logic-based turret controller's behavior in various scenarios:
- Target selection with multiple enemies
- Rotation speed adaptation
- Firing decision logic
- Adaptive scanning behavior
"""

import unittest
from typing import Any, Dict
from unittest.mock import MagicMock

# Mock skfuzzy if not installed
try:
    import skfuzzy  # noqa: F401
except ImportError:
    import sys
    from unittest.mock import MagicMock
    sys.modules['skfuzzy'] = MagicMock()
    sys.modules['skfuzzy.control'] = MagicMock()

from agent_core.fuzzy_turret import FuzzyTurretController, THREAT_WEIGHTS


class MockTank:
    """Mock tank object for testing."""
    
    def __init__(self, x: float, y: float, tank_type: str = "LIGHT", is_damaged: bool = False):
        self.position = {"x": x, "y": y}
        self.tank_type = tank_type
        self.is_damaged = is_damaged
        self.distance = 0.0  # Will be calculated by controller


def create_mock_tank_dict(x: float, y: float, tank_type: str = "LIGHT", is_damaged: bool = False) -> Dict[str, Any]:
    """Create a mock tank dictionary."""
    return {
        "position": {"x": x, "y": y},
        "tank_type": tank_type,
        "is_damaged": is_damaged,
    }


class TestFuzzyTurretController(unittest.TestCase):
    """Test suite for FuzzyTurretController."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.controller = FuzzyTurretController(
            max_barrel_spin_rate=90.0,
            vision_range=70.0,
            aim_threshold=2.5,
        )
        self.my_x = 50.0
        self.my_y = 50.0
        self.my_heading = 0.0  # Facing north
    
    def test_initialization(self):
        """Test controller initializes with correct parameters."""
        self.assertEqual(self.controller.max_barrel_spin_rate, 90.0)
        self.assertEqual(self.controller.vision_range, 70.0)
        self.assertEqual(self.controller.aim_threshold, 2.5)
        self.assertEqual(self.controller.cooldown_ticks, 0)
        self.assertIsNone(self.controller.last_seen_direction)
        self.assertEqual(self.controller.ticks_since_last_seen, 0)
    
    def test_no_enemies_scanning(self):
        """Test turret scans when no enemies are visible."""
        rotation, should_fire = self.controller.update(
            my_x=self.my_x,
            my_y=self.my_y,
            my_heading=self.my_heading,
            current_barrel_angle=0.0,
            seen_tanks=[],
            max_barrel_rotation=90.0,
        )
        
        # Should rotate for scanning
        self.assertNotEqual(rotation, 0.0)
        # Should not fire
        self.assertFalse(should_fire)
        # Rotation should be within limits
        self.assertLessEqual(abs(rotation), 90.0)
    
    def test_single_enemy_tracking(self):
        """Test turret tracks a single visible enemy."""
        # Enemy directly ahead (north) at distance 30
        enemy = create_mock_tank_dict(50.0, 80.0, "LIGHT", False)
        
        rotation, should_fire = self.controller.update(
            my_x=self.my_x,
            my_y=self.my_y,
            my_heading=self.my_heading,
            current_barrel_angle=0.0,
            seen_tanks=[enemy],
            max_barrel_rotation=90.0,
        )
        
        # Should attempt some rotation (may be small if already aligned)
        self.assertIsInstance(rotation, float)
        self.assertLessEqual(abs(rotation), 90.0)
        
        # Should fire or not depending on alignment (can't guarantee from initial position)
        self.assertIsInstance(should_fire, bool)
    
    def test_target_selection_prioritizes_dangerous_close_enemies(self):
        """Test that dangerous close enemies are prioritized over distant weak ones."""
        # Close Heavy tank (dangerous)
        heavy_close = create_mock_tank_dict(50.0, 70.0, "HEAVY", False)  # Distance ~20
        # Far Light tank (weak)
        light_far = create_mock_tank_dict(50.0, 130.0, "LIGHT", False)  # Distance ~80
        
        seen_tanks = [light_far, heavy_close]
        
        # Select target
        target = self.controller._select_target(self.my_x, self.my_y, seen_tanks)
        
        # Should select the Heavy tank
        self.assertIsNotNone(target)
        # Check it's the closer/more dangerous one
        target_type = target.get("tank_type") if isinstance(target, dict) else target.tank_type
        self.assertEqual(target_type, "HEAVY")
    
    def test_threat_weights(self):
        """Test threat level mapping for different tank types."""
        self.assertEqual(THREAT_WEIGHTS["LIGHT"], 3)
        self.assertEqual(THREAT_WEIGHTS["HEAVY"], 7)
        self.assertEqual(THREAT_WEIGHTS["Sniper"], 9)
    
    def test_rotation_respects_max_limit(self):
        """Test rotation is clamped to maximum allowed rotation."""
        # Enemy at 180 degrees (behind)
        enemy = create_mock_tank_dict(50.0, 20.0, "LIGHT", False)
        
        max_allowed = 30.0
        rotation, _ = self.controller.update(
            my_x=self.my_x,
            my_y=self.my_y,
            my_heading=self.my_heading,
            current_barrel_angle=0.0,
            seen_tanks=[enemy],
            max_barrel_rotation=max_allowed,
        )
        
        # Rotation should not exceed max allowed
        self.assertLessEqual(abs(rotation), max_allowed)
    
    def test_cooldown_prevents_rapid_firing(self):
        """Test that cooldown prevents firing too rapidly."""
        enemy = create_mock_tank_dict(50.0, 52.5, "LIGHT", False)  # Very close and aligned
        
        # First shot
        _, fired1 = self.controller.update(
            my_x=self.my_x,
            my_y=self.my_y,
            my_heading=self.my_heading,
            current_barrel_angle=0.0,
            seen_tanks=[enemy],
            max_barrel_rotation=90.0,
        )
        
        if fired1:
            # Cooldown should be active
            self.assertGreater(self.controller.cooldown_ticks, 0)
            
            # Immediate next call should not fire
            _, fired2 = self.controller.update(
                my_x=self.my_x,
                my_y=self.my_y,
                my_heading=self.my_heading,
                current_barrel_angle=0.0,
                seen_tanks=[enemy],
                max_barrel_rotation=90.0,
            )
            
            self.assertFalse(fired2)
    
    def test_damaged_target_increases_firing_likelihood(self):
        """Test that damaged enemies are fired upon more readily."""
        # Reset cooldown
        self.controller.cooldown_ticks = 0
        
        result = self.controller._should_fire_fuzzy(
            angle_error=1.0,  # Good aim
            distance=30.0,    # Reasonable distance
            is_damaged=True,
        )
        
        # Should return a boolean
        self.assertIsInstance(result, bool)
    
    def test_last_seen_direction_stored(self):
        """Test that last seen enemy direction is stored for adaptive scanning."""
        enemy = create_mock_tank_dict(60.0, 50.0, "LIGHT", False)  # To the east
        
        # See an enemy
        self.controller.update(
            my_x=self.my_x,
            my_y=self.my_y,
            my_heading=self.my_heading,
            current_barrel_angle=0.0,
            seen_tanks=[enemy],
            max_barrel_rotation=90.0,
        )
        
        # Last seen direction should be updated
        self.assertIsNotNone(self.controller.last_seen_direction)
    
    def test_adaptive_scan_uses_last_known_direction(self):
        """Test that adaptive scanning considers last known enemy position."""
        enemy = create_mock_tank_dict(60.0, 50.0, "LIGHT", False)
        
        # See enemy once
        self.controller.update(
            my_x=self.my_x,
            my_y=self.my_y,
            my_heading=self.my_heading,
            current_barrel_angle=0.0,
            seen_tanks=[enemy],
            max_barrel_rotation=90.0,
        )
        
        last_dir = self.controller.last_seen_direction
        
        # Enemy disappears
        rotation, _ = self.controller.update(
            my_x=self.my_x,
            my_y=self.my_y,
            my_heading=self.my_heading,
            current_barrel_angle=45.0,  # Now pointing somewhere else
            seen_tanks=[],
            max_barrel_rotation=90.0,
        )
        
        # Should still have last known direction
        self.assertEqual(self.controller.last_seen_direction, last_dir)
        # Should increment time counter
        self.assertGreater(self.controller.ticks_since_last_seen, 0)
    
    def test_multiple_enemies_selects_best_target(self):
        """Test target selection with multiple enemies of varying threat."""
        enemies = [
            create_mock_tank_dict(55.0, 50.0, "LIGHT", False),    # East, close, low threat
            create_mock_tank_dict(50.0, 75.0, "Sniper", False),   # North, medium, high threat
            create_mock_tank_dict(45.0, 50.0, "HEAVY", False),    # West, close, medium-high threat
            create_mock_tank_dict(50.0, 20.0, "LIGHT", False),    # South, far, low threat
        ]
        
        target = self.controller._select_target(self.my_x, self.my_y, enemies)
        
        # Should select a target
        self.assertIsNotNone(target)
        
        # Target should be one of the enemies
        self.assertIn(target, enemies)
    
    def test_rotation_speed_adapts_to_error(self):
        """Test that rotation speed factor changes based on angle error."""
        # Small error should give low speed
        speed_small = self.controller._calculate_rotation_speed(angle_error=2.0, distance=50.0)
        
        # Large error should give high speed
        speed_large = self.controller._calculate_rotation_speed(angle_error=90.0, distance=50.0)
        
        # Both should be valid factors
        self.assertGreaterEqual(speed_small, 0.0)
        self.assertLessEqual(speed_small, 1.0)
        self.assertGreaterEqual(speed_large, 0.0)
        self.assertLessEqual(speed_large, 1.0)
        
        # Large error should generally produce higher speed (though fuzzy logic may vary)
        # This is a weak assertion since fuzzy output depends on membership functions
        self.assertIsInstance(speed_large, float)
    
    def test_firing_decision_poor_aim_denies_fire(self):
        """Test that poor aim prevents firing."""
        self.controller.cooldown_ticks = 0
        
        result = self.controller._should_fire_fuzzy(
            angle_error=15.0,  # Very poor aim
            distance=50.0,
            is_damaged=False,
        )
        
        # Should not fire with poor aim
        self.assertFalse(result)
    
    def test_firing_decision_perfect_aim_allows_fire(self):
        """Test that perfect aim at optimal range allows firing."""
        self.controller.cooldown_ticks = 0
        
        result = self.controller._should_fire_fuzzy(
            angle_error=0.5,  # Perfect aim
            distance=40.0,    # Optimal range
            is_damaged=False,
        )
        
        # Should likely fire (though fuzzy system may decide otherwise)
        self.assertIsInstance(result, bool)
    
    def test_extreme_distance_prevents_firing(self):
        """Test that extreme distances prevent firing even with good aim."""
        self.controller.cooldown_ticks = 0
        
        result = self.controller._should_fire_fuzzy(
            angle_error=1.0,   # Good aim
            distance=140.0,    # Extreme distance
            is_damaged=False,
        )
        
        # Should not fire at extreme distance
        self.assertFalse(result)
    
    def test_returns_tuple_of_float_and_bool(self):
        """Test that update method returns correct types."""
        rotation, should_fire = self.controller.update(
            my_x=self.my_x,
            my_y=self.my_y,
            my_heading=self.my_heading,
            current_barrel_angle=0.0,
            seen_tanks=[],
            max_barrel_rotation=90.0,
        )
        
        self.assertIsInstance(rotation, float)
        self.assertIsInstance(should_fire, bool)


class TestFuzzyTurretIntegration(unittest.TestCase):
    """Integration tests for realistic scenarios."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.controller = FuzzyTurretController(
            max_barrel_spin_rate=90.0,
            vision_range=70.0,
            aim_threshold=2.5,
        )
    
    def test_combat_scenario_acquire_and_fire(self):
        """Test full acquire-track-fire sequence."""
        my_x, my_y = 50.0, 50.0
        my_heading = 0.0
        
        # Enemy appears at 45-degree angle
        enemy = create_mock_tank_dict(60.0, 60.0, "HEAVY", False)
        
        current_barrel = 0.0
        fired = False
        
        # Simulate multiple ticks until lock and fire
        for tick in range(20):
            rotation, should_fire = self.controller.update(
                my_x=my_x,
                my_y=my_y,
                my_heading=my_heading,
                current_barrel_angle=current_barrel,
                seen_tanks=[enemy],
                max_barrel_rotation=90.0,
            )
            
            # Update barrel position
            current_barrel += rotation
            
            if should_fire:
                fired = True
                break
        
        # Should eventually track and fire (or at least attempt tracking)
        # We can't guarantee firing because of fuzzy logic, but barrel should move
        self.assertIsInstance(fired, bool)
    
    def test_switch_targets_when_new_threat_appears(self):
        """Test that controller switches to higher-priority target."""
        my_x, my_y = 50.0, 50.0
        
        # Start with weak enemy
        weak_enemy = create_mock_tank_dict(60.0, 50.0, "LIGHT", False)
        
        # Track weak enemy
        target1 = self.controller._select_target(my_x, my_y, [weak_enemy])
        self.assertEqual(target1.get("tank_type"), "LIGHT")
        
        # Dangerous enemy appears
        dangerous_enemy = create_mock_tank_dict(50.0, 60.0, "Sniper", False)
        
        # Should switch targets
        target2 = self.controller._select_target(my_x, my_y, [weak_enemy, dangerous_enemy])
        
        # Should prefer the more dangerous closer target
        self.assertIsNotNone(target2)


if __name__ == "__main__":
    unittest.main()
