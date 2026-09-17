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
    CONF_AUTO_GEOFENCING_ENABLED,
    CONF_AUTO_OFFSET_CALIBRATION,
    CONF_AUTO_WINDOW_DURATION,
    CONF_AUTO_WINDOW_ENABLED,
    CONF_DYNAMIC_WINDOW_DROP,
    CONF_ECO_TEMP,
    CONF_GEOFENCING_PERSONS,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_OUTDOOR_WEATHER_ENTITY,
    CONF_OVERLAY_DURATION,
    CONF_OVERLAY_MODE,
    CONF_PREHEAT_ENABLED,
    CONF_PREHEAT_MAX_DURATION,
    CONF_PREHEAT_MODE,
    CONF_ROOM_LABELS,
    CONF_SMART_BOOST_DURATION,
    CONF_SMART_BOOST_TEMP,
    CONF_ZONE_HUMIDITY_ENTITIES,
    CONF_ZONE_TEMP_ENTITIES,
    DEFAULT_AUTO_GEOFENCING_ENABLED,
    DEFAULT_AUTO_OFFSET_CALIBRATION,
    DEFAULT_AUTO_WINDOW_DURATION,
    DEFAULT_AUTO_WINDOW_ENABLED,
    DEFAULT_DYNAMIC_WINDOW_DROP,
    DEFAULT_ECO_TEMP,
    DEFAULT_GEOFENCING_PERSONS,
    DEFAULT_HEATING_RATE,
    DEFAULT_OVERLAY_MODE,
    DEFAULT_PREHEAT_ENABLED,
    DEFAULT_PREHEAT_MAX_DURATION,
    DEFAULT_PREHEAT_MODE,
    DEFAULT_SMART_BOOST_DURATION,
    DEFAULT_SMART_BOOST_TEMP,
    DOMAIN,
    OFFSET_MIN_STEP,
    OFFSET_UPDATE_COOLDOWN,
    OVERLAY_MANUAL,
    OVERLAY_NEXT_TIME_BLOCK,
    OVERLAY_TIMER,
    PREHEAT_MODE_AUTONOMOUS,
    UPDATE_INTERVAL_SECONDS,
)
from .adaptive_preheat import (
    detect_rapid_temperature_drop,
    estimate_preheat_duration,
    find_next_scheduled_change,
    update_heating_rate,
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
        self._zone_temp_history: dict[int, list[tuple[float, float]]] = {}
        self._zone_heating_rates: dict[int, float] = {}
        self._zone_heating_sessions: dict[int, dict[str, Any]] = {}
        self._zone_schedules_raw: dict[int, list[dict[str, Any]]] = {}
        self._last_schedule_fetch_time: dict[int, float] = {}
        self._preheat_triggered: dict[int, bool] = {}
        self._last_offset_update_time: dict[str, float] = {}
        self._consecutive_failures: int = 0

    def _create_safe_task(self, coro: Coroutine[Any, Any, Any], task_name: str = "tado_task") -> asyncio.Task[Any]:
        """Create a background task with error logging to avoid unretrieved exceptions."""
        async def _wrapper() -> None:
            try:
                await coro
            except Exception as err:
                _LOGGER.warning("DomoLink-Tado: Erreur dans la tâche d'arrière-plan %s: %s", task_name, err)

        return self.hass.async_create_task(_wrapper())

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
                    if not self._zones_raw or not self._devices_raw:
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
            dynamic_window = self.entry.options.get(CONF_DYNAMIC_WINDOW_DROP, DEFAULT_DYNAMIC_WINDOW_DROP)
            preheat_enabled = self.entry.options.get(CONF_PREHEAT_ENABLED, DEFAULT_PREHEAT_ENABLED)
            preheat_mode = self.entry.options.get(CONF_PREHEAT_MODE, DEFAULT_PREHEAT_MODE)
            max_preheat_dur = self.entry.options.get(CONF_PREHEAT_MAX_DURATION, DEFAULT_PREHEAT_MAX_DURATION)

            # M-6: Pré-chargement asynchrone et concurrent des plannings si préchauffe active
            if preheat_enabled:
                zones_needing_sched = [
                    z.get("id") for z in self._zones_raw
                    if z.get("id") is not None
                    and (not self._zone_schedules_raw.get(z.get("id")) or (now - self._last_schedule_fetch_time.get(z.get("id"), 0.0) > 21600))
                ]
                if zones_needing_sched:
                    async def _fetch_zone_sched(zone_id: int) -> None:
                        try:
                            active_tt = await self.client.get_active_timetable(self.home_id, zone_id)
                            if active_tt and "id" in active_tt:
                                blocks = await self.client.get_timetable_blocks(self.home_id, zone_id, active_tt["id"])
                                if blocks is not None:
                                    self._zone_schedules_raw[zone_id] = blocks
                                    self._last_schedule_fetch_time[zone_id] = now
                        except Exception as err:
                            _LOGGER.debug("DomoLink-Tado: Impossible de charger le planning pour la zone %s: %s", zone_id, err)

                    await asyncio.gather(*[_fetch_zone_sched(zid) for zid in zones_needing_sched], return_exceptions=True)

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

                raw_inside_temp = inside_temp
                raw_humidity = humidity
                is_external_temp = False
                is_external_hum = False

                temp_entities = self.entry.options.get(CONF_ZONE_TEMP_ENTITIES, {})
                hum_entities = self.entry.options.get(CONF_ZONE_HUMIDITY_ENTITIES, {})
                auto_offset_calib = self.entry.options.get(
                    CONF_AUTO_OFFSET_CALIBRATION, DEFAULT_AUTO_OFFSET_CALIBRATION
                )

                # Remplacement par capteur de température externe Home Assistant (Priorité Confort)
                ext_temp_ent = temp_entities.get(str(zid))
                if ext_temp_ent and getattr(self.hass, "states", None):
                    st = self.hass.states.get(ext_temp_ent)
                    if st and st.state not in ("unavailable", "unknown"):
                        try:
                            inside_temp = float(st.state)
                            is_external_temp = True
                        except (ValueError, TypeError):
                            pass

                # Remplacement par capteur d'humidité externe Home Assistant
                ext_hum_ent = hum_entities.get(str(zid))
                if ext_hum_ent and getattr(self.hass, "states", None):
                    st = self.hass.states.get(ext_hum_ent)
                    if st and st.state not in ("unavailable", "unknown"):
                        try:
                            humidity = float(st.state)
                            is_external_hum = True
                        except (ValueError, TypeError):
                            pass

                # Auto-calibrage physique des têtes thermostatiques par capteur externe (anti-battement 0.5°C & cooldown 30min)
                if (
                    auto_offset_calib
                    and is_external_temp
                    and raw_inside_temp is not None
                    and inside_temp is not None
                ):
                    temp_diff = float(inside_temp) - float(raw_inside_temp)
                    for d in enhanced_devices:
                        serial = d.get("serialNo")
                        if not serial:
                            continue

                        curr_offset = 0.0
                        if "currentMountedOffset" in d and isinstance(d["currentMountedOffset"], dict):
                            curr_offset = float(d["currentMountedOffset"].get("celsius", 0.0))
                        elif "characteristics" in d and isinstance(d["characteristics"], dict):
                            curr_offset = float(d["characteristics"].get("temperatureOffset", {}).get("celsius", 0.0))

                        new_offset = round(max(-5.0, min(5.0, curr_offset + temp_diff)), 1)
                        if abs(new_offset - curr_offset) >= OFFSET_MIN_STEP:
                            last_calib = self._last_offset_update_time.get(serial, 0.0)
                            if now - last_calib >= OFFSET_UPDATE_COOLDOWN:
                                self._last_offset_update_time[serial] = now
                                _LOGGER.info(
                                    "DomoLink-Tado: Auto-calibrage offset physique %s (zone %s) : actuel=%.1f°C -> nouveau=%.1f°C (diff=%.1f°C)",
                                    serial,
                                    zid,
                                    curr_offset,
                                    new_offset,
                                    temp_diff,
                                )
                                self._create_safe_task(
                                    self.async_set_temperature_offset(serial, new_offset, refresh=False),
                                    task_name=f"offset_{serial}",
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
                ac_mode = setting.get("mode") if setting else None
                fan_speed = setting.get("fanSpeed") if setting else None
                swing = setting.get("swing") if setting else None

                # Open window detection native Tado
                open_window = z_state.get("openWindow") is not None

                # Détection dynamique locale de chute brutale de température (fenêtre ouverte rapide)
                rapid_drop = False
                if inside_temp is not None:
                    history = self._zone_temp_history.setdefault(zid, [])
                    history.append((now, float(inside_temp)))
                    # Conservation de l'historique sur 10 minutes (600s)
                    self._zone_temp_history[zid] = [(t, v) for t, v in history if now - t <= 600]
                    if dynamic_window:
                        rapid_drop = detect_rapid_temperature_drop(
                            self._zone_temp_history[zid], threshold_drop=0.5, max_seconds=300.0
                        )

                # Coupure automatique de sécurité si fenêtre ouverte (Tado natif ou Chute brutale locale)
                window_cutoff_condition = open_window or (dynamic_window and rapid_drop and heating_power > 0)
                if (
                    auto_window
                    and window_cutoff_condition
                    and not self._open_window_handled.get(zid, False)
                    and zid not in self._open_window_pending
                ):
                    self._open_window_pending.add(zid)
                    self.hass.async_create_task(
                        self._async_handle_open_window(
                            zid, z.get("name", f"Zone {zid}"), window_duration
                        )
                    )
                elif not open_window and not (dynamic_window and rapid_drop):
                    self._open_window_handled[zid] = False

                # Apprentissage automatique de la vitesse de chauffe réelle (°C/h) par EMA
                current_rate = self._zone_heating_rates.get(zid, DEFAULT_HEATING_RATE)
                if inside_temp is not None:
                    if heating_power > 20:
                        if zid not in self._zone_heating_sessions:
                            self._zone_heating_sessions[zid] = {"time": now, "temp": float(inside_temp)}
                        else:
                            session = self._zone_heating_sessions[zid]
                            duration_h = (now - session["time"]) / 3600.0
                            if duration_h >= 2.0:
                                if float(inside_temp) > session["temp"]:
                                    current_rate = update_heating_rate(
                                        current_rate, session["temp"], float(inside_temp), duration_h
                                    )
                                    self._zone_heating_rates[zid] = current_rate
                                self._zone_heating_sessions[zid] = {"time": now, "temp": float(inside_temp)}
                    else:
                        if zid in self._zone_heating_sessions:
                            session = self._zone_heating_sessions.pop(zid)
                            duration_h = (now - session["time"]) / 3600.0
                            if duration_h >= 0.2 and float(inside_temp) > session["temp"]:
                                current_rate = update_heating_rate(
                                    current_rate, session["temp"], float(inside_temp), duration_h
                                )
                                self._zone_heating_rates[zid] = current_rate
                                _LOGGER.debug(
                                    "DomoLink-Tado: Vitesse de chauffe actualisée zone %s: %.2f °C/h",
                                    zid,
                                    current_rate,
                                )

                # Récupération du planning de la zone (mis en cache 6h pour respecter les quotas API)
                timetable_blocks = self._zone_schedules_raw.get(zid, [])
                last_sched_time = self._last_schedule_fetch_time.get(zid, 0.0)
                if preheat_enabled and (not timetable_blocks or (now - last_sched_time > 21600)):
                    try:
                        active_tt = await self.client.get_active_timetable(self.home_id, zid)
                        if active_tt and "id" in active_tt:
                            blocks = await self.client.get_timetable_blocks(
                                self.home_id, zid, active_tt["id"]
                            )
                            if blocks is not None:
                                self._zone_schedules_raw[zid] = blocks
                                self._last_schedule_fetch_time[zid] = now
                                timetable_blocks = blocks
                    except Exception as err:
                        _LOGGER.debug(
                            "DomoLink-Tado: Impossible de charger le planning pour la zone %s: %s",
                            zid,
                            err,
                        )

                # Calcul de la préchauffe adaptative locale
                preheat_now = False
                preheat_advisor: str | None = None
                preheat_duration = 0
                preheat_target_temp: float | None = None

                if preheat_enabled and timetable_blocks:
                    current_dt = datetime.now()
                    next_change = find_next_scheduled_change(timetable_blocks, current_dt)
                    if next_change and next_change.get("power") == "ON" and next_change.get("target_temp") is not None:
                        sched_target = float(next_change["target_temp"])
                        if inside_temp is not None and sched_target > float(inside_temp):
                            preheat_duration = estimate_preheat_duration(
                                sched_target, float(inside_temp), current_rate, max_preheat_dur
                            )
                            if preheat_duration > 0:
                                start_preheat_dt = next_change["start_dt"] - timedelta(minutes=preheat_duration)
                                preheat_advisor = start_preheat_dt.isoformat()
                                preheat_target_temp = sched_target

                                if current_dt >= start_preheat_dt and current_dt < next_change["start_dt"]:
                                    preheat_now = True

                                # Mode autonome : application automatique de la consigne anticipée
                                if preheat_mode == PREHEAT_MODE_AUTONOMOUS and preheat_now:
                                    if not self._preheat_triggered.get(zid, False):
                                        self._preheat_triggered[zid] = True
                                        _LOGGER.info(
                                            "DomoLink-Tado: Démarrage préchauffe autonome zone %s -> %.1f°C (%s min d'avance)",
                                            zid,
                                            sched_target,
                                            preheat_duration,
                                        )
                                        self._create_safe_task(
                                            self.async_set_temperature(
                                                zid,
                                                target_temp=sched_target,
                                                termination_type=OVERLAY_NEXT_TIME_BLOCK,
                                            ),
                                            task_name=f"preheat_{zid}",
                                        )
                                elif not preheat_now:
                                    self._preheat_triggered[zid] = False

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
                    "raw_inside_temperature": raw_inside_temp,
                    "humidity": humidity,
                    "raw_humidity": raw_humidity,
                    "is_external_temp": is_external_temp,
                    "is_external_humidity": is_external_hum,
                    "target_temperature": target_temp,
                    "power": power,
                    "heating_power": heating_power,
                    "ac_mode": ac_mode,
                    "fan_speed": fan_speed,
                    "swing": swing,
                    "overlay": overlay,
                    "is_overlay_active": overlay is not None,
                    "open_window": open_window,
                    "rapid_window_drop": rapid_drop,
                    "heating_rate": current_rate,
                    "preheat_advisor": preheat_advisor,
                    "preheat_duration": preheat_duration,
                    "preheat_target_temp": preheat_target_temp,
                    "preheat_now": preheat_now,
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

            presence_val = home_state.get("presence", "HOME")
            self._check_automated_geofencing(presence_val)

            # Succès : réinitialiser le compteur d'échecs consécutifs
            self._consecutive_failures = 0

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
                "presence": presence_val,
                "active_heating_zones": active_heating_count,
                "total_heating_power": total_heating_power,
                "rate_limit": self.client.rate_limit_info,
                "last_update": datetime.now().isoformat(),
            }

        except TadoAuthError as err:
            _LOGGER.error("Erreur d'authentification auprès de Tado: %s", err)
            raise ConfigEntryAuthFailed(f"Session Tado expirée: {err}") from err
        except (TadoError, aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
            self._consecutive_failures += 1
            if self.data and self._consecutive_failures <= 3:
                _LOGGER.warning(
                    "Erreur transitoire de communication avec Tado (%s). Conservation des dernières valeurs connues en cache (%d/3).",
                    err,
                    self._consecutive_failures,
                )
                return self.data
            raise UpdateFailed(f"Erreur de communication Tado ({self._consecutive_failures} échecs consécutifs): {err}") from err
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
        original_data = self.data
        has_zone = bool(self.data and "zones" in self.data and zone_id in self.data["zones"])
        backup_state: dict[str, Any] | None = None

        if has_zone:
            backup_state = dict(self.data["zones"][zone_id])
            self.data["zones"][zone_id].update(optimistic_patch)
            self.async_set_updated_data(self.data)

        try:
            await coro
        except Exception as err:
            # M-4: Ne restaurer le backup QUE si self.data n'a pas été remplacé par un rafraîchissement d'arrière-plan
            if has_zone and backup_state is not None:
                _LOGGER.warning(
                    "DomoLink-Tado: Échec de la commande sur la zone %s (%s). Annulation de la mise à jour optimiste.",
                    zone_id,
                    err,
                )
                if self.data is original_data and "zones" in self.data and zone_id in self.data["zones"]:
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
        original_data = self.data
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
                    # M-4: Ne restaurer QUE si self.data n'a pas été remplacé par un rafraîchissement global
                    if self.data is original_data and zid in backup and zid in self.data.get("zones", {}):
                        self.data["zones"][zid].update(backup[zid])

        await asyncio.gather(*[_worker(zid) for zid in zone_ids])

        # Rafraîchir les données en cas de rollback partiel
        if failed_zones and self.data is original_data:
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

    async def async_set_ac_mode(
        self,
        zone_id: int,
        mode: str | None = None,
        target_temp: float | None = None,
        fan_speed: str | None = None,
        swing: str | None = None,
        power: str = "ON",
        termination_type: str = OVERLAY_NEXT_TIME_BLOCK,
        duration_seconds: int | None = None,
    ) -> None:
        """Set AC mode, fan speed, swing, and temperature with optimistic update."""
        rounded_temp = round(float(target_temp), 1) if target_temp is not None else None
        patch: dict[str, Any] = {
            "power": power,
            "is_overlay_active": True,
        }
        if mode is not None:
            patch["ac_mode"] = mode.upper()
        if rounded_temp is not None:
            patch["target_temperature"] = rounded_temp
        if fan_speed is not None:
            patch["fan_speed"] = fan_speed.upper()
        if swing is not None:
            patch["swing"] = swing.upper()

        await self._async_optimistic_zone_update(
            zone_id,
            patch,
            self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zone_id,
                target_temp=rounded_temp,
                power=power,
                termination_type=termination_type,
                duration_seconds=duration_seconds,
                zone_type="AIR_CONDITIONING",
                mode=mode.upper() if mode else "COOL",
                fan_speed=fan_speed.upper() if fan_speed else "AUTO",
                swing=swing.upper() if swing else "OFF",
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
        """Set home presence lock (Home/Away) with local redundancy check."""
        target_state = "HOME" if home else "AWAY"
        current_state = self.data.get("presence") if self.data else None
        if current_state == target_state:
            _LOGGER.debug(
                "DomoLink-Tado: Présence déjà sur %s. Appel API ignoré (filtre anti-redondance).",
                target_state,
            )
            return

        _LOGGER.info("DomoLink-Tado: Bascule de présence du domicile -> %s", target_state)
        if self.data:
            self.data["presence"] = target_state
            self.async_set_updated_data(self.data)

        await self.client.set_presence(self.home_id, home)
        self._last_home_state_time = 0.0

    def _check_automated_geofencing(self, current_presence: str | None = None) -> None:
        """Check Home Assistant person or zone states and automatically sync Tado presence if enabled."""
        if not self.entry.options.get(CONF_AUTO_GEOFENCING_ENABLED, DEFAULT_AUTO_GEOFENCING_ENABLED):
            return

        if not hasattr(self.hass, "states") or self.hass.states is None:
            return

        persons_str = str(
            self.entry.options.get(CONF_GEOFENCING_PERSONS, DEFAULT_GEOFENCING_PERSONS)
        ).strip()
        tracked_entities = [p.strip() for p in persons_str.split(",") if p.strip()]

        target_home: bool | None = None

        if tracked_entities:
            states = [self.hass.states.get(ent) for ent in tracked_entities]
            valid_states = [s for s in states if s is not None and s.state not in ("unknown", "unavailable")]
            if valid_states:
                # If ANY tracked entity is "home" or "on", someone is home
                if any(s.state.lower() in ("home", "on") for s in valid_states):
                    target_home = True
                else:
                    target_home = False
        else:
            # Fallback: inspect zone.home count
            zone_home = self.hass.states.get("zone.home")
            if zone_home and zone_home.state not in ("unknown", "unavailable"):
                try:
                    count = int(float(zone_home.state))
                    target_home = count > 0
                except (ValueError, TypeError):
                    pass

        if target_home is not None:
            target_state = "HOME" if target_home else "AWAY"
            eff_current = current_presence or (self.data.get("presence") if self.data else None)
            if eff_current and eff_current != target_state:
                _LOGGER.info(
                    "DomoLink-Tado: Geofencing automatique HA -> bascule de présence vers %s",
                    target_state,
                )
                self._create_safe_task(
                    self.async_set_presence(target_home),
                    task_name="geofencing_set_presence",
                )

    async def async_smart_boost(
        self,
        target_temp: float | None = None,
        duration_seconds: int | None = None,
        target_zone_ids: list[int] | None = None,
    ) -> None:
        """Boost heating across all zones (or target subset) for a temporary duration."""
        boost_temp = (
            float(target_temp)
            if target_temp is not None
            else float(self.entry.options.get(CONF_SMART_BOOST_TEMP, DEFAULT_SMART_BOOST_TEMP))
        )
        boost_dur = (
            int(duration_seconds)
            if duration_seconds is not None
            else int(self.entry.options.get(CONF_SMART_BOOST_DURATION, DEFAULT_SMART_BOOST_DURATION))
        )
        _LOGGER.info(
            "DomoLink-Tado: Lancement Smart Boost -> %.1f°C pendant %ds",
            boost_temp,
            boost_dur,
        )
        patch = {
            "target_temperature": boost_temp,
            "power": "ON",
            "is_overlay_active": True,
        }
        await self._async_execute_all_zones(
            f"Smart Boost {boost_temp}°C ({boost_dur}s)",
            patch,
            lambda zid: self.client.set_zone_overlay(
                home_id=self.home_id,
                zone_id=zid,
                target_temp=boost_temp,
                power="ON",
                termination_type=OVERLAY_TIMER,
                duration_seconds=boost_dur,
            ),
            target_zone_ids=target_zone_ids,
        )

    async def async_set_zone_boost(
        self,
        zone_id: int,
        target_temp: float | None = None,
        duration_seconds: int | None = None,
    ) -> None:
        """Boost a single zone for a temporary duration."""
        boost_temp = (
            float(target_temp)
            if target_temp is not None
            else float(self.entry.options.get(CONF_SMART_BOOST_TEMP, DEFAULT_SMART_BOOST_TEMP))
        )
        boost_dur = (
            int(duration_seconds)
            if duration_seconds is not None
            else int(self.entry.options.get(CONF_SMART_BOOST_DURATION, DEFAULT_SMART_BOOST_DURATION))
        )
        await self.async_set_temperature(
            zone_id,
            target_temp=boost_temp,
            termination_type=OVERLAY_TIMER,
            duration_seconds=boost_dur,
        )

    async def async_set_water_heater_temperature(
        self, zone_id: int, target_temp: float
    ) -> None:
        """Set target water temperature for a hot water zone."""
        await self.async_set_temperature(
            zone_id,
            target_temp=target_temp,
            termination_type=OVERLAY_NEXT_TIME_BLOCK,
        )

    async def async_set_water_heater_mode(
        self, zone_id: int, mode: str
    ) -> None:
        """Set operation mode for a hot water zone (auto, off, heat)."""
        if mode == "off":
            await self.async_set_zone_off(zone_id)
        elif mode == "auto":
            await self.async_resume_schedule(zone_id)
        elif mode == "heat":
            current_target = (
                self.data.get("zones", {}).get(zone_id, {}).get("target_temperature")
                if self.data
                else None
            )
            temp = float(current_target) if current_target is not None else 55.0
            await self.async_set_temperature(
                zone_id, target_temp=temp, termination_type=OVERLAY_NEXT_TIME_BLOCK
            )

    async def async_set_temperature_offset(
        self, device_serial: str, offset: float, refresh: bool = True
    ) -> None:
        """Set calibration offset on a device."""
        await self.client.set_temperature_offset(device_serial, offset)
        if refresh:
            await self.async_request_refresh()

    async def async_save_room_labels(self, labels_dict: dict[str, Any]) -> None:
        """Save room labels to config entry options."""
        current_options = dict(self.entry.options)
        current_options[CONF_ROOM_LABELS] = labels_dict
        self.hass.config_entries.async_update_entry(self.entry, options=current_options)
        await self.async_request_refresh()

