"""Unit tests for Tado v10.9 microservices (GraphQL, Ivar, Minder, Hops) and Local Bridge Bypass."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

from custom_components.domolink_tado.const import (
    TADO_GRAPHQL_FALLBACK_URL,
    TADO_GRAPHQL_URL,
    TADO_IVAR_FALLBACK_URL,
    TADO_IVAR_GRAPHQL_URL,
    TADO_MINDER_API_URL,
    TADO_HOPS_API_URL,
)
from custom_components.domolink_tado.local_bridge import LocalBridgeManager
from custom_components.domolink_tado.quota_budget import QuotaBudget, QuotaSnapshot
from custom_components.domolink_tado.tado_api import TadoClient, TadoError, TadoRateLimitError
from custom_components.domolink_tado.button import (
    DomolinkTadoIdentifyDeviceButton,
    DomolinkTadoRebootDeviceButton,
)
from custom_components.domolink_tado.switch import DomolinkTadoDeviceDazzleSwitch
from custom_components.domolink_tado.binary_sensor import (
    DomolinkTadoBoilerIncidentBinarySensor,
    DomolinkTadoDeviceBadSignalBinarySensor,
    DomolinkTadoLocalBridgeActiveBinarySensor,
    DomolinkTadoZoneMoldRiskProblemBinarySensor,
)
from custom_components.domolink_tado.sensor import (
    DomolinkTadoBurnerRunningTimeSensor,
    DomolinkTadoEnergySavingsSensor,
    DomolinkTadoHeatPumpCopSensor,
)


class TestTadoMicroservices(unittest.IsolatedAsyncioTestCase):
    """Test suite for Tado v10.9 microservices integration."""

    async def asyncSetUp(self) -> None:
        self.session = MagicMock()
        self.client = TadoClient(self.session, access_token="test_token")
        self.client.async_get_valid_token = AsyncMock(return_value="test_valid_token")

    async def test_graphql_request_success(self) -> None:
        """Test standard GraphQL query execution."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"ratelimit": "r=95;t=3600", "ratelimit-policy": "100;w=86400"}
        mock_resp.json = AsyncMock(return_value={
            "data": {
                "home": {
                    "devices": {
                        "all": [
                            {"id": "12345", "serialNumber": "VA001", "dazzleEnabled": True, "supportsIdentify": True}
                        ]
                    }
                }
            }
        })

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_resp
        self.session.request.return_value = mock_cm

        devices = await self.client.get_graphql_devices(1234)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["serialNumber"], "VA001")
        self.assertTrue(devices[0]["dazzleEnabled"])
        self.assertTrue(devices[0]["supportsIdentify"])

    async def test_graphql_fallback_on_primary_failure(self) -> None:
        """Test automatic fallback from ext.api.tado.com to app.tado.com/api/..."""
        fail_resp = MagicMock()
        fail_resp.status = 404
        fail_cm = AsyncMock()
        fail_cm.__aenter__.return_value = fail_resp

        success_resp = MagicMock()
        success_resp.status = 200
        success_resp.headers = {}
        success_resp.json = AsyncMock(return_value={
            "data": {"identifyDevice": {"success": True, "failureReason": None}}
        })
        success_cm = AsyncMock()
        success_cm.__aenter__.return_value = success_resp

        self.session.request.side_effect = [fail_cm, success_cm]

        result = await self.client.identify_device("12345")
        self.assertTrue(result.get("success"))
        self.assertEqual(self.session.request.call_count, 2)

    async def test_reboot_device_mutation(self) -> None:
        """Test RebootDevice mutation."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {}
        mock_resp.json = AsyncMock(return_value={
            "data": {"rebootDevice": {"success": True, "failureReason": None}}
        })
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_resp
        self.session.request.return_value = mock_cm

        res = await self.client.reboot_device("12345")
        self.assertTrue(res.get("success"))

    async def test_set_device_dazzle_mutation(self) -> None:
        """Test SetDeviceDazzleEnabled mutation."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {}
        mock_resp.json = AsyncMock(return_value={
            "data": {"setDeviceDazzleEnabled": {"success": True, "failureReason": None}}
        })
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_resp
        self.session.request.return_value = mock_cm

        res = await self.client.set_device_dazzle("12345", True)
        self.assertTrue(res.get("success"))

    async def test_minder_boiler_incidents_and_running_times(self) -> None:
        """Test minder.tado.com incidents and running times retrieval."""
        mock_incidents = MagicMock()
        mock_incidents.status = 200
        mock_incidents.headers = {}
        mock_incidents.json = AsyncMock(return_value=[
            {"id": "inc_1", "type": "WATER_PRESSURE_LOW", "title": "Pression basse"}
        ])
        cm_inc = AsyncMock()
        cm_inc.__aenter__.return_value = mock_incidents

        self.session.request.return_value = cm_inc
        incidents = await self.client.get_boiler_incidents(1234)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["id"], "inc_1")

        # Test tolerance on 404
        mock_404 = MagicMock()
        mock_404.status = 404
        cm_404 = AsyncMock()
        cm_404.__aenter__.return_value = mock_404
        self.session.request.return_value = cm_404
        empty_incidents = await self.client.get_boiler_incidents(1234)
        self.assertEqual(empty_incidents, [])

    async def test_energy_insights_and_cop(self) -> None:
        """Test unified GraphQL query for energy savings and heat pump COP."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {}
        mock_resp.json = AsyncMock(return_value={
            "data": {
                "home": {
                    "energySavings": {
                        "totalSavings": {"percentage": 24.5},
                        "openWindowDetectionTimes": 12,
                        "sunshineDuration": {"duration": 7200},
                        "awayDuration": {"duration": 14400},
                        "manualControlSaving": {"percentage": 5.2},
                        "hasAutoAssist": True,
                    },
                    "heatPump": {
                        "consumption": {
                            "cop": {"heating": 3.8, "domesticHotWater": 2.9}
                        }
                    },
                    "notifications": [
                        {"id": "notif_1", "type": "MOLD_INDEX", "roomIds": [1, 2]}
                    ]
                }
            }
        })
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_resp
        self.session.request.return_value = cm

        res = await self.client.get_energy_insights(1234, "2026-11")
        self.assertEqual(res["energySavings"]["totalSavings"]["percentage"], 24.5)
        self.assertEqual(res["heatPump"]["consumption"]["cop"]["heating"], 3.8)
        self.assertEqual(len(res["notifications"]), 1)

    async def test_matter_provisioning_codes(self) -> None:
        """Test retrieval of secret Matter pairing passcode & discriminator."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {}
        mock_resp.json = AsyncMock(return_value={
            "data": {
                "home": {
                    "device": {
                        "matterProvisioningData": {
                            "passcode": 20202021,
                            "discriminator": 3840
                        }
                    }
                }
            }
        })
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_resp
        self.session.request.return_value = cm

        data = await self.client.get_matter_provisioning(1234, "dev_99")
        self.assertEqual(data["passcode"], 20202021)
        self.assertEqual(data["discriminator"], 3840)

    async def test_quota_budget_respect_on_microservices(self) -> None:
        """Test that QuotaBudget protects background calls when quota is low."""
        budget = QuotaBudget()
        # Free tier with 20 calls remaining (below background threshold of 30)
        budget.update(QuotaSnapshot(limit=100, remaining=20, reset_in=3600, observed_at=1000.0))
        self.assertFalse(budget.can_spend("background"))
        # But commands (IdentifyDevice, RebootDevice) are always allowed
        self.assertTrue(budget.can_spend("command"))


class TestLocalBridgeManager(unittest.IsolatedAsyncioTestCase):
    """Test suite for Local Bridge Bypass & Auto-pairing."""

    async def test_local_bridge_discovery_and_commands(self) -> None:
        hass = MagicMock(spec=["states", "services", "config_entries", "data"])
        coordinator = MagicMock()
        coordinator.data = {
            "zones": {1: {"name": "Salon", "id": 1}},
            "devices": {"VA123": {"serialNo": "VA123", "zoneId": 1}}
        }

        # Mock HA climate entities (including own domolink_tado entity that MUST be ignored)
        state_own = MagicMock()
        state_own.entity_id = "climate.salon_tado"
        state_own.state = "heat"
        state_own.attributes = {"friendly_name": "Salon", "integration": "domolink_tado"}

        state_salon = MagicMock()
        state_salon.entity_id = "climate.salon_homekit"
        state_salon.state = "heat"
        state_salon.attributes = {"friendly_name": "Salon"}
        hass.states.async_all.return_value = [state_own, state_salon]
        hass.states.get.return_value = state_salon

        lbm = LocalBridgeManager(hass, coordinator)
        mapped = lbm.discover_local_entities()
        self.assertEqual(mapped.get(1), "climate.salon_homekit")
        self.assertTrue(lbm.has_local_entities)

        # Test local temperature command bypasses cloud
        hass.services.async_call = AsyncMock()
        ok = await lbm.async_set_temperature_local(1, 21.5)
        self.assertTrue(ok)
        hass.services.async_call.assert_called_once_with(
            "climate", "set_temperature", {"entity_id": "climate.salon_homekit", "temperature": 21.5}, blocking=True
        )

        # Test local turn off (WindowGuard)
        hass.services.async_call.reset_mock()
        ok_off = await lbm.async_turn_off_local(1)
        self.assertTrue(ok_off)
        hass.services.async_call.assert_called_once_with(
            "climate", "set_hvac_mode", {"entity_id": "climate.salon_homekit", "hvac_mode": "off"}, blocking=True
        )


class TestNewEntities(unittest.TestCase):
    """Test suite for new Button, Switch, BinarySensor, and Sensor entities."""

    def setUp(self) -> None:
        self.coordinator = MagicMock()
        self.coordinator.home_id = 1234
        self.coordinator.formatted_home_name = "Tado Test Home"
        self.coordinator.data = {
            "devices": {
                "VA001": {
                    "serialNo": "VA001",
                    "deviceType": "VA02",
                    "dazzleEnabled": True,
                    "hasBadSignal": True,
                    "supportsIdentify": True,
                }
            },
            "boiler_care": {
                "boiler_present": True,
                "boiler_model": "Vaillant ecoTEC",
                "has_active_incident": True,
                "incidents": [{"id": "1"}],
                "daily_running_hours": 3.5,
                "daily_running_seconds": 12600,
            },
            "energy_insights": {
                "total_savings_percentage": 22.0,
                "open_window_detections": 5,
                "sunshine_duration_hours": 4.5,
                "away_duration_hours": 10.0,
                "cop_heating": 4.1,
                "cop_dhw": 3.0,
                "mold_risk_room_ids": [1],
            },
            "local_bridge_active": True,
            "local_bridge_zones": {1: "climate.salon_homekit"},
            "zones": {1: {"name": "Salon", "mold_risk_problem": False}}
        }

    def test_buttons(self) -> None:
        btn_ident = DomolinkTadoIdentifyDeviceButton(self.coordinator, "VA001")
        self.assertIn("VA001", btn_ident.name)
        btn_reboot = DomolinkTadoRebootDeviceButton(self.coordinator, "VA001")
        self.assertIn("Redémarrer", btn_reboot.name)

    def test_switch_dazzle(self) -> None:
        sw = DomolinkTadoDeviceDazzleSwitch(self.coordinator, "VA001")
        self.assertTrue(sw.is_on)

    def test_binary_sensors(self) -> None:
        bs_sig = DomolinkTadoDeviceBadSignalBinarySensor(self.coordinator, "VA001")
        self.assertTrue(bs_sig.is_on)

        bs_care = DomolinkTadoBoilerIncidentBinarySensor(self.coordinator)
        self.assertTrue(bs_care.is_on)
        self.assertEqual(bs_care.extra_state_attributes["boiler_model"], "Vaillant ecoTEC")

        bs_lan = DomolinkTadoLocalBridgeActiveBinarySensor(self.coordinator)
        self.assertTrue(bs_lan.is_on)

        bs_mold = DomolinkTadoZoneMoldRiskProblemBinarySensor(self.coordinator, 1)
        # Should be on because room 1 is in mold_risk_room_ids
        self.assertTrue(bs_mold.is_on)

    def test_sensors(self) -> None:
        s_burn = DomolinkTadoBurnerRunningTimeSensor(self.coordinator)
        self.assertEqual(s_burn.native_value, 3.5)

        s_sav = DomolinkTadoEnergySavingsSensor(self.coordinator)
        self.assertEqual(s_sav.native_value, 22.0)

        s_cop = DomolinkTadoHeatPumpCopSensor(self.coordinator)
        self.assertEqual(s_cop.native_value, 4.1)


if __name__ == "__main__":
    unittest.main()
