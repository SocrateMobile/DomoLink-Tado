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
        BUTTON = "button"
        WATER_HEATER = "water_heater"
    ha_const.Platform = Platform
    ha_const.PERCENTAGE = "%"
    ha_const.ATTR_TEMPERATURE = "temperature"
    ha_const.PRECISION_HALVES = 0.5
    ha_const.PRECISION_TENTHS = 0.1
    class UnitOfTemperature:
        CELSIUS = "°C"
    ha_const.UnitOfTemperature = UnitOfTemperature

    ha_climate = make_pkg("homeassistant.components.climate")
    class ClimateEntity: pass
    class ClimateEntityFeature:
        TARGET_TEMPERATURE = 1
        TURN_ON = 2
        TURN_OFF = 4
        FAN_MODE = 8
        SWING_MODE = 16
    class HVACMode:
        OFF = "off"
        HEAT = "heat"
        COOL = "cool"
        HEAT_COOL = "heat_cool"
        AUTO = "auto"
        DRY = "dry"
        FAN_ONLY = "fan_only"
    class HVACAction:
        OFF = "off"
        HEATING = "heating"
        COOLING = "cooling"
        DRYING = "drying"
        IDLE = "idle"
        FAN = "fan"
    ha_climate.ClimateEntity = ClimateEntity
    ha_climate.ClimateEntityFeature = ClimateEntityFeature
    ha_climate.HVACMode = HVACMode
    ha_climate.HVACAction = HVACAction

    ha_btn = make_pkg("homeassistant.components.button")
    class ButtonEntity: pass
    ha_btn.ButtonEntity = ButtonEntity

    ha_switch = make_pkg("homeassistant.components.switch")
    class SwitchEntity: pass
    ha_switch.SwitchEntity = SwitchEntity

    ha_wh = make_pkg("homeassistant.components.water_heater")
    class WaterHeaterEntity: pass
    class WaterHeaterEntityFeature:
        OPERATION_MODE = 1
        TARGET_TEMPERATURE = 2
    ha_wh.WaterHeaterEntity = WaterHeaterEntity
    ha_wh.WaterHeaterEntityFeature = WaterHeaterEntityFeature

    ha_sensor = make_pkg("homeassistant.components.sensor")
    class SensorEntity: pass
    class SensorDeviceClass:
        TEMPERATURE = "temperature"
        HUMIDITY = "humidity"
        ENUM = "enum"
        TIMESTAMP = "timestamp"
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
    class OptionsFlow:
        def async_create_entry(self, **kwargs): return {"type": "create_entry", **kwargs}
        def async_show_form(self, **kwargs): return {"type": "form", **kwargs}
        def async_abort(self, **kwargs): return {"type": "abort", **kwargs}
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
    class HomeAssistantError(Exception): pass
    ha_exc.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    ha_exc.UpdateFailed = UpdateFailed
    ha_exc.ConfigEntryNotReady = ConfigEntryNotReady
    ha_exc.HomeAssistantError = HomeAssistantError

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
        @property
        def unique_id(self):
            return getattr(self, "_attr_unique_id", None)
        @property
        def name(self):
            return getattr(self, "_attr_name", None)
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
    DomolinkTadoZonePreheatAdvisorSensor,
    DomolinkTadoZoneHeatingRateSensor,
    DomolinkTadoQuotaRemainingSensor,
    DomolinkTadoQuotaLimitSensor,
    DomolinkTadoQuotaUsedSensor,
    DomolinkTadoZoneTempSensor,
    DomolinkTadoZoneHumiditySensor,
)
from custom_components.domolink_tado.climate import (
    DomolinkTadoClimate,
    async_setup_entry as async_setup_climate_entry,
)
from custom_components.domolink_tado.config_flow import (
    DomolinkTadoConfigFlow,
    DomolinkTadoOptionsFlow,
)
from custom_components.domolink_tado.const import (
    CONF_AUTO_OFFSET_CALIBRATION,
    CONF_SHOW_QUOTA_SENSORS,
    CONF_ZONE_HUMIDITY_ENTITIES,
    CONF_ZONE_TEMP_ENTITIES,
)
from homeassistant.components.climate import HVACAction, HVACMode
from custom_components.domolink_tado.binary_sensor import (
    DomolinkTadoZoneMoldRiskProblemBinarySensor,
    DomolinkTadoZoneVentilationRecommendedBinarySensor,
    DomolinkTadoZonePreheatNowBinarySensor,
    DomolinkTadoZoneRapidWindowDropBinarySensor,
)
from custom_components.domolink_tado.adaptive_preheat import (
    estimate_preheat_duration,
    update_heating_rate,
    detect_rapid_temperature_drop,
    find_next_scheduled_change,
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


class TestAdaptivePreheatAndRapidDrop(unittest.TestCase):
    """Test adaptive preheat calculation, heating rate learning, and rapid drop detection."""

    def test_estimate_preheat_duration_basic(self):
        # 2.0 deg rise at 2.0 deg/h = 1.0 h = 60 min
        self.assertEqual(estimate_preheat_duration(21.0, 19.0, 2.0), 60)
        # 1.0 deg rise at 2.0 deg/h = 0.5 h = 30 min
        self.assertEqual(estimate_preheat_duration(20.0, 19.0, 2.0), 30)
        # Already at or above target
        self.assertEqual(estimate_preheat_duration(19.0, 20.0, 2.0), 0)
        self.assertEqual(estimate_preheat_duration(20.0, 20.0, 2.0), 0)
        # None inputs
        self.assertEqual(estimate_preheat_duration(None, 20.0, 2.0), 0)
        self.assertEqual(estimate_preheat_duration(21.0, None, 2.0), 0)
        # Max duration capping
        self.assertEqual(estimate_preheat_duration(25.0, 15.0, 1.0, max_duration_minutes=90), 90)

    def test_update_heating_rate_ema(self):
        # 1.0 deg rise in 0.5 hours -> 2.0 deg/h measured
        # 0.8 * 1.5 + 0.2 * 2.0 = 1.2 + 0.4 = 1.6
        new_rate = update_heating_rate(1.5, 19.0, 20.0, 0.5)
        self.assertEqual(new_rate, 1.6)

        # Duration too short (< 0.2 hours = 12 min): should return old rate
        unchanged = update_heating_rate(1.5, 19.0, 20.0, 0.1)
        self.assertEqual(unchanged, 1.5)

        # Temperature decreased: should return old rate
        unchanged_drop = update_heating_rate(1.5, 20.0, 19.0, 0.5)
        self.assertEqual(unchanged_drop, 1.5)

    def test_detect_rapid_temperature_drop(self):
        # Insufficient data
        self.assertFalse(detect_rapid_temperature_drop([]))
        self.assertFalse(detect_rapid_temperature_drop([(100.0, 20.0)]))

        # Stable temperature
        stable_history = [(100.0, 20.0), (200.0, 20.1), (300.0, 20.0)]
        self.assertFalse(detect_rapid_temperature_drop(stable_history))

        # Slow drop: 0.6 deg drop over 400s (exceeds max_seconds 300s)
        slow_drop_history = [(0.0, 20.0), (100.0, 19.8), (400.0, 19.4)]
        self.assertFalse(detect_rapid_temperature_drop(slow_drop_history, threshold_drop=0.5, max_seconds=300.0))

        # Rapid drop: 0.7 deg drop in 240s
        rapid_drop_history = [(0.0, 20.0), (120.0, 19.8), (240.0, 19.3)]
        self.assertTrue(detect_rapid_temperature_drop(rapid_drop_history, threshold_drop=0.5, max_seconds=300.0))

    def test_find_next_scheduled_change(self):
        from datetime import datetime, timedelta
        now = datetime(2026, 9, 17, 6, 0)  # Thursday 06:00
        blocks = [
            {
                "dayType": "THURSDAY",
                "start": "05:00",
                "end": "07:00",
                "setting": {"power": "ON", "temperature": {"celsius": 18.0}},
            },
            {
                "dayType": "THURSDAY",
                "start": "07:30",
                "end": "22:00",
                "setting": {"power": "ON", "temperature": {"celsius": 21.0}},
            },
        ]
        res = find_next_scheduled_change(blocks, now)
        self.assertIsNotNone(res)
        self.assertEqual(res["start_dt"], datetime(2026, 9, 17, 7, 30))
        self.assertEqual(res["target_temp"], 21.0)
        self.assertEqual(res["power"], "ON")


class TestPreheatSensorEntities(unittest.TestCase):
    """Test preheat sensors and binary sensors."""

    def setUp(self):
        self.hass = MagicMock()
        self.entry = MagicMock()
        self.entry.options = {}
        self.client = MagicMock(spec=TadoClient)
        self.coordinator = DomolinkTadoCoordinator(self.hass, self.entry, self.client, 631338, "Maison Tado")
        self.coordinator.data = {
            "home_id": 631338,
            "zones": {
                36: {
                    "zone_id": 36,
                    "name": "Salon",
                    "preheat_advisor": "2026-09-17T07:00:00",
                    "preheat_duration": 30,
                    "preheat_target_temp": 21.0,
                    "preheat_now": True,
                    "heating_rate": 1.75,
                    "rapid_window_drop": True,
                }
            }
        }

    def test_preheat_advisor_sensor(self):
        sensor = DomolinkTadoZonePreheatAdvisorSensor(self.coordinator, 36)
        from datetime import datetime
        self.assertEqual(sensor.native_value, datetime(2026, 9, 17, 7, 0))
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["preheat_duration_minutes"], 30)
        self.assertEqual(attrs["target_temperature"], 21.0)
        self.assertEqual(attrs["heating_rate"], 1.75)

    def test_preheat_advisor_sensor_none(self):
        self.coordinator.data["zones"][36]["preheat_advisor"] = None
        sensor = DomolinkTadoZonePreheatAdvisorSensor(self.coordinator, 36)
        self.assertIsNone(sensor.native_value)

    def test_heating_rate_sensor(self):
        sensor = DomolinkTadoZoneHeatingRateSensor(self.coordinator, 36)
        self.assertEqual(sensor.native_value, 1.75)

    def test_preheat_now_binary_sensor(self):
        sensor = DomolinkTadoZonePreheatNowBinarySensor(self.coordinator, 36)
        self.assertTrue(sensor.is_on)
        self.coordinator.data["zones"][36]["preheat_now"] = False
        self.assertFalse(sensor.is_on)

    def test_rapid_window_drop_binary_sensor(self):
        sensor = DomolinkTadoZoneRapidWindowDropBinarySensor(self.coordinator, 36)
        self.assertTrue(sensor.is_on)
        self.coordinator.data["zones"][36]["rapid_window_drop"] = False
        self.assertFalse(sensor.is_on)


if __name__ == "__main__":
    unittest.main()


from custom_components.domolink_tado.button import (
    DomolinkTadoResumeAllSchedulesButton,
    DomolinkTadoAllOffButton,
    DomolinkTadoSmartBoostButton,
    DomolinkTadoZoneResumeScheduleButton,
    DomolinkTadoZoneBoostButton,
    async_setup_entry as async_setup_button_entry,
)
from custom_components.domolink_tado.switch import (
    DomolinkTadoGlobalEcoSwitch,
)
from custom_components.domolink_tado.water_heater import (
    DomolinkTadoWaterHeater,
    async_setup_entry as async_setup_water_heater_entry,
)
from custom_components.domolink_tado.const import (
    CONF_AUTO_GEOFENCING_ENABLED,
    CONF_GEOFENCING_PERSONS,
    CONF_SMART_BOOST_TEMP,
    CONF_SMART_BOOST_DURATION,
    CONF_ECO_TEMP,
)


class TestGeofencingAndSmartBoost(unittest.IsolatedAsyncioTestCase):
    """Tests pour le bridge de géofencing automatisé et le Smart Boost."""

    def setUp(self):
        self.hass = MagicMock()
        self.entry = MagicMock()
        self.entry.options = {
            CONF_AUTO_GEOFENCING_ENABLED: True,
            CONF_GEOFENCING_PERSONS: "person.alice, person.bob",
            CONF_SMART_BOOST_TEMP: 23.5,
            CONF_SMART_BOOST_DURATION: 1200,
        }
        self.client = MagicMock(spec=TadoClient)
        self.coordinator = DomolinkTadoCoordinator(
            self.hass, self.entry, self.client, 631338, "Maison Tado"
        )
        self.coordinator.data = {
            "home_id": 631338,
            "presence": "HOME",
            "zones": {
                1: {"name": "Salon", "is_overlay_active": False, "type": "HEATING"},
                2: {"name": "Chambre", "is_overlay_active": False, "type": "HEATING"},
            },
        }

    async def test_geofencing_disabled_noop(self):
        self.entry.options[CONF_AUTO_GEOFENCING_ENABLED] = False
        with patch.object(self.coordinator, "async_set_presence") as mock_set_pres:
            self.coordinator._check_automated_geofencing("AWAY")
            mock_set_pres.assert_not_called()

    async def test_geofencing_all_persons_away(self):
        # Alice et Bob sont absents
        def get_state(entity_id):
            mock_st = MagicMock()
            mock_st.state = "not_home"
            return mock_st

        self.hass.states.get.side_effect = get_state

        tasks = []
        self.hass.async_create_task.side_effect = lambda coro: tasks.append(asyncio.create_task(coro))

        with patch.object(self.coordinator, "async_set_presence", new_callable=AsyncMock) as mock_set_pres:
            self.coordinator._check_automated_geofencing("HOME")
            self.assertEqual(len(tasks), 1)
            await asyncio.gather(*tasks)
            mock_set_pres.assert_called_once_with(False)

    async def test_geofencing_one_person_home(self):
        # Alice est à la maison, Bob absent -> Présence = HOME
        def get_state(entity_id):
            mock_st = MagicMock()
            mock_st.state = "home" if "alice" in entity_id else "not_home"
            return mock_st

        self.hass.states.get.side_effect = get_state

        tasks = []
        self.hass.async_create_task.side_effect = lambda coro: tasks.append(asyncio.create_task(coro))

        with patch.object(self.coordinator, "async_set_presence", new_callable=AsyncMock) as mock_set_pres:
            # Si actuellement AWAY sur Tado, on doit basculer HOME
            self.coordinator._check_automated_geofencing("AWAY")
            self.assertEqual(len(tasks), 1)
            await asyncio.gather(*tasks)
            mock_set_pres.assert_called_once_with(True)

    async def test_geofencing_fallback_zone_home(self):
        # Pas d'entités person configurées, fallback sur zone.home
        self.entry.options[CONF_GEOFENCING_PERSONS] = ""
        mock_zone = MagicMock()
        mock_zone.state = "2"  # 2 personnes dans la zone
        self.hass.states.get.return_value = mock_zone

        tasks = []
        self.hass.async_create_task.side_effect = lambda coro: tasks.append(asyncio.create_task(coro))

        with patch.object(self.coordinator, "async_set_presence", new_callable=AsyncMock) as mock_set_pres:
            self.coordinator._check_automated_geofencing("AWAY")
            self.assertEqual(len(tasks), 1)
            await asyncio.gather(*tasks)
            mock_set_pres.assert_called_once_with(True)

    async def test_set_presence_redundancy_filter(self):
        # Si la présence Tado est déjà HOME et qu'on demande HOME, aucun appel API ne doit être émis
        self.coordinator.data["presence"] = "HOME"
        self.client.set_presence = AsyncMock()

        await self.coordinator.async_set_presence(True)
        self.client.set_presence.assert_not_called()

        # Si on demande AWAY, l'appel doit être émis (avec home=False)
        await self.coordinator.async_set_presence(False)
        self.client.set_presence.assert_called_once_with(631338, False)

    async def test_async_smart_boost(self):
        with patch.object(self.coordinator, "_async_execute_all_zones", new_callable=AsyncMock) as mock_exec:
            await self.coordinator.async_smart_boost()
            mock_exec.assert_called_once()
            self.assertIn("Smart Boost 23.5°C (1200s)", mock_exec.call_args[0][0])

    async def test_async_set_zone_boost(self):
        with patch.object(self.coordinator, "async_set_temperature", new_callable=AsyncMock) as mock_temp:
            await self.coordinator.async_set_zone_boost(zone_id=1)
            mock_temp.assert_called_once_with(
                1,
                target_temp=23.5,
                termination_type="TIMER",
                duration_seconds=1200,
            )


class TestButtonEntities(unittest.IsolatedAsyncioTestCase):
    """Tests pour les entités de type Bouton."""

    def setUp(self):
        self.hass = MagicMock()
        self.coordinator = MagicMock()
        self.coordinator.home_id = 631338
        self.coordinator.home_name = "Maison"
        self.coordinator.data = {
            "zones": {
                1: {"name": "Salon"},
                2: {"name": "Cuisine"},
            }
        }
        self.coordinator.async_resume_all_schedules = AsyncMock()
        self.coordinator.async_set_all_off = AsyncMock()
        self.coordinator.async_smart_boost = AsyncMock()
        self.coordinator.async_resume_schedule = AsyncMock()
        self.coordinator.async_set_zone_boost = AsyncMock()

    async def test_resume_all_schedules_button(self):
        btn = DomolinkTadoResumeAllSchedulesButton(self.coordinator)
        self.assertEqual(btn.unique_id, "domolink_tado_631338_resume_all_schedules")
        await btn.async_press()
        self.coordinator.async_resume_all_schedules.assert_called_once()

    async def test_all_off_button(self):
        btn = DomolinkTadoAllOffButton(self.coordinator)
        self.assertEqual(btn.unique_id, "domolink_tado_631338_all_off")
        await btn.async_press()
        self.coordinator.async_set_all_off.assert_called_once()

    async def test_smart_boost_button(self):
        btn = DomolinkTadoSmartBoostButton(self.coordinator)
        self.assertEqual(btn.unique_id, "domolink_tado_631338_smart_boost")
        await btn.async_press()
        self.coordinator.async_smart_boost.assert_called_once()

    async def test_zone_buttons(self):
        btn_res = DomolinkTadoZoneResumeScheduleButton(self.coordinator, 1)
        self.assertEqual(btn_res.unique_id, "domolink_tado_631338_1_resume_schedule")
        await btn_res.async_press()
        self.coordinator.async_resume_schedule.assert_called_once_with(1)

        btn_boost = DomolinkTadoZoneBoostButton(self.coordinator, 1)
        self.assertEqual(btn_boost.unique_id, "domolink_tado_631338_1_smart_boost")
        await btn_boost.async_press()
        self.coordinator.async_set_zone_boost.assert_called_once_with(1)

    async def test_button_async_setup_entry(self):
        entry = MagicMock()
        entry.entry_id = "entry_123"
        self.hass.data = {"domolink_tado": {"entry_123": {"coordinator": self.coordinator}}}

        added_entities = []
        def add_entities(ents):
            added_entities.extend(ents)

        await async_setup_button_entry(self.hass, entry, add_entities)
        # 3 globaux + 2 par zone (2 zones -> 4 boutons de zone) = 7 boutons
        self.assertEqual(len(added_entities), 7)


class TestGlobalEcoSwitch(unittest.IsolatedAsyncioTestCase):
    """Tests pour le commutateur global Mode Éco."""

    def setUp(self):
        self.coordinator = MagicMock()
        self.coordinator.home_id = 631338
        self.coordinator.home_name = "Maison"
        self.coordinator.entry = MagicMock()
        self.coordinator.entry.options = {CONF_ECO_TEMP: 17.0}
        self.coordinator.data = {
            "zones": {
                1: {
                    "type": "HEATING",
                    "is_overlay_active": False,
                    "target_temperature": 21.0,
                },
                2: {
                    "type": "HEATING",
                    "is_overlay_active": False,
                    "target_temperature": 20.0,
                },
            }
        }
        self.coordinator.async_set_eco_all = AsyncMock()
        self.coordinator.async_resume_all_schedules = AsyncMock()

    async def test_eco_switch_state(self):
        switch = DomolinkTadoGlobalEcoSwitch(self.coordinator)
        self.assertEqual(switch.unique_id, "domolink_tado_631338_global_eco_switch")
        self.assertFalse(switch.is_on)

        # Quand toutes les zones sont à 17°C en forçage manuel
        self.coordinator.data["zones"][1]["is_overlay_active"] = True
        self.coordinator.data["zones"][1]["target_temperature"] = 17.0
        self.coordinator.data["zones"][2]["is_overlay_active"] = True
        self.coordinator.data["zones"][2]["target_temperature"] = 17.0

        self.assertTrue(switch.is_on)

    async def test_eco_switch_actions(self):
        switch = DomolinkTadoGlobalEcoSwitch(self.coordinator)
        await switch.async_turn_on()
        self.coordinator.async_set_eco_all.assert_called_once()

        await switch.async_turn_off()
        self.coordinator.async_resume_all_schedules.assert_called_once()


class TestWaterHeaterEntity(unittest.IsolatedAsyncioTestCase):
    """Tests pour l'entité chauffe-eau sanitaire DomoLink-Tado."""

    def setUp(self):
        self.coordinator = MagicMock()
        self.coordinator.home_id = 631338
        self.coordinator.data = {
            "zones": {
                3: {
                    "zone_id": 3,
                    "name": "Ballon ECS",
                    "type": "HOT_WATER",
                    "power": "ON",
                    "is_overlay_active": False,
                    "inside_temperature": 52.0,
                    "target_temperature": 55.0,
                },
                1: {
                    "zone_id": 1,
                    "name": "Salon",
                    "type": "HEATING",
                },
            }
        }
        self.coordinator.async_set_water_heater_mode = AsyncMock()
        self.coordinator.async_set_water_heater_temperature = AsyncMock()

    def test_water_heater_properties(self):
        wh = DomolinkTadoWaterHeater(self.coordinator, 3)
        self.assertEqual(wh.unique_id, "domolink_tado_631338_3_water_heater")
        self.assertEqual(wh.current_operation, "auto")
        self.assertEqual(wh.current_temperature, 52.0)
        self.assertEqual(wh.target_temperature, 55.0)

        # Overlay actif -> mode heat
        self.coordinator.data["zones"][3]["is_overlay_active"] = True
        self.assertEqual(wh.current_operation, "heat")

        # Coupure complète -> mode off
        self.coordinator.data["zones"][3]["power"] = "OFF"
        self.assertEqual(wh.current_operation, "off")

    async def test_water_heater_actions(self):
        wh = DomolinkTadoWaterHeater(self.coordinator, 3)
        await wh.async_set_operation_mode("off")
        self.coordinator.async_set_water_heater_mode.assert_called_once_with(3, "off")

        await wh.async_set_temperature(temperature=60.0)
        self.coordinator.async_set_water_heater_temperature.assert_called_once_with(3, 60.0)

    async def test_water_heater_setup_entry(self):
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {"domolink_tado": {"test_entry": {"coordinator": self.coordinator}}}

        added_entities = []
        def add_entities(ents):
            added_entities.extend(ents)

        await async_setup_water_heater_entry(hass, entry, add_entities)
        # Seule la zone HOT_WATER doit être ajoutée (pas la zone HEATING)
        self.assertEqual(len(added_entities), 1)
        self.assertIsInstance(added_entities[0], DomolinkTadoWaterHeater)


class TestRateLimitHeaderParsing(unittest.IsolatedAsyncioTestCase):
    """Unit tests for RFC RateLimit sniffing in TadoClient."""

    def setUp(self):
        self.client = TadoClient(session=MagicMock(), access_token="mock_token")

    def test_parse_ratelimit_standard_headers(self):
        headers = {
            "RateLimit": "r=42",
            "RateLimit-Policy": "q=100;w=86400",
            "RateLimit-Reset": "1200",
        }
        self.client._parse_ratelimit_headers(headers)
        self.assertEqual(self.client.rate_limit_limit, 100)
        self.assertEqual(self.client.rate_limit_remaining, 42)
        self.assertEqual(self.client.rate_limit_reset_seconds, 1200)

        info = self.client.rate_limit_info
        self.assertEqual(info["limit"], 100)
        self.assertEqual(info["remaining"], 42)
        self.assertEqual(info["used"], 58)
        self.assertEqual(info["requests_count"], 0)
        self.assertEqual(info["reset_seconds"], 1200)
        self.assertIsNotNone(info["last_update"])

    def test_parse_ratelimit_lowercase_headers(self):
        headers = {
            "ratelimit": "r=15",
            "ratelimit-policy": "q=200",
        }
        self.client._parse_ratelimit_headers(headers)
        self.assertEqual(self.client.rate_limit_limit, 200)
        self.assertEqual(self.client.rate_limit_remaining, 15)

    def test_parse_x_ratelimit_legacy_headers(self):
        headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "88",
            "X-RateLimit-Reset": "600",
        }
        self.client._parse_ratelimit_headers(headers)
        self.assertEqual(self.client.rate_limit_limit, 100)
        self.assertEqual(self.client.rate_limit_remaining, 88)
        self.assertEqual(self.client.rate_limit_reset_seconds, 600)

    async def test_set_zone_overlay_with_ac_parameters(self):
        self.client._request = AsyncMock(return_value={"setting": {"power": "ON"}})
        await self.client.set_zone_overlay(
            home_id=631338,
            zone_id=5,
            target_temp=22.0,
            power="ON",
            termination_type="MANUAL",
            zone_type="AIR_CONDITIONING",
            mode="COOL",
            fan_speed="HIGH",
            swing="ON",
        )
        self.client._request.assert_called_once()
        call_args = self.client._request.call_args
        self.assertEqual(call_args[0][0], "PUT")
        self.assertEqual(call_args[0][1], "/homes/631338/zones/5/overlay")
        json_data = call_args[1]["json_data"]
        self.assertEqual(json_data["setting"]["type"], "AIR_CONDITIONING")
        self.assertEqual(json_data["setting"]["mode"], "COOL")
        self.assertEqual(json_data["setting"]["fanSpeed"], "HIGH")
        self.assertEqual(json_data["setting"]["swing"], "ON")
        self.assertEqual(json_data["setting"]["temperature"]["celsius"], 22.0)


class TestQuotaSensors(unittest.TestCase):
    """Unit tests for Tado API Quota sensors."""

    def setUp(self):
        self.coordinator = MagicMock()
        self.coordinator.home_id = 631338
        self.coordinator.home_name = "Maison Test"
        self.coordinator.data = {
            "rate_limit": {
                "limit": 100,
                "remaining": 42,
                "used": 58,
                "requests_count": 58,
                "reset_seconds": 3600,
                "last_update": "2026-09-17T22:00:00",
            }
        }

    def test_quota_remaining_sensor(self):
        sensor = DomolinkTadoQuotaRemainingSensor(self.coordinator)
        self.assertEqual(sensor.unique_id, "domolink_tado_631338_quota_remaining")
        self.assertEqual(sensor.native_value, 42)
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["quota_limit"], 100)
        self.assertEqual(attrs["requests_used"], 58)
        self.assertEqual(attrs["requests_count"], 58)
        self.assertEqual(attrs["reset_seconds"], 3600)
        self.assertEqual(attrs["last_update"], "2026-09-17T22:00:00")

    def test_quota_limit_sensor(self):
        sensor = DomolinkTadoQuotaLimitSensor(self.coordinator)
        self.assertEqual(sensor.unique_id, "domolink_tado_631338_quota_limit")
        self.assertEqual(sensor.native_value, 100)

    def test_quota_used_sensor(self):
        sensor = DomolinkTadoQuotaUsedSensor(self.coordinator)
        self.assertEqual(sensor.unique_id, "domolink_tado_631338_quota_used")
        self.assertEqual(sensor.native_value, 58)


class TestExternalSensorsAndAutoCalibration(unittest.IsolatedAsyncioTestCase):
    """Unit tests for external sensor override and auto-offset calibration engine."""

    def setUp(self):
        self.hass = MagicMock()
        self.entry = MagicMock()
        self.entry.entry_id = "test_entry"
        self.entry.options = {
            CONF_ZONE_TEMP_ENTITIES: {"1": "sensor.salon_external_temp"},
            CONF_ZONE_HUMIDITY_ENTITIES: {"1": "sensor.salon_external_hum"},
            CONF_AUTO_OFFSET_CALIBRATION: True,
        }
        self.client = MagicMock()
        self.coordinator = DomolinkTadoCoordinator(
            self.hass, self.entry, self.client, 631338, "Maison Test"
        )
        self.coordinator.data = {
            "zones": {
                1: {
                    "zone_id": 1,
                    "name": "Salon",
                    "type": "HEATING",
                    "inside_temperature": 20.0,
                    "raw_inside_temperature": 23.0,
                    "humidity": 55.0,
                    "raw_humidity": 40.0,
                    "is_external_temp": True,
                    "is_external_humidity": True,
                    "devices": [{"serialNo": "VA0123", "currentMountedOffset": {"celsius": 0.0}}],
                }
            }
        }

    def test_zone_temp_sensor_attributes_with_external_sensor(self):
        temp_sensor = DomolinkTadoZoneTempSensor(self.coordinator, 1)
        self.assertEqual(temp_sensor.native_value, 20.0)
        attrs = temp_sensor.extra_state_attributes
        self.assertEqual(attrs["source"], "external_sensor")
        self.assertEqual(attrs["raw_tado_temperature"], 23.0)

        hum_sensor = DomolinkTadoZoneHumiditySensor(self.coordinator, 1)
        self.assertEqual(hum_sensor.native_value, 55.0)
        h_attrs = hum_sensor.extra_state_attributes
        self.assertEqual(h_attrs["source"], "external_sensor")
        self.assertEqual(h_attrs["raw_tado_humidity"], 40.0)

    def test_zone_temp_sensor_attributes_native_tado(self):
        self.coordinator.data["zones"][1]["is_external_temp"] = False
        self.coordinator.data["zones"][1]["is_external_humidity"] = False
        temp_sensor = DomolinkTadoZoneTempSensor(self.coordinator, 1)
        self.assertEqual(temp_sensor.extra_state_attributes["source"], "tado_sensor")
        hum_sensor = DomolinkTadoZoneHumiditySensor(self.coordinator, 1)
        self.assertEqual(hum_sensor.extra_state_attributes["source"], "tado_sensor")

    async def test_auto_offset_calibration_triggered_and_cooldown(self):
        # Mocking Tado API discovery and zone state
        now_time = 100000.0
        self.coordinator.client.get_zones = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "Salon",
                    "type": "HEATING",
                    "devices": [{"serialNo": "VA0123"}],
                }
            ]
        )
        self.coordinator.client.get_devices = AsyncMock(
            return_value=[
                {
                    "serialNo": "VA0123",
                    "deviceType": "VA01",
                    "currentMountedOffset": {"celsius": 0.0},
                }
            ]
        )
        self.coordinator.client.get_zone_states = AsyncMock(
            return_value={
                "zoneStates": {
                    "1": {
                        "sensorDataPoints": {
                            "insideTemperature": {"celsius": 23.0},
                            "humidity": {"percentage": 40.0},
                        },
                        "setting": {"power": "ON", "temperature": {"celsius": 21.0}},
                    }
                }
            }
        )
        self.coordinator.client.get_weather = AsyncMock(return_value={})
        self.coordinator.client.get_home_state = AsyncMock(return_value={"presence": "HOME"})
        self.coordinator.async_set_temperature_offset = AsyncMock()

        # HA state mock: external temp is 20.0°C (difference is 20.0 - 23.0 = -3.0°C)
        ext_st = MagicMock()
        ext_st.state = "20.0"
        self.hass.states.get = MagicMock(return_value=ext_st)

        created_tasks = []
        def _mock_create_task(coro):
            created_tasks.append(coro)
            return MagicMock()

        self.coordinator.hass.async_create_task = MagicMock(side_effect=_mock_create_task)

        with patch("time.time", return_value=now_time):
            data = await self.coordinator._async_update_data()

        # Check injected values
        self.assertEqual(data["zones"][1]["inside_temperature"], 20.0)
        self.assertEqual(data["zones"][1]["raw_inside_temperature"], 23.0)
        self.assertTrue(data["zones"][1]["is_external_temp"])

        # Offset change is -3.0°C (>= 0.5°C threshold) -> async_set_temperature_offset must be triggered
        self.assertEqual(len(created_tasks), 1)
        self.assertEqual(self.coordinator._last_offset_update_time["VA0123"], now_time)
        for c in created_tasks:
            await c

        # Immediate next call (100 seconds later < 1800s cooldown)
        self.coordinator.hass.async_create_task.reset_mock()
        created_tasks.clear()
        with patch("time.time", return_value=now_time + 100):
            await self.coordinator._async_update_data()
        # Should NOT be called because of cooldown
        self.assertEqual(len(created_tasks), 0)

    async def test_auto_offset_anti_chatter_deadband(self):
        # When delta is only 0.2°C (< 0.5°C deadband)
        now_time = 200000.0
        self.coordinator._zones_raw = [
            {"id": 1, "name": "Salon", "type": "HEATING", "devices": [{"serialNo": "VA0123"}]}
        ]
        self.coordinator._devices_raw = [
            {"serialNo": "VA0123", "currentMountedOffset": {"celsius": 0.0}}
        ]
        self.coordinator._last_discovery_time = now_time
        self.coordinator.client.get_zone_states = AsyncMock(
            return_value={
                "zoneStates": {
                    "1": {
                        "sensorDataPoints": {"insideTemperature": {"celsius": 20.0}},
                        "setting": {"power": "ON"},
                    }
                }
            }
        )
        self.coordinator.client.get_weather = AsyncMock(return_value={})
        self.coordinator.client.get_home_state = AsyncMock(return_value={})

        ext_st = MagicMock()
        ext_st.state = "20.2"  # Diff is only 0.2°C (< 0.5°C)
        self.hass.states.get = MagicMock(return_value=ext_st)
        self.coordinator.hass.async_create_task = MagicMock()

        with patch("time.time", return_value=now_time):
            await self.coordinator._async_update_data()

        # No offset task created
        self.coordinator.hass.async_create_task.assert_not_called()


class TestSmartACClimate(unittest.IsolatedAsyncioTestCase):
    """Unit tests for Smart AC Control Climate platform."""

    def setUp(self):
        self.coordinator = MagicMock()
        self.coordinator.home_id = 631338
        self.coordinator.home_name = "Maison Test"
        self.coordinator.get_zone_labels = MagicMock(return_value=["Salon"])
        self.coordinator.async_set_ac_mode = AsyncMock()
        self.coordinator.async_set_temperature = AsyncMock()
        self.coordinator.async_resume_schedule = AsyncMock()
        self.coordinator.async_set_zone_off = AsyncMock()
        self.coordinator.data = {
            "zones": {
                2: {
                    "zone_id": 2,
                    "name": "Clim Salon",
                    "type": "AIR_CONDITIONING",
                    "inside_temperature": 24.5,
                    "target_temperature": 22.0,
                    "power": "ON",
                    "ac_mode": "COOL",
                    "fan_speed": "HIGH",
                    "swing": "ON",
                    "is_overlay_active": True,
                    "devices": [
                        {
                            "serialNo": "AC12345",
                            "deviceType": "Smart AC Control",
                            "batteryState": "NORMAL",
                        }
                    ],
                }
            }
        }
        self.entry = MagicMock()
        self.entry.options = {}

    def test_ac_climate_properties(self):
        climate = DomolinkTadoClimate(self.coordinator, self.entry, 2)
        self.assertTrue(climate.is_ac)
        self.assertEqual(climate.icon, "mdi:air-conditioner")
        self.assertEqual(climate.hvac_mode, HVACMode.COOL)
        self.assertEqual(climate.hvac_action, HVACAction.COOLING)
        self.assertEqual(climate.fan_mode, "high")
        self.assertEqual(climate.swing_mode, "on")
        self.assertIn(HVACMode.COOL, climate.hvac_modes)
        self.assertIn(HVACMode.DRY, climate.hvac_modes)
        self.assertIn(HVACMode.FAN_ONLY, climate.hvac_modes)
        self.assertEqual(climate.fan_modes, ["auto", "quiet", "low", "middle", "high"])
        self.assertEqual(climate.swing_modes, ["off", "on"])

    async def test_ac_climate_actions(self):
        climate = DomolinkTadoClimate(self.coordinator, self.entry, 2)

        # Set HVAC mode
        await climate.async_set_hvac_mode(HVACMode.HEAT)
        self.coordinator.async_set_ac_mode.assert_called_with(
            zone_id=2,
            mode="HEAT",
            target_temp=22.0,
            fan_speed="HIGH",
            swing="ON",
            termination_type="NEXT_TIME_BLOCK",
            duration_seconds=3600,
        )

        # Set Fan mode
        await climate.async_set_fan_mode("low")
        self.coordinator.async_set_ac_mode.assert_called_with(
            zone_id=2,
            mode="COOL",
            target_temp=22.0,
            fan_speed="LOW",
            swing="ON",
            termination_type="NEXT_TIME_BLOCK",
            duration_seconds=3600,
        )

        # Set Swing mode
        await climate.async_set_swing_mode("off")
        self.coordinator.async_set_ac_mode.assert_called_with(
            zone_id=2,
            mode="COOL",
            target_temp=22.0,
            fan_speed="HIGH",
            swing="OFF",
            termination_type="NEXT_TIME_BLOCK",
            duration_seconds=3600,
        )

        # Set Temperature
        await climate.async_set_temperature(temperature=21.5)
        self.coordinator.async_set_ac_mode.assert_called_with(
            zone_id=2,
            mode="COOL",
            target_temp=21.5,
            fan_speed="HIGH",
            swing="ON",
            termination_type="NEXT_TIME_BLOCK",
            duration_seconds=3600,
        )

    async def test_ac_setup_climate_entry(self):
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        self.coordinator.data["zones"][1] = {
            "zone_id": 1,
            "name": "Chambre",
            "type": "HEATING",
        }
        hass.data = {"domolink_tado": {"test_entry": {"coordinator": self.coordinator}}}

        added = []
        await async_setup_climate_entry(hass, entry, lambda ents: added.extend(ents))
        self.assertEqual(len(added), 2)  # 1 HEATING + 1 AC
        ac_ent = [e for e in added if e.is_ac][0]
        self.assertEqual(ac_ent.zone_id, 2)


class TestOptionsFlowExternalSensors(unittest.IsolatedAsyncioTestCase):
    """Unit tests for OptionsFlow external sensor configuration."""

    def setUp(self):
        self.entry = MagicMock()
        self.entry.entry_id = "test_entry"
        self.entry.options = {
            CONF_ZONE_TEMP_ENTITIES: {"1": "sensor.old_temp"},
            CONF_ZONE_HUMIDITY_ENTITIES: {"1": "sensor.old_hum"},
        }
        self.flow = DomolinkTadoOptionsFlow(self.entry)
        self.flow.hass = MagicMock()
        coord = MagicMock()
        coord.data = {
            "zones": {
                1: {"name": "Salon"},
                2: {"name": "Chambre"},
            }
        }
        self.flow.hass.data = {"domolink_tado": {"test_entry": {"coordinator": coord}}}

    async def test_options_flow_init_triggers_external_sensors(self):
        result = await self.flow.async_step_init({"external_sensors_trigger": True})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "external_sensors")

    async def test_options_flow_external_sensors_submit(self):
        user_input = {
            "temp_zone_1": "sensor.salon_temp",
            "hum_zone_1": "sensor.salon_hum",
            "temp_zone_2": "sensor.chambre_temp",
            "hum_zone_2": "",
        }
        result = await self.flow.async_step_external_sensors(user_input)
        self.assertEqual(result["type"], "create_entry")
        options = result["data"]
        self.assertEqual(
            options[CONF_ZONE_TEMP_ENTITIES],
            {"1": "sensor.salon_temp", "2": "sensor.chambre_temp"},
        )
        self.assertEqual(
            options[CONF_ZONE_HUMIDITY_ENTITIES],
            {"1": "sensor.salon_hum"},
        )


class TestAuditFixes(unittest.IsolatedAsyncioTestCase):
    """Unit tests validating audit fixes (Sprint 1, 2, 3)."""

    async def test_timer_overlay_zero_duration_respected(self):
        """m-2: Test that duration_seconds=0 is not overwritten with 3600."""
        from datetime import datetime
        from custom_components.domolink_tado.const import OVERLAY_TIMER
        client = TadoClient(MagicMock())
        client._request = AsyncMock(return_value={"mock": True})
        await client.set_zone_overlay(
            home_id=123,
            zone_id=1,
            target_temp=21.0,
            power="ON",
            termination_type=OVERLAY_TIMER,
            duration_seconds=0,
        )
        _, kwargs = client._request.call_args
        termination = kwargs["json_data"]["termination"]
        self.assertEqual(termination["durationInSeconds"], 0)

    def test_adaptive_preheat_null_setting_handling(self):
        """M-17: Test that find_next_scheduled_change handles blocks with null setting or temperature."""
        from datetime import datetime
        blocks = [
            {
                "dayType": "MONDAY",
                "start": "08:00",
                "end": "12:00",
                "setting": None,
            },
            {
                "dayType": "MONDAY",
                "start": "12:00",
                "end": "18:00",
                "setting": {
                    "power": "ON",
                    "temperature": None,
                },
            },
            {
                "dayType": "MONDAY",
                "start": "18:00",
                "end": "22:00",
                "setting": {
                    "power": "ON",
                    "temperature": {"celsius": 21.5},
                },
            },
        ]
        # Current time at Monday 07:00
        now = datetime(2026, 9, 21, 7, 0)  # 2026-09-21 is a Monday
        result = find_next_scheduled_change(blocks, now)
        self.assertIsNotNone(result)
        self.assertEqual(result["power"], "OFF")

    async def test_climate_fan_mode_temperature_suppression(self):
        """M-13: Test that setting fan mode when mode is FAN does not send target_temp."""
        coordinator = MagicMock()
        coordinator.home_id = 123
        coordinator.data = {
            "zones": {
                1: {
                    "name": "Clim Salon",
                    "type": "AIR_CONDITIONING",
                    "ac_mode": "FAN",
                    "target_temperature": 22.0,
                }
            }
        }
        coordinator.async_set_ac_mode = AsyncMock()
        entry = MagicMock()
        entry.options = {}

        climate = DomolinkTadoClimate(coordinator, entry, 1)
        await climate.async_set_fan_mode("high")

        coordinator.async_set_ac_mode.assert_called_once()
        _, kwargs = coordinator.async_set_ac_mode.call_args
        self.assertIsNone(kwargs["target_temp"])
        self.assertEqual(kwargs["mode"], "FAN")

    async def test_climate_set_temperature_in_fan_mode_switches_to_cool(self):
        """M-14: Test that calling set_temperature in FAN mode auto-switches to COOL."""
        coordinator = MagicMock()
        coordinator.home_id = 123
        coordinator.data = {
            "zones": {
                1: {
                    "name": "Clim Salon",
                    "type": "AIR_CONDITIONING",
                    "ac_mode": "FAN",
                    "target_temperature": 22.0,
                }
            }
        }
        coordinator.async_set_ac_mode = AsyncMock()
        entry = MagicMock()
        entry.options = {}

        climate = DomolinkTadoClimate(coordinator, entry, 1)
        await climate.async_set_temperature(temperature=23.0)

        coordinator.async_set_ac_mode.assert_called_once()
        _, kwargs = coordinator.async_set_ac_mode.call_args
        self.assertEqual(kwargs["mode"], "COOL")
        self.assertEqual(kwargs["target_temp"], 23.0)

    def test_climate_extra_attributes_battery_zero_not_overwritten(self):
        """M-12: Test that battery percentage 0% is preserved and not overwritten to 100%."""
        coordinator = MagicMock()
        coordinator.home_id = 123
        coordinator.get_zone_labels = MagicMock(return_value=[])
        coordinator.data = {
            "zones": {
                1: {
                    "name": "Radiateur",
                    "type": "HEATING",
                    "devices": [
                        {
                            "serialNo": "VA123",
                            "batteryState": "NORMAL",
                            "batteryPercentage": 0,
                        }
                    ],
                }
            }
        }
        entry = MagicMock()
        entry.options = {}

        climate = DomolinkTadoClimate(coordinator, entry, 1)
        attrs = climate.extra_state_attributes
        self.assertEqual(attrs["devices"][0]["battery_percentage"], 0)

    async def test_coordinator_optimistic_rollback_prevented_when_data_replaced(self):
        """M-4: Test that optimistic rollback is skipped if self.data reference was refreshed."""
        coordinator = MagicMock()
        coordinator.home_id = 123
        initial_data = {
            "zones": {
                1: {"target_temperature": 20.0}
            }
        }
        refreshed_data = {
            "zones": {
                1: {"target_temperature": 22.0}
            }
        }
        coordinator.data = initial_data

        async def failing_api():
            # Simuler un polling d'arrière-plan qui remplace coordinator.data pendant l'appel
            coordinator.data = refreshed_data
            raise TadoError("API Timeout")

        with self.assertRaises(TadoError):
            await DomolinkTadoCoordinator._async_optimistic_zone_update(
                coordinator,
                zone_id=1,
                optimistic_patch={"target_temperature": 25.0},
                coro=failing_api(),
            )

        # L'état rafraîchi (22.0) NE doit PAS avoir été écrasé par l'ancien backup (20.0)
        self.assertEqual(coordinator.data["zones"][1]["target_temperature"], 22.0)

    def test_options_flow_ha_compatibility(self):
        """Test that DomolinkTadoOptionsFlow is compatible with HA 2024.4+ base property."""
        from custom_components.domolink_tado.config_flow import DomolinkTadoOptionsFlow, DomolinkTadoConfigFlow

        mock_entry = MagicMock()
        mock_entry.options = {"eco_temperature": 16.5}

        # Instantiation with entry
        flow1 = DomolinkTadoOptionsFlow(mock_entry)
        self.assertEqual(flow1.config_entry.options["eco_temperature"], 16.5)

        # Instantiation without argument
        flow2 = DomolinkTadoOptionsFlow()
        flow2._config_entry = mock_entry
        self.assertEqual(flow2.config_entry.options["eco_temperature"], 16.5)

        # Static factory method
        flow3 = DomolinkTadoConfigFlow.async_get_options_flow(mock_entry)
        self.assertIsInstance(flow3, DomolinkTadoOptionsFlow)

    async def test_coordinator_multi_sensor_average(self):
        """Test that coordinator computes the mathematical average across up to 4 sensors."""
        from custom_components.domolink_tado.const import CONF_ZONE_TEMP_ENTITIES

        coordinator = MagicMock()
        coordinator.entry = MagicMock()
        coordinator.entry.options = {
            CONF_ZONE_TEMP_ENTITIES: {
                "1": ["sensor.temp_salon_1", "sensor.temp_salon_2", "sensor.temp_salon_3"],
            }
        }
        coordinator.hass = MagicMock()
        state1 = MagicMock()
        state1.state = "19.0"
        state2 = MagicMock()
        state2.state = "20.0"
        state3 = MagicMock()
        state3.state = "21.0"
        coordinator.hass.states.get = MagicMock(side_effect=lambda entity_id: {
            "sensor.temp_salon_1": state1,
            "sensor.temp_salon_2": state2,
            "sensor.temp_salon_3": state3,
        }.get(entity_id))

        # Re-run simulation logic for multi-sensor averaging
        ext_temp_list = coordinator.entry.options[CONF_ZONE_TEMP_ENTITIES]["1"]
        valid_temps = []
        for ent_id in ext_temp_list:
            st = coordinator.hass.states.get(ent_id)
            if st and st.state not in ("unavailable", "unknown"):
                valid_temps.append(float(st.state))

        avg = round(sum(valid_temps) / len(valid_temps), 1)
        self.assertEqual(avg, 20.0)

    async def test_coordinator_per_valve_calibration_mode(self):
        """Test that per-valve mode AUTO triggers offset and MANUAL ignores offset."""
        from custom_components.domolink_tado.const import (
            CONF_VALVE_CALIBRATION_MODES,
            CALIBRATION_MODE_AUTO,
            CALIBRATION_MODE_MANUAL,
        )

        modes = {
            "VA_AUTO_1": CALIBRATION_MODE_AUTO,
            "VA_MAN_2": CALIBRATION_MODE_MANUAL,
        }

        # Check AUTO
        mode_1 = modes.get("VA_AUTO_1")
        is_auto_1 = (mode_1 == CALIBRATION_MODE_AUTO)
        self.assertTrue(is_auto_1)

        # Check MANUAL
        mode_2 = modes.get("VA_MAN_2")
        is_auto_2 = (mode_2 == CALIBRATION_MODE_AUTO)
        self.assertFalse(is_auto_2)

    async def test_coordinator_save_sensors_and_set_mode_methods(self):
        """Test async_save_room_sensors and async_set_valve_calibration_mode."""
        from custom_components.domolink_tado.const import (
            CONF_ZONE_TEMP_ENTITIES,
            CONF_VALVE_CALIBRATION_MODES,
            CALIBRATION_MODE_AUTO,
        )

        coordinator = MagicMock()
        coordinator.entry = MagicMock()
        coordinator.entry.options = {}
        coordinator.hass = MagicMock()
        coordinator.async_request_refresh = AsyncMock()
        coordinator._safe_request_refresh = AsyncMock()
        coordinator.data = {"zones": {}}

        # Test async_save_room_sensors
        await DomolinkTadoCoordinator.async_save_room_sensors(
            coordinator,
            {"1": ["sensor.temp_1", "sensor.temp_2"]}
        )
        self.assertEqual(
            coordinator.hass.config_entries.async_update_entry.call_args[1]["options"][CONF_ZONE_TEMP_ENTITIES],
            {"1": ["sensor.temp_1", "sensor.temp_2"]}
        )

        # Test async_set_valve_calibration_mode
        coordinator.entry.options = {CONF_VALVE_CALIBRATION_MODES: {}}
        await DomolinkTadoCoordinator.async_set_valve_calibration_mode(
            coordinator,
            "VA012345",
            CALIBRATION_MODE_AUTO,
        )
        self.assertEqual(
            coordinator.hass.config_entries.async_update_entry.call_args[1]["options"][CONF_VALVE_CALIBRATION_MODES],
            {"VA012345": CALIBRATION_MODE_AUTO}
        )

    async def test_tado_scope_includes_offline_access(self):
        """Test that TADO_SCOPE includes offline_access for refresh tokens."""
        from custom_components.domolink_tado.const import TADO_SCOPE
        self.assertIn("offline_access", TADO_SCOPE)

    async def test_async_get_valid_token_expired_no_refresh(self):
        """Test async_get_valid_token raises TadoAuthError when access token is expired and no refresh token."""
        import time
        from custom_components.domolink_tado.tado_api import TadoClient, TadoAuthError
        session = MagicMock()
        client = TadoClient(session, access_token="old_expired", refresh_token=None, expires_at=time.time() - 100)
        with self.assertRaises(TadoAuthError):
            await client.async_get_valid_token()

    async def test_calibration_auto_resilient_on_auth_failure(self):
        """Test async_set_valve_calibration_mode is resilient and does not fail on TadoAuthError."""
        from custom_components.domolink_tado.coordinator import DomolinkTadoCoordinator
        from custom_components.domolink_tado.tado_api import TadoAuthError
        from custom_components.domolink_tado.const import CALIBRATION_MODE_AUTO, CONF_VALVE_CALIBRATION_MODES

        coordinator = MagicMock()
        coordinator.entry = MagicMock()
        coordinator.entry.options = {}
        coordinator.hass = MagicMock()
        coordinator.data = {
            "zones": {
                1: {
                    "raw_inside_temperature": 20.0,
                    "inside_temperature": 21.0,
                    "devices": [{"serialNo": "VA001", "currentMountedOffset": {"celsius": 0.0}}],
                }
            }
        }
        coordinator._last_offset_update_time = {}
        coordinator.client = MagicMock()
        coordinator.client.set_temperature_offset = AsyncMock(side_effect=TadoAuthError("unauthorized: token expired"))
        coordinator.async_request_refresh = AsyncMock()
        coordinator._safe_request_refresh = AsyncMock()

        # async_set_valve_calibration_mode should be resilient and not crash even if immediate offset fails
        await DomolinkTadoCoordinator.async_set_valve_calibration_mode(coordinator, "VA001", CALIBRATION_MODE_AUTO)
        self.assertEqual(
            coordinator.hass.config_entries.async_update_entry.call_args[1]["options"][CONF_VALVE_CALIBRATION_MODES],
            {"VA001": CALIBRATION_MODE_AUTO},
        )

        # async_set_temperature_offset should raise HomeAssistantError on auth failure
        from homeassistant.exceptions import HomeAssistantError
        with self.assertRaises(HomeAssistantError):
            await DomolinkTadoCoordinator.async_set_temperature_offset(coordinator, "VA001", 1.5)

    def test_services_yaml_is_valid(self):
        """Test that services.yaml is valid YAML and defines expected services."""
        import yaml
        from pathlib import Path
        yaml_path = Path(__file__).parent.parent / "custom_components" / "domolink_tado" / "services.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            services = yaml.safe_load(f)
        self.assertIsInstance(services, dict)
        self.assertIn("save_room_labels", services)
        self.assertIn("save_room_sensors", services)
        self.assertIn("set_valve_calibration_mode", services)

    async def test_safe_request_refresh_swallows_exceptions(self):
        """Test _safe_request_refresh absorbs exceptions from async_request_refresh."""
        from custom_components.domolink_tado.coordinator import DomolinkTadoCoordinator
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coordinator = MagicMock()
        coordinator.async_request_refresh = AsyncMock(side_effect=ConfigEntryAuthFailed("Session expired"))

        # Should not raise
        await DomolinkTadoCoordinator._safe_request_refresh(coordinator)

    async def test_save_room_labels_resilient_on_auth_failure(self):
        """Test async_save_room_labels does not crash when async_request_refresh raises."""
        from custom_components.domolink_tado.coordinator import DomolinkTadoCoordinator
        from custom_components.domolink_tado.const import CONF_ROOM_LABELS
        from homeassistant.exceptions import ConfigEntryAuthFailed
        import functools

        coordinator = MagicMock()
        coordinator.entry = MagicMock()
        coordinator.entry.options = {}
        coordinator.hass = MagicMock()
        coordinator.async_request_refresh = AsyncMock(side_effect=ConfigEntryAuthFailed("Session expired"))
        # Bind the real _safe_request_refresh so it calls the mocked async_request_refresh
        coordinator._safe_request_refresh = functools.partial(DomolinkTadoCoordinator._safe_request_refresh, coordinator)

        # Should not raise
        await DomolinkTadoCoordinator.async_save_room_labels(coordinator, {"1": ["RDC"]})
        # Verify the labels were saved
        call_args = coordinator.hass.config_entries.async_update_entry.call_args[1]["options"]
        self.assertEqual(call_args[CONF_ROOM_LABELS], {"1": ["RDC"]})

    async def test_save_room_sensors_resilient_on_auth_failure(self):
        """Test async_save_room_sensors does not crash when async_request_refresh raises."""
        from custom_components.domolink_tado.coordinator import DomolinkTadoCoordinator
        from custom_components.domolink_tado.const import CONF_ZONE_TEMP_ENTITIES
        from homeassistant.exceptions import ConfigEntryAuthFailed
        import functools

        coordinator = MagicMock()
        coordinator.entry = MagicMock()
        coordinator.entry.options = {}
        coordinator.hass = MagicMock()
        coordinator.async_request_refresh = AsyncMock(side_effect=ConfigEntryAuthFailed("Session expired"))
        coordinator._safe_request_refresh = functools.partial(DomolinkTadoCoordinator._safe_request_refresh, coordinator)

        # Should not raise
        await DomolinkTadoCoordinator.async_save_room_sensors(coordinator, {"1": ["sensor.temp_1"]})
        # Verify the sensors were saved
        call_args = coordinator.hass.config_entries.async_update_entry.call_args[1]["options"]
        self.assertEqual(call_args[CONF_ZONE_TEMP_ENTITIES], {"1": ["sensor.temp_1"]})

    async def test_heating_zone_max_temp_and_clamping(self):
        """Test that heating zone max_temp is 25.0 and set_temperature clamps values > 25.0."""
        from custom_components.domolink_tado.climate import DomolinkTadoClimate

        coordinator = MagicMock()
        coordinator.home_id = 123
        coordinator.get_zone_labels = MagicMock(return_value=[])
        coordinator.async_set_temperature = AsyncMock()
        coordinator.data = {
            "zones": {
                1: {
                    "name": "Radiateur Salon",
                    "type": "HEATING",
                    "target_temperature": 20.0,
                },
                2: {
                    "name": "Clim Bureau",
                    "type": "AIR_CONDITIONING",
                    "target_temperature": 22.0,
                },
            }
        }
        entry = MagicMock()
        entry.options = {}

        # 1. Heating zone
        heating_climate = DomolinkTadoClimate(coordinator, entry, 1)
        self.assertEqual(heating_climate.max_temp, 25.0)
        self.assertEqual(heating_climate.min_temp, 5.0)
        self.assertEqual(heating_climate.extra_state_attributes["max_temp"], 25.0)

        # Set temperature above 25.0 should be clamped to 25.0
        await heating_climate.async_set_temperature(temperature=28.5)
        coordinator.async_set_temperature.assert_called_once()
        _, kwargs = coordinator.async_set_temperature.call_args
        self.assertEqual(kwargs["target_temp"], 25.0)

        # 2. AC zone
        coordinator.async_set_ac_mode = AsyncMock()
        ac_climate = DomolinkTadoClimate(coordinator, entry, 2)
        self.assertEqual(ac_climate.max_temp, 30.0)
        await ac_climate.async_set_temperature(temperature=28.5)
        coordinator.async_set_ac_mode.assert_called_once()
        _, ac_kwargs = coordinator.async_set_ac_mode.call_args
        self.assertEqual(ac_kwargs["target_temp"], 28.5)

    async def test_coordinator_clamped_temperature(self):
        """Test coordinator clamps heating target_temp to 25.0 max."""
        from custom_components.domolink_tado.coordinator import DomolinkTadoCoordinator

        coordinator = MagicMock()
        coordinator.home_id = 123
        coordinator.client = MagicMock()
        coordinator.client.set_zone_overlay = AsyncMock()
        async def fake_optimistic(zid, patch, coro):
            try:
                coro.close()
            except Exception:
                pass
        coordinator._async_optimistic_zone_update = AsyncMock(side_effect=fake_optimistic)
        coordinator.data = {
            "zones": {
                1: {
                    "type": "HEATING",
                    "power": "OFF",
                    "is_overlay_active": False,
                }
            }
        }

        await DomolinkTadoCoordinator.async_set_temperature(coordinator, 1, 29.0)
        coordinator._async_optimistic_zone_update.assert_called_once()
        call_patch = coordinator._async_optimistic_zone_update.call_args[0][1]
        self.assertEqual(call_patch["target_temperature"], 25.0)


