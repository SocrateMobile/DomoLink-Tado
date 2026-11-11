"""Unit tests for QuotaBudget (Phase 1)."""
from unittest.mock import MagicMock
import unittest

from custom_components.domolink_tado.quota_budget import QuotaBudget, QuotaSnapshot


class TestQuotaBudget(unittest.TestCase):
    """Test suite for Tado API Quota & Rate-Limit Budgeting."""

    def setUp(self):
        self.budget = QuotaBudget()

    def test_tier_detection_free(self):
        """Test detection of Free tier (~100 req/day)."""
        snap = QuotaSnapshot(limit=100, remaining=85, reset_in=43200.0, observed_at=1000.0)
        self.budget.update(snap)
        self.assertEqual(self.budget.tier, "FREE")

    def test_tier_detection_assist(self):
        """Test detection of Assist / Auto-Assist tier (~20,000 req/day)."""
        snap = QuotaSnapshot(limit=20000, remaining=19500, reset_in=30000.0, observed_at=1000.0)
        self.budget.update(snap)
        self.assertEqual(self.budget.tier, "ASSIST")

    def test_tier_detection_unknown_when_no_limit(self):
        """Test unknown tier when limit is absent."""
        snap = QuotaSnapshot(limit=None, remaining=400, reset_in=None, observed_at=1000.0)
        self.budget.update(snap)
        self.assertEqual(self.budget.tier, "UNKNOWN")

    def test_manual_tier_override(self):
        """Test manual override of tier."""
        snap = QuotaSnapshot(limit=100, remaining=85, reset_in=43200.0, observed_at=1000.0)
        self.budget.update(snap)
        self.assertEqual(self.budget.tier, "FREE")

        self.budget.set_manual_tier("ASSIST")
        self.assertEqual(self.budget.tier, "ASSIST")

        self.budget.set_manual_tier(None)
        self.assertEqual(self.budget.tier, "FREE")

    def test_poll_interval_assist(self):
        """Test polling interval in Assist tier: 120s active heating, 300s idle, 600s quiet."""
        snap = QuotaSnapshot(limit=20000, remaining=18000, reset_in=50000.0, observed_at=1000.0)
        self.budget.update(snap)

        # Active heating
        self.assertEqual(self.budget.poll_interval(heating_active=True), 120)
        # Idle during day
        self.assertEqual(self.budget.poll_interval(heating_active=False, quiet_hours=False), 300)
        # Idle during night
        self.assertEqual(self.budget.poll_interval(heating_active=False, quiet_hours=True), 600)

    def test_poll_interval_free_smoothing(self):
        """Test that Free tier smoothly spreads remaining quota over time."""
        # 75 remaining calls for polling, 36000 seconds to reset (10 hours)
        # Budget = 75 * 0.75 = 56 calls -> 36000 / 56 ≈ 642s (10.7 min)
        snap = QuotaSnapshot(limit=100, remaining=75, reset_in=36000.0, observed_at=1000.0)
        self.budget.update(snap)

        interval = self.budget.poll_interval(now=1000.0, heating_active=False, quiet_hours=False)
        self.assertGreaterEqual(interval, 600)
        self.assertLessEqual(interval, 700)

    def test_poll_interval_free_critical_fallback(self):
        """Test that if remaining is almost zero in Free tier, interval clamps to 1 hour max."""
        snap = QuotaSnapshot(limit=100, remaining=3, reset_in=20000.0, observed_at=1000.0)
        self.budget.update(snap)

        interval = self.budget.poll_interval(now=1000.0)
        self.assertEqual(interval, 3600)

    def test_can_spend_priorities(self):
        """Test that interactive commands have priority over polls and background tasks."""
        snap = QuotaSnapshot(limit=100, remaining=15, reset_in=20000.0, observed_at=1000.0)
        self.budget.update(snap)

        # Commands can spend as long as remaining >= 1
        self.assertTrue(self.budget.can_spend("command", cost=1))

        # Poll cannot spend if it eats into the 25% command reserve (15 - 1 < 25)
        self.assertFalse(self.budget.can_spend("poll", cost=1))

        # Background tasks cannot spend if remaining <= 30
        self.assertFalse(self.budget.can_spend("background", cost=1))

    def test_ttl_optimizations_free_tier(self):
        """Test TTL optimizations in Free tier (skips weather/geofencing if HA handles them)."""
        snap = QuotaSnapshot(limit=100, remaining=80, reset_in=30000.0, observed_at=1000.0)
        self.budget.update(snap)

        # Discovery is 24h
        self.assertEqual(self.budget.ttl("discovery"), 86400)

        # Weather is None if HA has outdoor weather entity configured
        self.assertIsNone(self.budget.ttl("weather", has_ha_weather=True))
        self.assertEqual(self.budget.ttl("weather", has_ha_weather=False), 21600)

        # Home state is None if HA geofencing is enabled
        self.assertIsNone(self.budget.ttl("home_state", has_ha_geofencing=True))
        self.assertEqual(self.budget.ttl("home_state", has_ha_geofencing=False), 7200)

        # Schedules are never periodically polled in Free tier
        self.assertIsNone(self.budget.ttl("schedule"))


if __name__ == "__main__":
    unittest.main()
