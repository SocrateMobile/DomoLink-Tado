"""DomoLink-Tado — Intégration avancée et pérenne pour vos équipements Tado."""
from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:
    StaticPathConfig = None  # type: ignore[misc,assignment]

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    FRONTEND_FILE_NAME,
    FRONTEND_URL_PATH,
    NAME,
    PANEL_ICON,
    PANEL_NAME,
    PANEL_URL_PATH,
    PLATFORMS,
    VERSION,
)
from .coordinator import DomolinkTadoCoordinator
from .tado_api import TadoClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DomoLink-Tado from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    access_token = entry.data.get(CONF_ACCESS_TOKEN)
    refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
    expires_at = entry.data.get(CONF_EXPIRES_AT, 0.0)
    home_id = entry.data.get(CONF_HOME_ID)
    home_name = entry.data.get(CONF_HOME_NAME, "Tado Home")

    # Callback pour persister immédiatement tout jeton rafraîchi dans core.config_entries
    async def async_token_updated(tokens: dict[str, Any]) -> None:
        _LOGGER.info("DomoLink-Tado: Écriture persistante des jetons rafraîchis dans le stockage HA.")
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: tokens["access_token"],
                CONF_REFRESH_TOKEN: tokens["refresh_token"],
                CONF_EXPIRES_AT: tokens["expires_at"],
            },
        )

    client = TadoClient(
        session=session,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        token_update_callback=async_token_updated,
    )

    coordinator = DomolinkTadoCoordinator(
        hass=hass,
        entry=entry,
        client=client,
        home_id=home_id,
        home_name=home_name,
    )

    # Premier rafraîchissement avec tolérance au démarrage (ConfigEntryNotReady)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "DomoLink-Tado: Échec de connexion initiale aux serveurs Tado (%s). Nouvelle tentative automatique en arrière-plan...",
            err,
        )
        raise ConfigEntryNotReady(f"Serveurs Tado temporairement indisponibles: {err}") from err

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    # Charger toutes les plateformes d'entités
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 1. Enregistrer le chemin statique pour le frontend
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    if os.path.exists(frontend_dir):
        if hasattr(hass.http, "async_register_static_paths") and StaticPathConfig is not None:
            try:
                await hass.http.async_register_static_paths(
                    [StaticPathConfig(FRONTEND_URL_PATH, frontend_dir, cache_headers=False)]
                )
            except Exception as err:
                _LOGGER.debug("Erreur async_register_static_paths: %s", err)
        elif hasattr(hass.http, "register_static_path"):
            try:
                hass.http.register_static_path(FRONTEND_URL_PATH, frontend_dir, cache_headers=False)
            except Exception as err:
                _LOGGER.debug("Erreur register_static_path: %s", err)

    # 2. Enregistrer le panneau latéral Home Assistant
    panel_url = f"{FRONTEND_URL_PATH}/{FRONTEND_FILE_NAME}?v={VERSION}"
    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=NAME,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            config={
                "_panel_custom": {
                    "name": PANEL_NAME,
                    "module_url": panel_url,
                }
            },
            require_admin=False,
            update=True,
        )
        _LOGGER.info("DomoLink-Tado: Panneau latéral enregistré avec succès.")
    except Exception as err:
        _LOGGER.debug("Panneau latéral DomoLink-Tado déjà enregistré ou erreur: %s", err)

    # 3. Enregistrer les services DomoLink-Tado
    async def handle_resume_all(call: ServiceCall) -> None:
        """Reprendre le planning sur toutes les pièces."""
        await coordinator.async_resume_all_schedules()

    async def handle_all_off(call: ServiceCall) -> None:
        """Mettre tout le chauffage hors-gel / éteint."""
        await coordinator.async_set_all_off()

    async def handle_boost(call: ServiceCall) -> None:
        """Activer le mode Boost sur toutes les pièces."""
        temp = call.data.get("temperature", 25.0)
        duration = call.data.get("duration", 1800)
        await coordinator.async_set_boost(temp=temp, duration_seconds=duration)

    async def handle_child_lock(call: ServiceCall) -> None:
        """Activer ou désactiver la sécurité enfant sur une tête."""
        serial = call.data.get("device_serial")
        locked = call.data.get("locked", True)
        if serial:
            await coordinator.async_set_child_lock(serial, locked)

    async def handle_presence(call: ServiceCall) -> None:
        """Définir la présence globale (Home/Away)."""
        home = call.data.get("home", True)
        await coordinator.async_set_presence(home)

    if not hass.services.has_service(DOMAIN, "resume_all_schedules"):
        hass.services.async_register(DOMAIN, "resume_all_schedules", handle_resume_all)
    if not hass.services.has_service(DOMAIN, "set_all_off"):
        hass.services.async_register(DOMAIN, "set_all_off", handle_all_off)
    if not hass.services.has_service(DOMAIN, "set_boost"):
        hass.services.async_register(DOMAIN, "set_boost", handle_boost)
    if not hass.services.has_service(DOMAIN, "set_child_lock"):
        hass.services.async_register(DOMAIN, "set_child_lock", handle_child_lock)
    if not hass.services.has_service(DOMAIN, "set_presence"):
        hass.services.async_register(DOMAIN, "set_presence", handle_presence)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload DomoLink-Tado config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload DomoLink-Tado config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
