"""Shared pytest fixtures and Home Assistant mocks for DomoLink-Tado tests."""
import sys
import types
from unittest.mock import MagicMock

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
    ha_const.STATE_ON = "on"
    ha_const.STATE_OFF = "off"
    ha_const.STATE_UNAVAILABLE = "unavailable"
    ha_const.STATE_UNKNOWN = "unknown"
    class UnitOfTemperature:
        CELSIUS = "°C"
    ha_const.UnitOfTemperature = UnitOfTemperature
    class UnitOfTime:
        SECONDS = "s"
        MINUTES = "min"
        HOURS = "h"
        DAYS = "d"
    ha_const.UnitOfTime = UnitOfTime

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
        DURATION = "duration"
    class SensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"
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
    class Event:
        def __init__(self, event_type, data=None):
            self.event_type = event_type
            self.data = data or {}
    ha_core.Event = Event

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
    ha_service = make_pkg("homeassistant.helpers.service")
    ha_service.async_register_admin_service = MagicMock()
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
            self._listeners = {}
        def async_add_listener(self, update_callback, context=None):
            idx = len(self._listeners)
            self._listeners[idx] = update_callback
            return lambda: self._listeners.pop(idx, None)
        def async_update_listeners(self):
            for listener in list(self._listeners.values()):
                listener()
        def async_set_updated_data(self, data):
            self.data = data
            self.async_update_listeners()
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

    ha_event = make_pkg("homeassistant.helpers.event")
    ha_event.async_track_state_change_event = MagicMock(return_value=lambda: None)
    ha_event.async_call_later = MagicMock(return_value=lambda: None)

    ha_storage = make_pkg("homeassistant.helpers.storage")
    class Store:
        def __init__(self, hass, version, key):
            self.hass = hass
            self.version = version
            self.key = key
            self._data = None
        async def async_load(self):
            return self._data
        async def async_save(self, data):
            self._data = data
    ha_storage.Store = Store

    ha_flow = make_pkg("homeassistant.data_entry_flow")
    class AbortFlow(Exception): pass
    ha_flow.AbortFlow = AbortFlow
    ha_flow.FlowResult = dict
