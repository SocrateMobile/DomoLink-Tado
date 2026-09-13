"""Update platform for DomoLink-Tado integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from typing import Any

import aiohttp

from homeassistant.components import frontend
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    FRONTEND_FILE_NAME,
    FRONTEND_URL_PATH,
    NAME,
    PANEL_ICON,
    PANEL_NAME,
    PANEL_URL_PATH,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

GITHUB_REPO = "SocrateMobile/DomoLink-Tado"
GITHUB_LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_CHECK_INTERVAL = timedelta(hours=4)


def parse_semver(version_str: str) -> tuple[int, ...]:
    """Parse semver string into a comparable tuple of integers."""
    if not version_str:
        return (0, 0, 0)
    clean = re.sub(r"^[vV]", "", str(version_str).strip())
    parts: list[int] = []
    for chunk in clean.split("."):
        m = re.match(r"^(\d+)", chunk)
        if m:
            parts.append(int(m.group(1)))
        else:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the update entity for DomoLink-Tado."""
    entity = DomolinkTadoUpdateEntity(hass, entry)
    async_add_entities([entity], True)


class DomolinkTadoUpdateEntity(UpdateEntity):
    """Update entity to check for and install updates for DomoLink-Tado."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.RELEASE_NOTES
        | UpdateEntityFeature.PROGRESS
    )
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_name = "Mise à jour DomoLink-Tado"
        self._attr_unique_id = f"domolink_tado_update_{entry.entry_id}"
        self._attr_installed_version = VERSION
        self._attr_latest_version: str | None = VERSION
        self._attr_in_progress: bool | int = False
        self._release_body: str | None = None
        self._zip_download_url: str | None = None
        self._remove_timer: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_system")},
            name=f"{NAME} Système",
            manufacturer="Socrate Mobile",
            model="DomoLink Suite",
            sw_version=self._attr_installed_version,
        )

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant."""
        await super().async_added_to_hass()
        await self.async_update()

        async def _periodic_check(_now: Any) -> None:
            await self.async_update()
            self.async_write_ha_state()

        self._remove_timer = async_track_time_interval(
            self.hass, _periodic_check, UPDATE_CHECK_INTERVAL
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_timer:
            self._remove_timer()
            self._remove_timer = None
        await super().async_will_remove_from_hass()

    async def async_update(self) -> None:
        """Check GitHub for new releases."""
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(10):
                resp = await session.get(
                    GITHUB_LATEST_RELEASE_URL,
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp.status != 200:
                    _LOGGER.debug("GitHub API returned status %s for %s", resp.status, GITHUB_REPO)
                    return

                data = await resp.json()
                raw_tag: str = data.get("tag_name", "")
                tag = re.sub(r"^[vV]", "", raw_tag.strip())

                if not tag:
                    return

                self._attr_latest_version = tag
                self._release_body = data.get("body", "Nouvelle version disponible.")
                self._zip_download_url = data.get("zipball_url")

                has_update = (
                    parse_semver(self._attr_latest_version)
                    > parse_semver(self._attr_installed_version or "0.0.0")
                )
                self._update_sidebar_panel(has_update)

        except asyncio.TimeoutError:
            _LOGGER.debug("Timeout checking GitHub releases for DomoLink-Tado")
        except Exception as err:
            _LOGGER.warning("Error checking GitHub releases for DomoLink-Tado: %s", err)

    def _update_sidebar_panel(self, update_available: bool) -> None:
        """Update the Home Assistant left sidebar panel badge/title if registered."""
        try:
            title = f"{NAME} 🔴" if update_available else NAME
            icon = "mdi:shield-alert" if update_available else PANEL_ICON
            frontend.async_register_built_in_panel(
                self.hass,
                component_name="custom",
                sidebar_title=title,
                sidebar_icon=icon,
                frontend_url_path=PANEL_URL_PATH,
                config={
                    "_panel_custom": {
                        "name": PANEL_NAME,
                        "module_url": f"{FRONTEND_URL_PATH}/{FRONTEND_FILE_NAME}?v={self._attr_installed_version or VERSION}",
                    }
                },
                require_admin=False,
                update=True,
            )
        except Exception as err:
            _LOGGER.debug("Could not update DomoLink-Tado sidebar panel registration: %s", err)

    async def async_release_notes(self) -> str | None:
        """Return release notes in markdown."""
        return self._release_body

    async def async_install(
        self, version: str | None = None, backup: bool = True, **kwargs: Any
    ) -> None:
        """Download and install update, then restart Home Assistant."""
        if not self._zip_download_url:
            await self.async_update()

        if not self._zip_download_url:
            raise HomeAssistantError("Impossible de trouver l'archive de mise à jour sur GitHub.")

        self._attr_in_progress = True
        self.async_write_ha_state()

        session = async_get_clientsession(self.hass)
        temp_dir = tempfile.mkdtemp(prefix="domolink_tado_update_")
        zip_path = os.path.join(temp_dir, "release.zip")

        try:
            async with session.get(self._zip_download_url) as resp:
                if resp.status != 200:
                    raise HomeAssistantError(f"Échec de téléchargement de la mise à jour: {resp.status}")
                with open(zip_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)

            def _extract_and_copy() -> None:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(temp_dir)

                source_subfolder: str | None = None
                for root, dirs, _files in os.walk(temp_dir):
                    if os.path.basename(root) == "domolink_tado" and "custom_components" in root:
                        source_subfolder = root
                        break

                if not source_subfolder:
                    for entry_name in os.listdir(temp_dir):
                        full_entry = os.path.join(temp_dir, entry_name)
                        if os.path.isdir(full_entry) and entry_name != "__MACOSX":
                            candidate = os.path.join(full_entry, "custom_components", "domolink_tado")
                            if os.path.isdir(candidate):
                                source_subfolder = candidate
                                break

                if not source_subfolder:
                    raise HomeAssistantError("Structure d'archive invalide : dossier custom_components/domolink_tado introuvable.")

                target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
                for item in os.listdir(source_subfolder):
                    s = os.path.join(source_subfolder, item)
                    d = os.path.join(target_dir, item)
                    if os.path.isdir(s):
                        if os.path.exists(d):
                            shutil.rmtree(d)
                        shutil.copytree(s, d)
                    else:
                        shutil.copy2(s, d)

            await self.hass.async_add_executor_job(_extract_and_copy)
            _LOGGER.info("Mise à jour DomoLink-Tado extraite et installée avec succès.")

            self._attr_installed_version = self._attr_latest_version
            self._attr_in_progress = False
            self._update_sidebar_panel(False)
            self.async_write_ha_state()

            # Redémarrer Home Assistant pour activer la nouvelle version
            if self.hass.services.has_service("restart_ha", "start_process"):
                await self.hass.services.async_call("restart_ha", "start_process", {"action": "quick_restart"})
            else:
                await self.hass.services.async_call("homeassistant", "restart")

        except Exception as err:
            self._attr_in_progress = False
            self.async_write_ha_state()
            _LOGGER.error("Erreur lors de l'installation de la mise à jour: %s", err)
            raise HomeAssistantError(f"Erreur d'installation : {err}") from err
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
