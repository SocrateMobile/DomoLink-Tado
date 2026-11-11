import json
import os
from homeassistant.const import Platform

DOMAIN = "domolink_tado"
NAME = "DomoLink-Tado"

# Source unique de vérité : la version est lue directement depuis manifest.json (requis par HA & HACS)
_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "manifest.json")
try:
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as _f:
        VERSION = json.load(_f).get("version", "unknown")
except Exception:
    VERSION = "unknown"

# Endpoints API Tado
TADO_AUTH_BASE = "https://login.tado.com/oauth2"
TADO_API_BASE = "https://my.tado.com/api/v2"
TADO_DEVICE_AUTH_URL = f"{TADO_AUTH_BASE}/device_authorize"
TADO_TOKEN_URL = f"{TADO_AUTH_BASE}/token"

# Microservices Tado v10.9 (Rétro-ingénierie APK)
TADO_GRAPHQL_URL = "https://ext.api.tado.com/apps/graphql"
TADO_GRAPHQL_FALLBACK_URL = "https://app.tado.com/api/ext.api.tado.com/apps/graphql"
TADO_IVAR_GRAPHQL_URL = "https://ivar.tado.com/graphql"
TADO_IVAR_FALLBACK_URL = "https://app.tado.com/api/ivar.tado.com/graphql"
TADO_MINDER_API_URL = "https://minder.tado.com/v1"
TADO_MINDER_FALLBACK_URL = "https://app.tado.com/api/minder.tado.com/v1"
TADO_HOPS_API_URL = "https://hops.tado.com"
TADO_HOPS_FALLBACK_URL = "https://app.tado.com/api/hops.tado.com"

# Services Home Assistant spécifiques DomoLink-Tado
SERVICE_IDENTIFY_DEVICE = "identify_device"
SERVICE_REBOOT_DEVICE = "reboot_device"
SERVICE_SET_DEVICE_DAZZLE = "set_device_dazzle"
SERVICE_PAIR_LOCAL_BRIDGE = "pair_local_bridge"

# Client ID officiel Tado pour OAuth2 Device Flow
TADO_CLIENT_ID = "1bb50063-6b0c-4d11-bd99-387f4a91cc46"
TADO_SCOPE = "home.user offline_access"

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
CONF_ZONE_CONTACT_ENTITIES = "zone_contact_entities"
CONF_WINDOW_OPEN_DELAY = "window_open_delay"
CONF_WINDOW_CLOSE_DELAY = "window_close_delay"
CONF_WINDOW_MAX_DURATION = "window_max_duration"
CONF_WINDOW_RESTORE_MODE = "window_restore_mode"
CONF_USE_NATIVE_WINDOW = "use_native_window"
CONF_AUTO_OFFSET_CALIBRATION = "auto_offset_calibration"
CONF_VALVE_CALIBRATION_MODES = "valve_calibration_modes"
CONF_SHOW_QUOTA_SENSORS = "show_quota_sensors"
CONF_LOCAL_HOMEKIT_PIN = "local_homekit_pin"
CONF_ENABLE_LOCAL_PRIORITY = "enable_local_priority"

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
DEFAULT_WINDOW_OPEN_DELAY = 30  # 30 secondes avant coupure
DEFAULT_WINDOW_CLOSE_DELAY = 60  # 60 secondes après fermeture avant restauration
DEFAULT_WINDOW_MAX_DURATION = 1800  # 30 minutes max sécurité
WINDOW_RESTORE_RESUME = "RESUME"
WINDOW_RESTORE_PREVIOUS = "RESTORE_PREVIOUS"
DEFAULT_WINDOW_RESTORE_MODE = WINDOW_RESTORE_RESUME
DEFAULT_USE_NATIVE_WINDOW = False
EVENT_WINDOW_OPENED = "domolink_tado_window_opened"
EVENT_WINDOW_CLOSED = "domolink_tado_window_closed"
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
DEFAULT_ENABLE_LOCAL_PRIORITY = True
DEFAULT_LOCAL_HOMEKIT_PIN = ""
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
