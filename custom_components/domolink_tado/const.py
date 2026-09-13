"""Constants for the DomoLink-Tado integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "domolink_tado"
NAME = "DomoLink-Tado"
VERSION = "1.0.0"

# Endpoints API Tado
TADO_AUTH_BASE = "https://auth.tado.com/oauth"
TADO_API_BASE = "https://my.tado.com/api/v2"
TADO_DEVICE_AUTH_URL = f"{TADO_AUTH_BASE}/device_authorization"
TADO_TOKEN_URL = f"{TADO_AUTH_BASE}/token"

# Client ID officiel Tado pour OAuth2 Device Flow
TADO_CLIENT_ID = "1211b988-ec98-4ac2-8563-787169f16bfa"
TADO_SCOPE = "home.user"

# Configuration Entry keys
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
CONF_HOME_ID = "home_id"
CONF_HOME_NAME = "home_name"
CONF_OVERLAY_MODE = "overlay_mode"
CONF_OVERLAY_DURATION = "overlay_duration"

# Overlay termination modes
OVERLAY_NEXT_TIME_BLOCK = "NEXT_TIME_BLOCK"  # Jusqu'au prochain changement de programmation
OVERLAY_MANUAL = "MANUAL"                    # Jusqu'à annulation manuelle
OVERLAY_TIMER = "TIMER"                      # Minuterie définie en secondes

DEFAULT_OVERLAY_MODE = OVERLAY_NEXT_TIME_BLOCK
DEFAULT_OVERLAY_DURATION = 3600  # 1 heure par défaut

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
