"""DataUpdateCoordinator for DomoLink-Tado."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ADAPTIVE_POLLING,
    CONF_AUTO_WINDOW_DURATION,
    CONF_AUTO_WINDOW_ENABLED,
    CONF_ECO_TEMP,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_OVERLAY_DURATION,
    CONF_OVERLAY_MODE,
    CONF_ROOM_LABELS,
    DEFAULT_AUTO_WINDOW_DURATION,
    DEFAULT_AUTO_WINDOW_ENABLED,
    DEFAULT_ECO_TEMP,
    DEFAULT_OVERLAY_MODE,
    DOMAIN,
    OVERLAY_MANUAL,
    OVERLAY_NEXT_TIME_BLOCK,
    OVERLAY_TIMER,
    UPDATE_INTERVAL_SECONDS,
)
from .tado_api import TadoAuthError, TadoClient, TadoError

_LOGGER = logging.getLogger(__name__)


class DomolinkTadoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Central data coordinator that fetches all Tado data and controls zones."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TadoClient,
        home_id: int,
        home_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{home_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.entry = entry
        self.client = client
        self.home_id = home_id
        self.home_name = home_name
        self._zones_raw: list[dict[str, Any]] = []
        self._devices_raw: list[dict[str, Any]] = []
        self._last_discovery_time: float = 0.0
        self._open_window_handled: dict[int, bool] = {}

    def get_zone_labels(self, zone_id: int | str) -> list[str]:
        """Return configured labels for a given zone ID."""
        labels_map = self.entry.options.get(CONF_ROOM_LABELS, {})
        res = labels_map.get(str(zone_id), [])
        if isinstance(res, str):
            return [s.strip() for s in res.split(",") if s.strip()]
        return res if isinstance(res, list) else []

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all zone states and weather with smart zones/devices metadata caching."""
        try:
            now = time.time()
            # Cache zones et matériel pendant 30 minutes pour éviter le rate limit Tado (429)
            if not self._zones_raw or not self._devices_raw or (now - self._last_discovery_time > 1800):
                try:
                    _LOGGER.debug("DomoLink-Tado: Découverte complète des zones et équipements...")
                    z_res, d_res = await asyncio.gather(
                        self.client.get_zones(self.home_id),
                        self.client.get_devices(self.home_id),
                    )
                    self._zones_raw = z_res or []
                    self._devices_raw = d_res or []
                    self._last_discovery_time = now
                except Exception as err:
                    _LOGGER.warning("DomoLink-Tado: Échec de rafraîchissement des zones/matériels (%s), utilisation du cache", err)
                    if not self._zones_raw:
                        raise

            # En routine : seulement les requêtes d'états dynamiques légères
            states_task = self.client.get_zone_states(self.home_id)
            weather_task = self.client.get_weather(self.home_id)
            home_state_task = self.client.get_home_state(self.home_id)

            states_res, weather_res, home_state_res = await asyncio.gather(
                states_task,
                weather_task,
                home_state_task,
                return_exceptions=True,
            )

            if isinstance(states_res, Exception):
                raise states_res

            zone_states = (states_res or {}).get("zoneStates", {})
            devices = self._devices_raw if isinstance(self._devices_raw, list) else []
            weather = weather_res if isinstance(weather_res, dict) else {}
            home_state = home_state_res if isinstance(home_state_res, dict) else {}

            # Map devices by zone and serial number
            devices_by_serial: dict[str, dict[str, Any]] = {
                dev.get("serialNo", ""): dev for dev in devices if dev.get("serialNo")
            }

            # Structure data per zone
            zones_data: dict[int, dict[str, Any]] = {}
            active_heating_count = 0
            total_heating_power = 0.0

            labels_map = self.entry.options.get(CONF_ROOM_LABELS, {})
            auto_window = self.entry.options.get(CONF_AUTO_WINDOW_ENABLED, DEFAULT_AUTO_WINDOW_ENABLED)
            window_duration = self.entry.options.get(CONF_AUTO_WINDOW_DURATION, DEFAULT_AUTO_WINDOW_DURATION)

            for z in self._zones_raw:
                zid = z.get("id")
                if zid is None:
                    continue

                z_state = zone_states.get(str(zid), {})
                z_devices = [
                    d for d in z.get("devices", [])
                    if d.get("serialNo") in devices_by_serial
                ]

                # Enhance zone devices with full device info (battery, childLock, connection)
                enhanced_devices = [
                    devices_by_serial.get(d.get("serialNo", ""), d) for d in z_devices
                ]

                # Extract heating metrics
                activity_data = z_state.get("activityDataPoints", {})
                heating_power = (
                    activity_data.get("heatingPower", {}).get("percentage", 0.0)
                    if activity_data
                    else 0.0
                )
                if heating_power > 0:
                    active_heating_count += 1
                total_heating_power += heating_power

                # Extract current measurement (temp & humidity)
                sensor_data = z_state.get("sensorDataPoints", {})
                inside_temp = (
                    sensor_data.get("insideTemperature", {}).get("celsius")
                    if sensor_data
                    else None
                )
                humidity = (
                    sensor_data.get("humidity", {}).get("percentage")
                    if sensor_data
                    else None
                )

                # Extract target setting & overlay
                setting = z_state.get("setting", {})
                overlay = z_state.get("overlay")
                target_temp = (
                    setting.get("temperature", {}).get("celsius")
                    if setting and setting.get("temperature")
                    else None
                )
                power = setting.get("power", "OFF") if setting else "OFF"

                # Open window detection
                open_window = z_state.get("openWindow") is not None

                # Bypass Auto-Assist: coupure automatique de la tête sur fenêtre ouverte
                if auto_window and open_window and not self._open_window_handled.get(zid, False):
                    self._open_window_handled[zid] = True
                    _LOGGER.info(
                        "DomoLink-Tado: Fenêtre ouverte détectée dans la pièce %s! Coupure automatique pendant %ss",
                        z.get("name"),
                        window_duration,
                    )
                    self.hass.async_create_task(
                        self.client.set_zone_overlay(
                            home_id=self.home_id,
                            zone_id=zid,
                            power="OFF",
                            termination_type=OVERLAY_TIMER,
                            duration_seconds=window_duration,
                        )
                    )
                elif not open_window and self._open_window_handled.get(zid, False):
                    self._open_window_handled[zid] = False

                # Étiquettes de la pièce
                room_labels = labels_map.get(str(zid), [])
                if isinstance(room_labels, str):
                    room_labels = [lbl.strip() for lbl in room_labels.split(",") if lbl.strip()]

                zones_data[zid] = {
                    "info": z,
                    "state": z_state,
                    "name": z.get("name", f"Zone {zid}"),
                    "zone_id": zid,
                    "type": z.get("type", "HEATING"),
                    "inside_temperature": inside_temp,
                    "humidity": humidity,
                    "target_temperature": target_temp,
                    "power": power,
                    "heating_power": heating_power,
                    "overlay": overlay,
                    "is_overlay_active": overlay is not None,
                    "open_window": open_window,
                    "devices": enhanced_devices,
                    "labels": room_labels,
                }

            # Polling adaptatif : 15s si chauffe active, 60s si tout est en veille
            adaptive = self.entry.options.get(CONF_ADAPTIVE_POLLING, True)
            if adaptive:
                new_interval = 15 if (active_heating_count > 0 or any(zd.get("is_overlay_active") for zd in zones_data.values())) else 60
                if self.update_interval != timedelta(seconds=new_interval):
                    self.update_interval = timedelta(seconds=new_interval)

            outdoor_temp = (
                weather.get("outsideTemperature", {}).get("celsius")
                if weather
                else None
            )
            weather_state = (
                weather.get("weatherState", {}).get("value")
                if weather
                else "CLEAR"
            )

            return {
                "home_id": self.home_id,
                "home_name": self.home_name,
                "zones": zones_data,
                "devices": devices_by_serial,
                "weather": {
                    "outdoor_temperature": outdoor_temp,
                    "weather_state": weather_state,
                    "solar_intensity": weather.get("solarIntensity", {}).get("percentage", 0),
                },
                "home_state": home_state,
                "presence": home_state.get("presence", "HOME"),
                "active_heating_zones": active_heating_count,
                "total_heating_power": total_heating_power,
                "last_update": datetime.now().isoformat(),
            }

        except TadoAuthError as err:
            _LOGGER.error("Erreur d'authentification auprès de Tado: %s", err)
            raise ConfigEntryAuthFailed(f"Session Tado expirée: {err}") from err
        except TadoError as err:
            if self.data:
                _LOGGER.warning("Erreur transitoire API Tado (%s). Conservation des dernières valeurs connues en cache.", err)
                return self.data
            raise UpdateFailed(f"Erreur API Tado: {err}") from err
        except Exception as err:
            if self.data:
                _LOGGER.warning("Erreur inattendue lors de la mise à jour Tado (%s). Utilisation du cache.", err)
                return self.data
            raise UpdateFailed(f"Erreur inattendue: {err}") from err

    # ── Actions ───────────────────────────────────────────────

    async def async_set_temperature(
        self,
        zone_id: int,
        target_temp: float,
        termination_type: str = OVERLAY_NEXT_TIME_BLOCK,
        duration_seconds: int | None = None,
    ) -> None:
        """Set temperature for a zone."""
        await self.client.set_zone_overlay(
            home_id=self.home_id,
            zone_id=zone_id,
            target_temp=target_temp,
            power="ON",
            termination_type=termination_type,
            duration_seconds=duration_seconds,
        )
        await self.async_request_refresh()

    async def async_set_zone_off(self, zone_id: int) -> None:
        """Turn heating off for a zone."""
        await self.client.set_zone_overlay(
            home_id=self.home_id,
            zone_id=zone_id,
            power="OFF",
            termination_type=OVERLAY_MANUAL,
        )
        await self.async_request_refresh()

    async def async_resume_schedule(self, zone_id: int) -> None:
        """Resume automatic schedule for a single zone."""
        await self.client.resume_schedule(self.home_id, zone_id)
        await self.async_request_refresh()

    async def async_resume_all_schedules(self) -> None:
        """Resume automatic schedule across all zones."""
        zone_ids = list((self.data.get("zones", {})).keys())
        await self.client.resume_all_schedules(self.home_id, zone_ids)
        await self.async_request_refresh()

    async def async_set_all_off(self) -> None:
        """Turn off all heating zones."""
        zone_ids = list((self.data.get("zones", {})).keys())
        await self.client.set_all_off(self.home_id, zone_ids)
        await self.async_request_refresh()

    async def async_set_boost(self, temp: float = 25.0, duration_seconds: int = 1800) -> None:
        """Boost all zones."""
        zone_ids = list((self.data.get("zones", {})).keys())
        await self.client.set_boost(self.home_id, zone_ids, temp=temp, duration_seconds=duration_seconds)
        await self.async_request_refresh()

    async def async_set_eco_all(self, eco_temp: float | None = None) -> None:
        """Apply eco temperature across all zones."""
        temp = eco_temp or self.entry.options.get(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)
        zone_ids = list((self.data.get("zones", {})).keys())
        tasks = [
            self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zid,
                target_temp=temp,
                power="ON",
                termination_type=OVERLAY_NEXT_TIME_BLOCK,
            )
            for zid in zone_ids
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.async_request_refresh()

    async def async_set_child_lock(self, device_serial: str, child_lock: bool) -> None:
        """Toggle physical child lock on a valve."""
        await self.client.set_child_lock(device_serial, child_lock)
        await self.async_request_refresh()

    async def async_set_presence(self, home: bool) -> None:
        """Set home presence lock (Home/Away)."""
        await self.client.set_presence(self.home_id, home)
        await self.async_request_refresh()

    async def async_set_temperature_offset(self, device_serial: str, offset: float) -> None:
        """Set calibration offset on a device."""
        await self.client.set_temperature_offset(device_serial, offset)
        await self.async_request_refresh()

    async def async_save_room_labels(self, labels_dict: dict[str, Any]) -> None:
        """Save room labels to config entry options."""
        current_options = dict(self.entry.options)
        current_options[CONF_ROOM_LABELS] = labels_dict
        self.hass.config_entries.async_update_entry(self.entry, options=current_options)
        await self.async_request_refresh()

