"""Constants for the DomoLink-Tado integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "domolink_tado"
NAME = "DomoLink-Tado"
VERSION = "1.5.7"

# Endpoints API Tado
TADO_AUTH_BASE = "https://login.tado.com/oauth2"
TADO_API_BASE = "https://my.tado.com/api/v2"
TADO_DEVICE_AUTH_URL = f"{TADO_AUTH_BASE}/device_authorize"
TADO_TOKEN_URL = f"{TADO_AUTH_BASE}/token"

# Client ID officiel Tado pour OAuth2 Device Flow
TADO_CLIENT_ID = "1bb50063-6b0c-4d11-bd99-387f4a91cc46"
TADO_SCOPE = "home.user"

# Configuration Entry keys
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
CONF_HOME_ID = "home_id"
CONF_HOME_NAME = "home_name"
CONF_OVERLAY_MODE = "overlay_mode"
CONF_OVERLAY_DURATION = "overlay_duration"
CONF_ROOM_LABELS = "room_labels"
CONF_AUTO_WINDOW_ENABLED = "auto_window_enabled"
CONF_AUTO_WINDOW_DURATION = "auto_window_duration"
CONF_ECO_TEMP = "eco_temperature"
CONF_ADAPTIVE_POLLING = "adaptive_polling"
CONF_OUTDOOR_WEATHER_ENTITY = "outdoor_weather_entity"
CONF_PREHEAT_ENABLED = "preheat_enabled"
CONF_PREHEAT_MODE = "preheat_mode"
CONF_PREHEAT_MAX_DURATION = "preheat_max_duration"
CONF_DYNAMIC_WINDOW_DROP = "dynamic_window_drop"
CONF_AUTO_GEOFENCING_ENABLED = "auto_geofencing_enabled"
CONF_GEOFENCING_PERSONS = "geofencing_persons"
CONF_SMART_BOOST_TEMP = "smart_boost_temp"
CONF_SMART_BOOST_DURATION = "smart_boost_duration"
CONF_ZONE_TEMP_ENTITIES = "zone_temp_entities"
CONF_ZONE_HUMIDITY_ENTITIES = "zone_humidity_entities"
CONF_AUTO_OFFSET_CALIBRATION = "auto_offset_calibration"
CONF_VALVE_CALIBRATION_MODES = "valve_calibration_modes"
CONF_SHOW_QUOTA_SENSORS = "show_quota_sensors"

# Modes de calibration de température par vanne
CALIBRATION_MODE_AUTO = "AUTO"
CALIBRATION_MODE_MANUAL = "MANUAL"

# Modes de préchauffage
PREHEAT_MODE_ADVISORY = "ADVISORY"
PREHEAT_MODE_AUTONOMOUS = "AUTONOMOUS"

# Overlay termination modes
OVERLAY_NEXT_TIME_BLOCK = "NEXT_TIME_BLOCK"  # Jusqu'au prochain changement de programmation
OVERLAY_MANUAL = "MANUAL"                    # Jusqu'à annulation manuelle
OVERLAY_TIMER = "TIMER"                      # Minuterie définie en secondes

DEFAULT_OVERLAY_MODE = OVERLAY_NEXT_TIME_BLOCK
DEFAULT_OVERLAY_DURATION = 3600  # 1 heure par défaut
DEFAULT_AUTO_WINDOW_ENABLED = True
DEFAULT_AUTO_WINDOW_DURATION = 900  # 15 minutes
DEFAULT_ECO_TEMP = 17.0
DEFAULT_ADAPTIVE_POLLING = True
DEFAULT_PREHEAT_ENABLED = False
DEFAULT_PREHEAT_MODE = PREHEAT_MODE_ADVISORY
DEFAULT_PREHEAT_MAX_DURATION = 90  # 90 minutes max par défaut
DEFAULT_DYNAMIC_WINDOW_DROP = True
DEFAULT_HEATING_RATE = 1.5  # 1.5 °C/heure par défaut pour un radiateur à eau chaude standard
DEFAULT_AUTO_GEOFENCING_ENABLED = False
DEFAULT_GEOFENCING_PERSONS = ""
DEFAULT_SMART_BOOST_TEMP = 22.0
DEFAULT_SMART_BOOST_DURATION = 1800  # 30 minutes
DEFAULT_AUTO_OFFSET_CALIBRATION = False
DEFAULT_SHOW_QUOTA_SENSORS = True
OFFSET_MIN_STEP = 0.5  # Écart minimal en °C pour déclencher une mise à jour d'offset
OFFSET_UPDATE_COOLDOWN = 1800  # 30 minutes minimum entre deux mises à jour d'offset par appareil

# Vitesses et volets Climatisation (Smart AC)
FAN_SPEED_AUTO = "AUTO"
FAN_SPEED_QUIET = "QUIET"
FAN_SPEED_LOW = "LOW"
FAN_SPEED_MIDDLE = "MIDDLE"
FAN_SPEED_HIGH = "HIGH"
SWING_ON = "ON"
SWING_OFF = "OFF"

# Températures limites
MIN_TEMP = 5.0
MAX_TEMP = 30.0
TEMP_STEP = 0.5

# Plateformes HA
PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.WATER_HEATER,
    Platform.UPDATE,
]

# Frontend Panel
FRONTEND_URL_PATH = "/domolink_tado_panel"
FRONTEND_FILE_NAME = "domolink_tado-panel.js"
PANEL_TITLE = "DomoLink-Tado"
PANEL_ICON = "mdi:radiator"
PANEL_NAME = "domolink-tado-panel"
PANEL_URL_PATH = "domolink_tado"

# Polling intervals (5 minutes to preserve Tado API daily quota)
UPDATE_INTERVAL_SECONDS = 300
