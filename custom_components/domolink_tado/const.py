"""Constants for the DomoLink-Tado integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "domolink_tado"
NAME = "DomoLink-Tado"
VERSION = "1.1.5"

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
    Platform.UPDATE,
]

# Frontend Panel
FRONTEND_URL_PATH = "/domolink_tado_panel"
FRONTEND_FILE_NAME = "domolink_tado-panel.js"
PANEL_TITLE = "DomoLink-Tado"
PANEL_ICON = "mdi:radiator"
PANEL_NAME = "domolink-tado-panel"
PANEL_URL_PATH = "domolink_tado"

# Polling intervals
UPDATE_INTERVAL_SECONDS = 30
