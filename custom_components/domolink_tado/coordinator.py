"""DataUpdateCoordinator for DomoLink-Tado."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import time
from typing import Any, Callable, Coroutine

import aiohttp

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
    CONF_OUTDOOR_WEATHER_ENTITY,
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
from .physics import (
    calculate_absolute_humidity,
    calculate_dew_point,
    calculate_mold_risk_level,
    calculate_mold_risk_problem,
    calculate_ventilation_recommended,
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
        self._weather_raw: dict[str, Any] = {}
        self._last_weather_time: float = 0.0
        self._home_state_raw: dict[str, Any] = {}
        self._last_home_state_time: float = 0.0
        self._open_window_handled: dict[int, bool] = {}
        self._open_window_pending: set[int] = set()

    def get_zone_labels(self, zone_id: int | str) -> list[str]:
        """Return configured labels for a given zone ID."""
        labels_map = self.entry.options.get(CONF_ROOM_LABELS, {})
        res = labels_map.get(str(zone_id), [])
        if isinstance(res, str):
            return [s.strip() for s in res.split(",") if s.strip()]
        return res if isinstance(res, list) else []

    def _get_outdoor_conditions(self) -> tuple[float | None, float | None]:
        """Get outdoor temperature and humidity from configured HA entity or Tado weather."""
        outdoor_temp: float | None = None
        outdoor_humidity: float | None = None

        weather_entity = self.entry.options.get(CONF_OUTDOOR_WEATHER_ENTITY)
        if weather_entity and getattr(self.hass, "states", None):
            st = self.hass.states.get(weather_entity)
            if st and st.state not in ("unavailable", "unknown"):
                attrs = getattr(st, "attributes", {}) or {}
                if "temperature" in attrs:
                    try:
                        outdoor_temp = float(attrs["temperature"])
                    except (ValueError, TypeError):
                        pass
                if "humidity" in attrs:
                    try:
                        outdoor_humidity = float(attrs["humidity"])
                    except (ValueError, TypeError):
                        pass
                if outdoor_temp is None:
                    try:
                        outdoor_temp = float(st.state)
                    except (ValueError, TypeError):
                        pass

        if outdoor_temp is None and self._weather_raw:
            outdoor_temp = self._weather_raw.get("outsideTemperature", {}).get("celsius")
        if outdoor_humidity is None and self._weather_raw:
            h_val = self._weather_raw.get("humidity")
            if isinstance(h_val, dict):
                outdoor_humidity = h_val.get("percentage")
            elif h_val is not None:
                try:
                    outdoor_humidity = float(h_val)
                except (ValueError, TypeError):
                    pass

        return outdoor_temp, outdoor_humidity

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all zone states with smart metadata, weather, and presence caching."""
        try:
            now = time.time()
            # 1. Cache zones et matériel pendant 30 minutes pour éviter le rate limit Tado (429)
            if not self._zones_raw or not self._devices_raw or (now - self._last_discovery_time > 1800):
                try:
                    _LOGGER.debug("DomoLink-Tado: Découverte des zones et équipements...")
                    z_res, d_res = await asyncio.gather(
                        self.client.get_zones(self.home_id),
                        self.client.get_devices(self.home_id),
                    )
                    self._zones_raw = z_res or []
                    self._devices_raw = d_res or []
                    self._last_discovery_time = now
                except Exception as err:
                    _LOGGER.warning("DomoLink-Tado: Échec rafraîchissement zones/matériels (%s), utilisation cache", err)
                    if not self._zones_raw:
                        raise

            # 2. En routine : rafraîchir uniquement les états dynamiques de zones (1 seule requête API !)
            states_res = await self.client.get_zone_states(self.home_id)
            zone_states = (states_res or {}).get("zoneStates", {})

            # 3. Météo mise en cache pendant 15 minutes (900s)
            if not self._weather_raw or (now - self._last_weather_time > 900):
                try:
                    self._weather_raw = await self.client.get_weather(self.home_id) or {}
                    self._last_weather_time = now
                except Exception as err:
                    _LOGGER.debug("DomoLink-Tado: Échec rafraîchissement météo: %s", err)

            # 4. État du domicile (présence) mis en cache pendant 5 minutes (300s)
            if not self._home_state_raw or (now - self._last_home_state_time > 300):
                try:
                    self._home_state_raw = await self.client.get_home_state(self.home_id) or {}
                    self._last_home_state_time = now
                except Exception as err:
                    _LOGGER.debug("DomoLink-Tado: Échec rafraîchissement présence: %s", err)

            devices = self._devices_raw if isinstance(self._devices_raw, list) else []
            weather = self._weather_raw if isinstance(self._weather_raw, dict) else {}
            outdoor_temp, outdoor_humidity = self._get_outdoor_conditions()
            home_state = self._home_state_raw if isinstance(self._home_state_raw, dict) else {}

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
                if (
                    auto_window
                    and open_window
                    and not self._open_window_handled.get(zid, False)
                    and zid not in self._open_window_pending
                ):
                    self._open_window_pending.add(zid)
                    self.hass.async_create_task(
                        self._async_handle_open_window(
                            zid, z.get("name", f"Zone {zid}"), window_duration
                        )
                    )
                elif not open_window:
                    self._open_window_handled[zid] = False

                # Étiquettes de la pièce
                room_labels = labels_map.get(str(zid), [])
                if isinstance(room_labels, str):
                    room_labels = [lbl.strip() for lbl in room_labels.split(",") if lbl.strip()]

                # Calculs physiques locaux (100% hors-ligne, zéro coût API)
                dew_point = calculate_dew_point(inside_temp, humidity)
                absolute_humidity = calculate_absolute_humidity(inside_temp, humidity)
                mold_risk_level = calculate_mold_risk_level(inside_temp, humidity)
                mold_risk_problem = calculate_mold_risk_problem(inside_temp, humidity)
                ventilation_recommended = calculate_ventilation_recommended(
                    inside_temp, humidity, outdoor_temp, outdoor_humidity
                )

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
                    "dew_point": dew_point,
                    "absolute_humidity": absolute_humidity,
                    "mold_risk_level": mold_risk_level,
                    "mold_risk_problem": mold_risk_problem,
                    "ventilation_recommended": ventilation_recommended,
                    "devices": enhanced_devices,
                    "labels": room_labels,
                }

            # Polling adaptatif : 60s si chauffe active, 300s (5 min) si tout est au repos (respect quota Tado)
            adaptive = self.entry.options.get(CONF_ADAPTIVE_POLLING, True)
            if adaptive:
                new_interval = 60 if (active_heating_count > 0 or any(zd.get("is_overlay_active") for zd in zones_data.values())) else 300
                if self.update_interval != timedelta(seconds=new_interval):
                    self.update_interval = timedelta(seconds=new_interval)

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
                    "outdoor_humidity": outdoor_humidity,
                    "outdoor_dew_point": calculate_dew_point(outdoor_temp, outdoor_humidity),
                    "outdoor_absolute_humidity": calculate_absolute_humidity(outdoor_temp, outdoor_humidity),
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
        except (TadoError, aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
            if self.data:
                _LOGGER.warning(
                    "Erreur transitoire de communication avec Tado (%s). Conservation des dernières valeurs connues en cache.",
                    err,
                )
                return self.data
            raise UpdateFailed(f"Erreur de communication Tado: {err}") from err
        except Exception as err:
            _LOGGER.exception("Erreur inattendue lors de la mise à jour DomoLink-Tado: %s", err)
            raise UpdateFailed(f"Erreur inattendue: {err}") from err

    async def _async_handle_open_window(
        self, zone_id: int, zone_name: str, duration: int
    ) -> None:
        """Handle automatic heating cutoff for open window with error handling and retry."""
        try:
            _LOGGER.info(
                "DomoLink-Tado: Fenêtre ouverte détectée dans la pièce %s! Coupure automatique pendant %ss",
                zone_name,
                duration,
            )
            await self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zone_id,
                power="OFF",
                termination_type=OVERLAY_TIMER,
                duration_seconds=duration,
            )
            self._open_window_handled[zone_id] = True
        except Exception as err:
            _LOGGER.warning(
                "DomoLink-Tado: Échec de la coupure automatique pour fenêtre ouverte (zone %s: %s): %s. Nouvelle tentative au prochain cycle.",
                zone_id,
                zone_name,
                err,
            )
            self._open_window_handled[zone_id] = False
        finally:
            self._open_window_pending.discard(zone_id)

    # ── Actions ───────────────────────────────────────────────

    async def _async_optimistic_zone_update(
        self,
        zone_id: int,
        optimistic_patch: dict[str, Any],
        coro: Coroutine[Any, Any, Any],
    ) -> None:
        """Apply optimistic update to a zone with automatic rollback if the API call fails."""
        has_zone = bool(self.data and "zones" in self.data and zone_id in self.data["zones"])
        backup_state: dict[str, Any] | None = None

        if has_zone:
            backup_state = dict(self.data["zones"][zone_id])
            self.data["zones"][zone_id].update(optimistic_patch)
            self.async_set_updated_data(self.data)

        try:
            await coro
        except Exception as err:
            if has_zone and backup_state is not None:
                _LOGGER.warning(
                    "DomoLink-Tado: Échec de la commande sur la zone %s (%s). Annulation de la mise à jour optimiste.",
                    zone_id,
                    err,
                )
                self.data["zones"][zone_id].update(backup_state)
                self.async_set_updated_data(self.data)
            raise

    async def _async_execute_all_zones(
        self,
        action_name: str,
        optimistic_patch: dict[str, Any],
        call_fn: Callable[[int], Coroutine[Any, Any, Any]],
        concurrency: int = 2,
        target_zone_ids: list[int] | None = None,
    ) -> None:
        """Execute a batch command across all zones (or target subset) with optimistic update and controlled concurrency."""
        if target_zone_ids is not None:
            zone_ids = [zid for zid in target_zone_ids if (self.data and "zones" in self.data and zid in self.data["zones"])]
        else:
            zone_ids = list((self.data.get("zones", {})).keys()) if (self.data and "zones" in self.data) else []

        if not zone_ids:
            return

        # 1. Sauvegarde et mise à jour optimiste immédiate en mémoire
        backup: dict[int, dict[str, Any]] = {
            zid: dict(self.data["zones"][zid]) for zid in zone_ids if zid in self.data["zones"]
        }
        for zid in zone_ids:
            if zid in self.data["zones"]:
                self.data["zones"][zid].update(optimistic_patch)
        self.async_set_updated_data(self.data)

        sem = asyncio.Semaphore(concurrency)
        failed_zones: list[int] = []

        async def _worker(zid: int) -> None:
            async with sem:
                try:
                    await call_fn(zid)
                    await asyncio.sleep(0.05)
                except Exception as err:
                    _LOGGER.warning("DomoLink-Tado: Erreur lors de %s pour la zone %s: %s", action_name, zid, err)
                    failed_zones.append(zid)
                    if zid in backup:
                        self.data["zones"][zid].update(backup[zid])

        await asyncio.gather(*[_worker(zid) for zid in zone_ids])

        # Rafraîchir les données en cas de rollback partiel
        if failed_zones:
            self.async_set_updated_data(self.data)

    async def async_set_temperature(
        self,
        zone_id: int,
        target_temp: float,
        termination_type: str = OVERLAY_NEXT_TIME_BLOCK,
        duration_seconds: int | None = None,
    ) -> None:
        """Set temperature for a zone with immediate optimistic update and rollback."""
        rounded_temp = round(float(target_temp), 1)

        # Filtre anti-redondance local (supprime les requêtes API inutiles)
        current_zone = (self.data.get("zones", {})).get(zone_id) if self.data else None
        if current_zone:
            current_pwr = current_zone.get("power")
            current_overlay = current_zone.get("is_overlay_active")
            current_target = current_zone.get("target_temperature")
            if (
                current_pwr == "ON"
                and current_overlay
                and current_target is not None
                and abs(float(current_target) - rounded_temp) < 0.1
            ):
                _LOGGER.debug(
                    "DomoLink-Tado: Consigne identique déjà active sur la zone %s (%.1f°C). Appel API ignoré.",
                    zone_id,
                    rounded_temp,
                )
                return

        patch = {
            "target_temperature": rounded_temp,
            "power": "ON",
            "is_overlay_active": True,
        }
        await self._async_optimistic_zone_update(
            zone_id,
            patch,
            self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zone_id,
                target_temp=rounded_temp,
                power="ON",
                termination_type=termination_type,
                duration_seconds=duration_seconds,
            ),
        )

    async def async_set_zone_off(self, zone_id: int) -> None:
        """Turn heating off for a zone with immediate optimistic update and rollback."""
        # Filtre anti-redondance local
        current_zone = (self.data.get("zones", {})).get(zone_id) if self.data else None
        if current_zone and current_zone.get("power") == "OFF" and current_zone.get("is_overlay_active"):
            _LOGGER.debug(
                "DomoLink-Tado: Zone %s déjà éteinte (OFF). Appel API ignoré.",
                zone_id,
            )
            return

        patch = {
            "power": "OFF",
            "is_overlay_active": True,
        }
        await self._async_optimistic_zone_update(
            zone_id,
            patch,
            self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zone_id,
                power="OFF",
                termination_type=OVERLAY_MANUAL,
            ),
        )

    async def async_resume_schedule(self, zone_id: int) -> None:
        """Resume automatic schedule for a single zone with immediate optimistic update and rollback."""
        # Filtre anti-redondance local
        current_zone = (self.data.get("zones", {})).get(zone_id) if self.data else None
        if current_zone and not current_zone.get("is_overlay_active"):
            _LOGGER.debug(
                "DomoLink-Tado: Zone %s déjà sous planning automatique. Appel API ignoré.",
                zone_id,
            )
            return

        patch = {
            "is_overlay_active": False,
        }
        await self._async_optimistic_zone_update(
            zone_id,
            patch,
            self.client.resume_schedule(self.home_id, zone_id),
        )

    async def async_resume_all_schedules(self) -> None:
        """Resume automatic schedule across all zones with controlled concurrency."""
        zones = self.data.get("zones", {}) if self.data else {}
        zones_in_overlay = [zid for zid, zd in zones.items() if zd.get("is_overlay_active")]
        if not zones_in_overlay:
            _LOGGER.debug("DomoLink-Tado: Aucune zone en dérogation manuelle. Reprise globale ignorée.")
            return

        await self._async_execute_all_zones(
            action_name="reprise planning",
            optimistic_patch={"is_overlay_active": False},
            call_fn=lambda zid: self.client.resume_schedule(self.home_id, zid),
            target_zone_ids=zones_in_overlay,
        )

    async def async_set_all_off(self) -> None:
        """Turn off all heating zones with controlled concurrency."""
        zones = self.data.get("zones", {}) if self.data else {}
        zones_to_off = [
            zid for zid, zd in zones.items()
            if not (zd.get("power") == "OFF" and zd.get("is_overlay_active"))
        ]
        if not zones_to_off:
            _LOGGER.debug("DomoLink-Tado: Toutes les zones sont déjà éteintes. Extinction globale ignorée.")
            return

        await self._async_execute_all_zones(
            action_name="extinction",
            optimistic_patch={"power": "OFF", "is_overlay_active": True},
            call_fn=lambda zid: self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zid,
                power="OFF",
                termination_type=OVERLAY_MANUAL,
            ),
            target_zone_ids=zones_to_off,
        )

    async def async_set_boost(self, temp: float = 25.0, duration_seconds: int = 1800) -> None:
        """Boost all zones with controlled concurrency."""
        await self._async_execute_all_zones(
            action_name="boost",
            optimistic_patch={"target_temperature": temp, "power": "ON", "is_overlay_active": True},
            call_fn=lambda zid: self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zid,
                target_temp=temp,
                power="ON",
                termination_type=OVERLAY_TIMER,
                duration_seconds=duration_seconds,
            ),
        )

    async def async_set_eco_all(self, eco_temp: float | None = None) -> None:
        """Apply eco temperature across all zones with controlled concurrency."""
        temp = eco_temp or self.entry.options.get(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)
        await self._async_execute_all_zones(
            action_name="mode éco",
            optimistic_patch={"target_temperature": temp, "power": "ON", "is_overlay_active": True},
            call_fn=lambda zid: self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zid,
                target_temp=temp,
                power="ON",
                termination_type=OVERLAY_NEXT_TIME_BLOCK,
            ),
        )

    async def async_set_child_lock(self, device_serial: str, child_lock: bool) -> None:
        """Toggle physical child lock on a valve."""
        await self.client.set_child_lock(device_serial, child_lock)

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

