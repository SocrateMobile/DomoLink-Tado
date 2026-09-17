"""Unit tests for DomoLink-Tado coordinator and API client fixes."""
import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

if "aiohttp" not in sys.modules:
    aiohttp_mock = types.ModuleType("aiohttp")
    aiohttp_mock.__path__ = []
    class ClientError(Exception): pass
    aiohttp_mock.ClientError = ClientError
    aiohttp_mock.ClientSession = MagicMock
    aiohttp_mock.ClientResponse = MagicMock
    sys.modules["aiohttp"] = aiohttp_mock

if "voluptuous" not in sys.modules:
    vol_mock = types.ModuleType("voluptuous")
    vol_mock.__path__ = []
    vol_mock.Schema = lambda s: s
    vol_mock.Optional = lambda k, **kw: k
    vol_mock.Required = lambda k, **kw: k
    vol_mock.In = lambda vals: vals
    vol_mock.All = lambda *args: args[0]
    vol_mock.Coerce = lambda t: t
    vol_mock.Range = lambda **kw: kw
    sys.modules["voluptuous"] = vol_mock

if "homeassistant" not in sys.modules:
    def make_pkg(name):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
        return mod

    ha = make_pkg("homeassistant")
    ha_const = make_pkg("homeassistant.const")
    class Platform:
        CLIMATE = "climate"
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        SWITCH = "switch"
        UPDATE = "update"
    ha_const.Platform = Platform
    ha_const.PERCENTAGE = "%"
    class UnitOfTemperature:
        CELSIUS = "°C"
    ha_const.UnitOfTemperature = UnitOfTemperature

    ha_sensor = make_pkg("homeassistant.components.sensor")
    class SensorEntity: pass
    class SensorDeviceClass:
        TEMPERATURE = "temperature"
        HUMIDITY = "humidity"
        ENUM = "enum"
    class SensorStateClass:
        MEASUREMENT = "measurement"
    ha_sensor.SensorEntity = SensorEntity
    ha_sensor.SensorDeviceClass = SensorDeviceClass
    ha_sensor.SensorStateClass = SensorStateClass

    ha_bsensor = make_pkg("homeassistant.components.binary_sensor")
    class BinarySensorEntity: pass
    class BinarySensorDeviceClass:
        PRESENCE = "presence"
        WINDOW = "window"
        HEAT = "heat"
        BATTERY = "battery"
        CONNECTIVITY = "connectivity"
        PROBLEM = "problem"
    ha_bsensor.BinarySensorEntity = BinarySensorEntity
    ha_bsensor.BinarySensorDeviceClass = BinarySensorDeviceClass

    ha_comp = make_pkg("homeassistant.components")
    ha_comp.frontend = MagicMock()
    sys.modules["homeassistant.components.frontend"] = ha_comp.frontend
    ha_http = make_pkg("homeassistant.components.http")
    ha_http.StaticPathConfig = MagicMock()
    sys.modules["homeassistant.components.http"] = ha_http

    ha_entries = make_pkg("homeassistant.config_entries")
    class ConfigEntry: pass
    class OptionsFlow: pass
    class ConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            pass
        async def async_set_unique_id(self, uid): pass
        def _abort_if_unique_id_configured(self): pass
        def async_create_entry(self, **kwargs): return {"type": "create_entry", **kwargs}
        def async_show_form(self, **kwargs): return {"type": "form", **kwargs}
        def async_abort(self, **kwargs): return {"type": "abort", **kwargs}
    ha_entries.ConfigEntry = ConfigEntry
    ha_entries.OptionsFlow = OptionsFlow
    ha_entries.ConfigFlow = ConfigFlow

    ha_core = make_pkg("homeassistant.core")
    ha_core.HomeAssistant = MagicMock
    ha_core.ServiceCall = MagicMock
    ha_core.callback = lambda f: f

    ha_exc = make_pkg("homeassistant.exceptions")
    class ConfigEntryAuthFailed(Exception): pass
    class UpdateFailed(Exception): pass
    class ConfigEntryNotReady(Exception): pass
    ha_exc.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    ha_exc.UpdateFailed = UpdateFailed
    ha_exc.ConfigEntryNotReady = ConfigEntryNotReady

    ha_helpers = make_pkg("homeassistant.helpers")
    ha_ent = make_pkg("homeassistant.helpers.entity")
    class DeviceInfo(dict): pass
    ha_ent.DeviceInfo = DeviceInfo
    ha_ent_plat = make_pkg("homeassistant.helpers.entity_platform")
    ha_ent_plat.AddEntitiesCallback = MagicMock

    ha_coord = make_pkg("homeassistant.helpers.update_coordinator")
    class DataUpdateCoordinator:
        def __init__(self, hass, logger, name, update_interval):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = {}
        def async_set_updated_data(self, data):
            self.data = data
        def __class_getitem__(cls, item):
            return cls

    class CoordinatorEntity:
        def __init__(self, coordinator, *args, **kwargs):
            self.coordinator = coordinator
        def __class_getitem__(cls, item):
            return cls

    ha_coord.DataUpdateCoordinator = DataUpdateCoordinator
    ha_coord.CoordinatorEntity = CoordinatorEntity
    ha_coord.UpdateFailed = UpdateFailed

    ha_aiohttp = make_pkg("homeassistant.helpers.aiohttp_client")
    ha_aiohttp.async_get_clientsession = MagicMock()

    ha_flow = make_pkg("homeassistant.data_entry_flow")
    class AbortFlow(Exception): pass
    ha_flow.AbortFlow = AbortFlow
    ha_flow.FlowResult = dict

from custom_components.domolink_tado.tado_api import TadoClient, TadoError
from custom_components.domolink_tado.coordinator import DomolinkTadoCoordinator
from custom_components.domolink_tado.config_flow import DomolinkTadoConfigFlow
from custom_components.domolink_tado.physics import (
    calculate_dew_point,
    calculate_absolute_humidity,
    calculate_mold_risk_level,
    calculate_mold_risk_problem,
    calculate_ventilation_recommended,
)
from custom_components.domolink_tado.sensor import (
    DomolinkTadoZoneDewPointSensor,
    DomolinkTadoZoneAbsoluteHumiditySensor,
    DomolinkTadoZoneMoldRiskSensor,
    DomolinkTadoOutdoorHumiditySensor,
)
from custom_components.domolink_tado.binary_sensor import (
    DomolinkTadoZoneMoldRiskProblemBinarySensor,
    DomolinkTadoZoneVentilationRecommendedBinarySensor,
)


class TestTadoApiRateLimit(unittest.TestCase):
    """Test rate limit delay calculation and backoff."""

    def test_calculate_rate_limit_delay_with_retry_after(self):
        resp = MagicMock()
        resp.headers = {"Retry-After": "14.5"}
        delay = TadoClient._calculate_rate_limit_delay(resp, attempt=0)
        self.assertEqual(delay, 14.5)

    def test_calculate_rate_limit_delay_with_ratelimit_reset(self):
        resp = MagicMock()
        resp.headers = {"RateLimit-Reset": "7.0"}
        delay = TadoClient._calculate_rate_limit_delay(resp, attempt=1)
        self.assertEqual(delay, 7.0)

    def test_calculate_rate_limit_delay_with_tado_ratelimit_header(self):
        resp = MagicMock()
        resp.headers = {"ratelimit": '"perday";r=0;t=18.5'}
        delay = TadoClient._calculate_rate_limit_delay(resp, attempt=0)
        self.assertEqual(delay, 18.5)

        resp.headers = {"ratelimit": '"perday";r=0;t=86400'}
        delay_capped = TadoClient._calculate_rate_limit_delay(resp, attempt=0)
        self.assertEqual(delay_capped, 30.0)

        delay_uncapped = TadoClient._calculate_rate_limit_delay(resp, attempt=0, max_delay=100000.0)
        self.assertEqual(delay_uncapped, 86400.0)

    def test_client_headers_contain_referer_and_user_agent(self):
        from custom_components.domolink_tado.tado_api import DEFAULT_REFERER, DEFAULT_USER_AGENT
        self.assertEqual(DEFAULT_REFERER, "https://app.tado.com/")
        self.assertEqual(DEFAULT_USER_AGENT, "PyTado/0.18.16")

    def test_calculate_rate_limit_delay_fallback_exponential(self):
        resp = MagicMock()
        resp.headers = {}
        delay0 = TadoClient._calculate_rate_limit_delay(resp, attempt=0, default_base=2.5)
        self.assertEqual(delay0, 2.5)

        delay2 = TadoClient._calculate_rate_limit_delay(resp, attempt=2, default_base=2.5)
        self.assertEqual(delay2, 10.0)

        delay_capped = TadoClient._calculate_rate_limit_delay(resp, attempt=5, default_base=2.5, max_delay=30.0)
        self.assertEqual(delay_capped, 30.0)


class TestCoordinatorFixes(unittest.IsolatedAsyncioTestCase):
    """Test coordinator exception handling, optimistic rollback, and window handling."""

    def setUp(self):
        self.hass = MagicMock()
        self.entry = MagicMock()
        self.entry.options = {}
        self.client = MagicMock(spec=TadoClient)
        self.coordinator = DomolinkTadoCoordinator(
            hass=self.hass,
            entry=self.entry,
            client=self.client,
            home_id=12345,
            home_name="Test Home",
        )
        self.coordinator.data = {
            "home_id": 12345,
            "zones": {
                1: {
                    "zone_id": 1,
                    "target_temperature": 19.0,
                    "power": "ON",
                    "is_overlay_active": False,
                }
            }
        }

    async def test_optimistic_zone_update_success(self):
        """Test optimistic update stays applied on API success."""
        api_coro = AsyncMock()()

        patch_data = {"target_temperature": 21.5, "power": "ON", "is_overlay_active": True}
        await self.coordinator._async_optimistic_zone_update(1, patch_data, api_coro)

        self.assertEqual(self.coordinator.data["zones"][1]["target_temperature"], 21.5)
        self.assertTrue(self.coordinator.data["zones"][1]["is_overlay_active"])

    async def test_optimistic_zone_update_rollback_on_failure(self):
        """Test optimistic update is rolled back if API call fails."""
        async def failing_call():
            raise TadoError("Network timeout")

        patch_data = {"target_temperature": 22.0, "power": "ON", "is_overlay_active": True}
        with self.assertRaises(TadoError):
            await self.coordinator._async_optimistic_zone_update(1, patch_data, failing_call())

        # Target temperature rolled back to initial 19.0
        self.assertEqual(self.coordinator.data["zones"][1]["target_temperature"], 19.0)
        self.assertFalse(self.coordinator.data["zones"][1]["is_overlay_active"])

    async def test_open_window_handler_success(self):
        """Test open window marks handled on success."""
        self.client.set_zone_overlay = AsyncMock()
        await self.coordinator._async_handle_open_window(1, "Salon", 900)

        self.assertTrue(self.coordinator._open_window_handled[1])
        self.assertNotIn(1, self.coordinator._open_window_pending)

    async def test_open_window_handler_failure_resets_handled(self):
        """Test open window resets handled flag to False on API failure so it will retry."""
        self.client.set_zone_overlay = AsyncMock(side_effect=TadoError("API 500"))
        await self.coordinator._async_handle_open_window(1, "Salon", 900)

        self.assertFalse(self.coordinator._open_window_handled[1])
        self.assertNotIn(1, self.coordinator._open_window_pending)

    async def test_batch_execute_all_zones_concurrency(self):
        """Test batch execution across all zones with concurrency."""
        self.coordinator.data["zones"][2] = {
            "zone_id": 2,
            "target_temperature": 18.0,
            "power": "OFF",
            "is_overlay_active": False,
        }

        call_records = []
        async def mock_call(zid):
            call_records.append(zid)

        await self.coordinator._async_execute_all_zones(
            action_name="test boost",
            optimistic_patch={"target_temperature": 25.0, "power": "ON", "is_overlay_active": True},
            call_fn=mock_call,
            concurrency=2,
        )

        self.assertEqual(set(call_records), {1, 2})
        self.assertEqual(self.coordinator.data["zones"][1]["target_temperature"], 25.0)
        self.assertEqual(self.coordinator.data["zones"][2]["target_temperature"], 25.0)


class TestConfigFlowAndTokenParsing(unittest.IsolatedAsyncioTestCase):
    """Test robust token polling and config flow entry creation."""

    async def test_poll_device_token_null_expires_in(self):
        """Test poll_device_token does not crash when expires_in is None."""
        session = MagicMock()
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={
            "access_token": "secret_token",
            "refresh_token": "refresh_secret",
            "expires_in": None,
        })
        session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=resp)))

        res = await TadoClient.poll_device_token(session, "test_code")
        self.assertEqual(res["access_token"], "secret_token")
        self.assertIsNotNone(res["expires_at"])

    async def test_poll_device_token_missing_access_token(self):
        """Test poll_device_token raises TadoAuthError if access_token is missing."""
        from custom_components.domolink_tado.tado_api import TadoAuthError
        session = MagicMock()
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"refresh_token": "r"})
        session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=resp)))

        with self.assertRaises(TadoAuthError):
            await TadoClient.poll_device_token(session, "test_code")

    async def test_manual_home_valid(self):
        """Test step_manual_home successfully creates entry with supplied home_id."""
        flow = DomolinkTadoConfigFlow()
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow._tokens = {
            "access_token": "acc_token",
            "refresh_token": "ref_token",
            "expires_at": 1234567,
        }

        res = await flow.async_step_manual_home({"home_id": 98765, "home_name": "Maison Test"})
        self.assertEqual(res["type"], "create_entry")
        self.assertEqual(res["title"], "DomoLink Tado (Maison Test)")
        self.assertEqual(res["data"]["home_id"], 98765)
        self.assertEqual(res["data"]["home_name"], "Maison Test")
        self.assertEqual(res["data"]["access_token"], "acc_token")

    async def test_manual_home_invalid_id(self):
        """Test step_manual_home shows form with invalid_home_id error when ID is not an integer."""
        flow = DomolinkTadoConfigFlow()
        flow.hass = MagicMock()
        flow._tokens = {"access_token": "acc_token"}

        res = await flow.async_step_manual_home({"home_id": "not-a-number"})
        self.assertEqual(res["type"], "form")
        self.assertEqual(res["errors"]["base"], "invalid_home_id")


class TestOverlayPayload(unittest.IsolatedAsyncioTestCase):
    """Test set_zone_overlay payload generation complies with Tado API."""

    async def test_overlay_next_time_block(self):
        client = TadoClient("test_token")
        client._request = AsyncMock(return_value={})

        await client.set_zone_overlay(
            home_id=631338,
            zone_id=36,
            target_temp=21.0,
            power="ON",
            termination_type="NEXT_TIME_BLOCK",
        )

        client._request.assert_called_once()
        method, endpoint = client._request.call_args[0]
        payload = client._request.call_args[1]["json_data"]

        self.assertEqual(method, "PUT")
        self.assertEqual(endpoint, "/homes/631338/zones/36/overlay")
        self.assertEqual(payload["setting"]["power"], "ON")
        self.assertEqual(payload["setting"]["temperature"]["celsius"], 21.0)
        self.assertEqual(payload["termination"]["typeSkillBasedApp"], "NEXT_TIME_BLOCK")
        self.assertNotIn("type", payload["termination"])

    async def test_overlay_manual(self):
        client = TadoClient("test_token")
        client._request = AsyncMock(return_value={})

        await client.set_zone_overlay(
            home_id=631338,
            zone_id=36,
            power="OFF",
            termination_type="MANUAL",
        )

        payload = client._request.call_args[1]["json_data"]
        self.assertEqual(payload["setting"]["power"], "OFF")
        self.assertEqual(payload["termination"]["typeSkillBasedApp"], "MANUAL")
        self.assertNotIn("temperature", payload["setting"])

    async def test_overlay_timer(self):
        client = TadoClient("test_token")
        client._request = AsyncMock(return_value={})

        await client.set_zone_overlay(
            home_id=631338,
            zone_id=36,
            target_temp=23.5,
            power="ON",
            termination_type="TIMER",
            duration_seconds=1800,
        )

        payload = client._request.call_args[1]["json_data"]
        self.assertEqual(payload["termination"]["typeSkillBasedApp"], "TIMER")
        self.assertEqual(payload["termination"]["durationInSeconds"], 1800)


class TestBuildingPhysics(unittest.TestCase):
    """Test atmospheric and building physics calculations."""

    def test_calculate_dew_point_nominal(self):
        # 20°C and 65% RH -> ~13.2°C
        dp = calculate_dew_point(20.0, 65.0)
        self.assertIsNotNone(dp)
        self.assertAlmostEqual(dp, 13.2, delta=0.2)

    def test_calculate_dew_point_extremes_and_invalid(self):
        self.assertIsNone(calculate_dew_point(None, 50.0))
        self.assertIsNone(calculate_dew_point(20.0, None))
        self.assertIsNone(calculate_dew_point(20.0, 0.0))
        self.assertIsNone(calculate_dew_point(20.0, -5.0))
        self.assertIsNone(calculate_dew_point(20.0, 105.0))
        self.assertIsNone(calculate_dew_point(-250.0, 50.0))

    def test_calculate_absolute_humidity_nominal(self):
        # 20°C and 65% RH -> ~11.23 g/m³
        ah = calculate_absolute_humidity(20.0, 65.0)
        self.assertIsNotNone(ah)
        self.assertAlmostEqual(ah, 11.23, delta=0.3)

    def test_calculate_absolute_humidity_invalid(self):
        self.assertIsNone(calculate_absolute_humidity(None, 50.0))
        self.assertIsNone(calculate_absolute_humidity(20.0, None))
        self.assertIsNone(calculate_absolute_humidity(20.0, -10.0))
        self.assertIsNone(calculate_absolute_humidity(-300.0, 50.0))

    def test_calculate_mold_risk_level(self):
        # Low humidity -> normal
        self.assertEqual(calculate_mold_risk_level(20.0, 40.0), "normal")
        # Moderate humidity -> low
        self.assertEqual(calculate_mold_risk_level(20.0, 62.0), "low")
        # Elevated humidity -> medium
        self.assertEqual(calculate_mold_risk_level(20.0, 72.0), "medium")
        # High humidity -> high
        self.assertEqual(calculate_mold_risk_level(20.0, 85.0), "high")
        self.assertIsNone(calculate_mold_risk_level(None, 50.0))

    def test_calculate_mold_risk_problem(self):
        self.assertTrue(calculate_mold_risk_problem(20.0, 75.0))
        self.assertTrue(calculate_mold_risk_problem(20.0, 85.0))
        self.assertFalse(calculate_mold_risk_problem(20.0, 45.0))
        self.assertIsNone(calculate_mold_risk_problem(None, 50.0))

    def test_calculate_ventilation_recommended(self):
        # Indoor warm and humid, outdoor cold: ventilation dries air
        self.assertTrue(calculate_ventilation_recommended(20.0, 65.0, 5.0, 80.0))
        # Outdoor is hotter and very humid: ventilation would introduce moisture
        self.assertFalse(calculate_ventilation_recommended(20.0, 50.0, 26.0, 90.0))
        # Fallback when outdoor humidity is not known
        self.assertTrue(calculate_ventilation_recommended(20.0, 70.0, 5.0, None))
        self.assertFalse(calculate_ventilation_recommended(20.0, 50.0, 5.0, None))
        self.assertIsNone(calculate_ventilation_recommended(None, 50.0, 5.0, 80.0))


class TestRedundancyFilter(unittest.IsolatedAsyncioTestCase):
    """Test coordinator local suppression of no-op API requests."""

    def setUp(self):
        self.hass = MagicMock()
        self.entry = MagicMock()
        self.entry.options = {}
        self.client = MagicMock(spec=TadoClient)
        self.coordinator = DomolinkTadoCoordinator(
            hass=self.hass,
            entry=self.entry,
            client=self.client,
            home_id=12345,
            home_name="Test Home",
        )
        self.coordinator.data = {
            "home_id": 12345,
            "zones": {
                1: {
                    "zone_id": 1,
                    "target_temperature": 21.0,
                    "power": "ON",
                    "is_overlay_active": True,
                },
                2: {
                    "zone_id": 2,
                    "target_temperature": 18.0,
                    "power": "OFF",
                    "is_overlay_active": True,
                },
                3: {
                    "zone_id": 3,
                    "target_temperature": 19.0,
                    "power": "ON",
                    "is_overlay_active": False,
                },
            },
        }

    async def test_set_temperature_redundant_suppressed(self):
        """Zone 1 is already ON at 21.0°C with overlay: call should be skipped."""
        self.client.set_zone_overlay = AsyncMock()
        await self.coordinator.async_set_temperature(1, 21.0)
        self.client.set_zone_overlay.assert_not_called()

    async def test_set_temperature_changed_executed(self):
        """Zone 1 changes to 22.0°C: call should be executed."""
        self.client.set_zone_overlay = AsyncMock(return_value={})
        await self.coordinator.async_set_temperature(1, 22.0)
        self.client.set_zone_overlay.assert_called_once()

    async def test_set_zone_off_redundant_suppressed(self):
        """Zone 2 is already OFF with overlay: call should be skipped."""
        self.client.set_zone_overlay = AsyncMock()
        await self.coordinator.async_set_zone_off(2)
        self.client.set_zone_overlay.assert_not_called()

    async def test_set_zone_off_executed_when_on(self):
        """Zone 1 is ON: turning off should execute."""
        self.client.set_zone_overlay = AsyncMock(return_value={})
        await self.coordinator.async_set_zone_off(1)
        self.client.set_zone_overlay.assert_called_once()

    async def test_resume_schedule_redundant_suppressed(self):
        """Zone 3 has is_overlay_active=False: resume schedule should be skipped."""
        self.client.resume_schedule = AsyncMock()
        await self.coordinator.async_resume_schedule(3)
        self.client.resume_schedule.assert_not_called()

    async def test_resume_schedule_executed_when_overlay(self):
        """Zone 1 has overlay: resume schedule should execute."""
        self.client.resume_schedule = AsyncMock(return_value={})
        await self.coordinator.async_resume_schedule(1)
        self.client.resume_schedule.assert_called_once()

    async def test_resume_all_schedules_filters_zones(self):
        """Zones 1 & 2 have overlay, Zone 3 does not. Resume all should only touch 1 & 2."""
        called_zones = []
        async def mock_resume(hid, zid):
            called_zones.append(zid)
            return {}

        self.client.resume_schedule = AsyncMock(side_effect=mock_resume)
        await self.coordinator.async_resume_all_schedules()
        self.assertEqual(set(called_zones), {1, 2})

    async def test_resume_all_schedules_skips_when_no_overlay(self):
        """When 0 zones have overlay, resume all does zero API calls."""
        for zd in self.coordinator.data["zones"].values():
            zd["is_overlay_active"] = False

        self.client.resume_schedule = AsyncMock()
        await self.coordinator.async_resume_all_schedules()
        self.client.resume_schedule.assert_not_called()

    async def test_set_all_off_filters_already_off(self):
        """Zone 2 is already OFF with overlay. set_all_off should only turn off Zones 1 & 3."""
        called_zones = []
        async def mock_overlay(home_id, zone_id, **kw):
            called_zones.append(zone_id)
            return {}

        self.client.set_zone_overlay = AsyncMock(side_effect=mock_overlay)
        await self.coordinator.async_set_all_off()
        self.assertEqual(set(called_zones), {1, 3})


class TestZonePhysicsDataAndSensors(unittest.IsolatedAsyncioTestCase):
    """Test sensor entities reading physics data computed by coordinator."""

    def test_sensor_entities_read_computed_physics(self):
        hass = MagicMock()
        entry = MagicMock()
        entry.options = {}
        client = MagicMock(spec=TadoClient)
        coordinator = DomolinkTadoCoordinator(hass, entry, client, 12345, "Test Home")
        coordinator.data = {
            "home_id": 12345,
            "zones": {
                1: {
                    "zone_id": 1,
                    "name": "Chambre",
                    "dew_point": 12.5,
                    "absolute_humidity": 10.5,
                    "mold_risk_level": "medium",
                    "mold_risk_problem": True,
                    "ventilation_recommended": True,
                }
            },
            "weather": {
                "outdoor_temperature": 7.0,
                "outdoor_humidity": 75.0,
            }
        }

        dp_sensor = DomolinkTadoZoneDewPointSensor(coordinator, 1)
        self.assertEqual(dp_sensor.native_value, 12.5)

        ah_sensor = DomolinkTadoZoneAbsoluteHumiditySensor(coordinator, 1)
        self.assertEqual(ah_sensor.native_value, 10.5)

        risk_sensor = DomolinkTadoZoneMoldRiskSensor(coordinator, 1)
        self.assertEqual(risk_sensor.native_value, "medium")

        problem_sensor = DomolinkTadoZoneMoldRiskProblemBinarySensor(coordinator, 1)
        self.assertTrue(problem_sensor.is_on)

        vent_sensor = DomolinkTadoZoneVentilationRecommendedBinarySensor(coordinator, 1)
        self.assertTrue(vent_sensor.is_on)

        outdoor_hum_sensor = DomolinkTadoOutdoorHumiditySensor(coordinator)
        self.assertEqual(outdoor_hum_sensor.native_value, 75.0)


if __name__ == "__main__":
    unittest.main()
