"""Tests for DomoLink-Tado WindowGuard event-driven open-window engine."""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.domolink_tado.const import (
    CONF_AUTO_WINDOW_ENABLED,
    CONF_WINDOW_CLOSE_DELAY,
    CONF_WINDOW_MAX_DURATION,
    CONF_WINDOW_OPEN_DELAY,
    CONF_WINDOW_RESTORE_MODE,
    CONF_ZONE_CONTACT_ENTITIES,
    CONF_ZONE_TEMP_ENTITIES,
    OVERLAY_TIMER,
    WINDOW_RESTORE_PREVIOUS,
    WINDOW_RESTORE_RESUME,
)
from custom_components.domolink_tado.quota_budget import QuotaBudget, QuotaSnapshot
from custom_components.domolink_tado.window_guard import WindowEpisode, WindowGuard
from custom_components.domolink_tado.binary_sensor import DomolinkTadoZoneWindowGuardBinarySensor


class DummyState:
    def __init__(self, state: str):
        self.state = state


class DummyStore:
    def __init__(self, initial_data=None):
        self.saved_data = initial_data

    async def async_load(self):
        return self.saved_data

    async def async_save(self, data):
        self.saved_data = data


class TestWindowGuard(unittest.IsolatedAsyncioTestCase):
    """Test suite for WindowGuard."""

    def setUp(self):
        self.hass = MagicMock()
        self.hass.bus = MagicMock()
        self.hass.bus.async_fire = MagicMock()
        self.hass.states = MagicMock()
        self.hass.states.get = MagicMock(return_value=DummyState("off"))

        def _create_task(coro):
            return asyncio.create_task(coro)

        self.hass.async_create_task = _create_task

        self.coord = MagicMock()
        self.coord.hass = self.hass
        self.coord.home_id = 12345
        self.coord.entry = MagicMock()
        self.coord.entry.options = {
            CONF_AUTO_WINDOW_ENABLED: True,
            CONF_WINDOW_OPEN_DELAY: 0,
            CONF_WINDOW_CLOSE_DELAY: 0,
            CONF_WINDOW_MAX_DURATION: 900,
            CONF_WINDOW_RESTORE_MODE: WINDOW_RESTORE_RESUME,
            CONF_ZONE_CONTACT_ENTITIES: {"1": ["binary_sensor.window_salon"]},
            CONF_ZONE_TEMP_ENTITIES: {"1": "sensor.salon_temp"},
        }
        self.coord.client = MagicMock()
        budget = QuotaBudget()
        budget.update(QuotaSnapshot(100, 100, 3600, time.time()))
        self.coord.client.budget = budget
        self.coord.client.set_zone_overlay = AsyncMock()
        self.coord.async_resume_schedule = AsyncMock()
        self.coord.async_update_listeners = MagicMock()
        self.coord.data = {
            "zones": {
                1: {
                    "name": "Salon",
                    "setting": {"power": "ON", "temperature": {"celsius": 21.0}},
                    "overlay": {"setting": {"power": "ON"}},
                    "heating_power": 80,
                }
            }
        }

    def test_window_episode_serialization(self):
        """Test WindowEpisode to_dict and from_dict."""
        ep = WindowEpisode(
            zone_id=1,
            started_at=1000.0,
            reason="contact",
            previous_overlay={"setting": {"power": "ON"}},
            we_own_overlay=True,
        )
        d = ep.to_dict()
        self.assertEqual(d["zone_id"], 1)
        self.assertEqual(d["reason"], "contact")
        self.assertTrue(d["we_own_overlay"])

        ep2 = WindowEpisode.from_dict(d)
        self.assertEqual(ep2.zone_id, 1)
        self.assertEqual(ep2.started_at, 1000.0)
        self.assertEqual(ep2.reason, "contact")
        self.assertEqual(ep2.previous_overlay, {"setting": {"power": "ON"}})
        self.assertTrue(ep2.we_own_overlay)

    async def test_window_guard_setup_and_store_load(self):
        """Test async_setup loads episodes from Store and subscribes."""
        store = DummyStore({
            "1": {
                "zone_id": 1,
                "started_at": 500.0,
                "reason": "contact",
                "previous_overlay": None,
                "we_own_overlay": True,
            }
        })
        guard = WindowGuard(self.hass, self.coord, store)
        await guard.async_setup()

        self.assertTrue(guard.is_window_open(1))
        ep = guard.get_episode(1)
        self.assertIsNotNone(ep)
        self.assertEqual(ep.zone_id, 1)
        self.assertGreater(len(guard._unsub_listeners), 0)

        guard.async_unload()
        self.assertEqual(len(guard._unsub_listeners), 0)

    async def test_window_guard_cut_when_heating(self):
        """Test _cut shuts down zone with TIMER overlay when heating is active."""
        guard = WindowGuard(self.hass, self.coord)
        await guard.async_setup()

        await guard._cut(1, "contact")

        self.coord.client.set_zone_overlay.assert_awaited_once_with(
            home_id=12345,
            zone_id=1,
            power="OFF",
            termination_type=OVERLAY_TIMER,
            duration_seconds=900,
        )
        self.assertTrue(guard.is_window_open(1))
        ep = guard.get_episode(1)
        self.assertTrue(ep.we_own_overlay)
        self.assertEqual(ep.reason, "contact")

        self.hass.bus.async_fire.assert_called_with(
            "domolink_tado_window_opened", {"zone_id": 1, "reason": "contact"}
        )

    async def test_window_guard_cut_when_already_off_skips_api(self):
        """Test _cut skips API call if the zone is already OFF (saving quota)."""
        self.coord.data["zones"][1]["setting"] = {"power": "OFF"}

        guard = WindowGuard(self.hass, self.coord)
        await guard.async_setup()

        await guard._cut(1, "contact")

        self.coord.client.set_zone_overlay.assert_not_called()
        self.assertTrue(guard.is_window_open(1))
        ep = guard.get_episode(1)
        self.assertFalse(ep.we_own_overlay)

    async def test_window_guard_restore_resume(self):
        """Test _restore calls resume_schedule when we own overlay and user hasn't overridden."""
        guard = WindowGuard(self.hass, self.coord)
        await guard.async_setup()

        await guard._cut(1, "contact")
        self.assertTrue(guard.is_window_open(1))

        await guard._restore(1)

        self.coord.async_resume_schedule.assert_awaited_once_with(1)
        self.assertFalse(guard.is_window_open(1))

        self.hass.bus.async_fire.assert_called_with(
            "domolink_tado_window_closed", {"zone_id": 1, "restored": True}
        )

    async def test_window_guard_restore_user_override_protection(self):
        """Test _restore aborts and does NOT overwrite if user manually turned heating ON during ventilation."""
        guard = WindowGuard(self.hass, self.coord)
        await guard.async_setup()

        await guard._cut(1, "contact")
        self.assertTrue(guard.is_window_open(1))

        # User manually changed temperature / turned zone back ON
        self.coord.data["zones"][1]["setting"] = {"power": "ON", "temperature": {"celsius": 22.0}}

        await guard._restore(1)

        self.coord.async_resume_schedule.assert_not_called()
        self.assertFalse(guard.is_window_open(1))

        self.hass.bus.async_fire.assert_called_with(
            "domolink_tado_window_closed", {"zone_id": 1, "aborted_user_override": True}
        )

    async def test_window_guard_restore_previous_mode(self):
        """Test _restore re-applies previous overlay when mode is RESTORE_PREVIOUS."""
        self.coord.entry.options[CONF_WINDOW_RESTORE_MODE] = WINDOW_RESTORE_PREVIOUS

        guard = WindowGuard(self.hass, self.coord)
        await guard.async_setup()

        await guard._cut(1, "contact")
        await guard._restore(1)

        self.coord.client.set_zone_overlay.assert_awaited_with(
            home_id=12345,
            zone_id=1,
            power="ON",
            temperature=None,
        )
        self.assertFalse(guard.is_window_open(1))

    async def test_window_guard_native_tado_fallback(self):
        """Test coordinator native openWindow detection integration."""
        guard = WindowGuard(self.hass, self.coord)
        await guard.async_setup()

        guard.on_tado_native_detected(1, True)
        await asyncio.sleep(0.01)

        self.assertTrue(guard.is_window_open(1))
        self.assertEqual(guard.get_episode(1).reason, "tado_native")

        guard.on_tado_native_detected(1, False)
        await asyncio.sleep(0.01)

        self.assertFalse(guard.is_window_open(1))

    def test_window_guard_binary_sensor(self):
        """Test DomolinkTadoZoneWindowGuardBinarySensor reflects WindowGuard state."""
        guard = WindowGuard(self.hass, self.coord)
        self.coord.window_guard = guard

        sensor = DomolinkTadoZoneWindowGuardBinarySensor(self.coord, 1)
        self.assertFalse(sensor.is_on)

        guard._episodes[1] = WindowEpisode(
            zone_id=1,
            started_at=1234.0,
            reason="contact",
            previous_overlay=None,
            we_own_overlay=True,
        )

        self.assertTrue(sensor.is_on)
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["reason"], "contact")
        self.assertEqual(attrs["started_at"], 1234.0)
        self.assertTrue(attrs["we_own_overlay"])
