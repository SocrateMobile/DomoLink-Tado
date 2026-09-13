"""DataUpdateCoordinator for DomoLink-Tado."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOME_ID,
    CONF_HOME_NAME,
    DOMAIN,
    OVERLAY_NEXT_TIME_BLOCK,
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all zones, zone states, devices, weather, and home state from Tado."""
        try:
            # 1. Fetch zones metadata (cached / refreshed on each poll)
            zones_task = self.client.get_zones(self.home_id)
            states_task = self.client.get_zone_states(self.home_id)
            devices_task = self.client.get_devices(self.home_id)
            weather_task = self.client.get_weather(self.home_id)
            home_state_task = self.client.get_home_state(self.home_id)

            results = await asyncio.gather(
                zones_task,
                states_task,
                devices_task,
                weather_task,
                home_state_task,
                return_exceptions=True,
            )

            zones_res, states_res, devices_res, weather_res, home_state_res = results

            if isinstance(zones_res, Exception):
                raise zones_res
            if isinstance(states_res, Exception):
                raise states_res

            self._zones_raw = zones_res or []
            zone_states = (states_res or {}).get("zoneStates", {})

            devices = devices_res if isinstance(devices_res, list) else []
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
                }

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
            _LOGGER.error("Authentication error while updating Tado data: %s", err)
            raise UpdateFailed(f"Tado authentication failed: {err}") from err
        except TadoError as err:
            _LOGGER.warning("Tado API error during coordinator update: %s", err)
            raise UpdateFailed(f"Tado API error: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error updating DomoLink-Tado data: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}") from err

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
            termination_type=OVERLAY_NEXT_TIME_BLOCK,
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

    async def async_set_child_lock(self, device_serial: str, child_lock: bool) -> None:
        """Toggle physical child lock on a valve."""
        await self.client.set_child_lock(device_serial, child_lock)
        await self.async_request_refresh()

    async def async_set_presence(self, home: bool) -> None:
        """Set home presence lock (Home/Away)."""
        await self.client.set_presence(self.home_id, home)
        await self.async_request_refresh()
