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
    ha_coord.DataUpdateCoordinator = DataUpdateCoordinator
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


if __name__ == "__main__":
    unittest.main()
