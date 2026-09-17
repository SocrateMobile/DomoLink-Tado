"""Climate platform for DomoLink-Tado supporting Heating and Air Conditioning."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PRECISION_HALVES, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_OVERLAY_DURATION,
    CONF_OVERLAY_MODE,
    CONF_VALVE_CALIBRATION_MODES,
    CONF_ZONE_TEMP_ENTITIES,
    DEFAULT_OVERLAY_DURATION,
    DEFAULT_OVERLAY_MODE,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    TEMP_STEP,
)
from .coordinator import DomolinkTadoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DomoLink-Tado climate entities from a config entry."""
    coordinator: DomolinkTadoCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[DomolinkTadoClimate] = []
    zones = (coordinator.data or {}).get("zones", {})

    for zone_id, zone_data in zones.items():
        if zone_data.get("type") in ("HEATING", "AIR_CONDITIONING"):
            entities.append(DomolinkTadoClimate(coordinator, entry, zone_id))

    async_add_entities(entities)


class DomolinkTadoClimate(CoordinatorEntity[DomolinkTadoCoordinator], ClimateEntity):
    """Representation of a DomoLink-Tado climate zone/thermostat (Heating or Smart AC)."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_HALVES
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP

    def __init__(
        self,
        coordinator: DomolinkTadoCoordinator,
        entry: ConfigEntry,
        zone_id: int,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.zone_id = zone_id
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_zone_{zone_id}"
        self._attr_name = self._zone_data.get("name", f"Tado Zone {zone_id}")

    @property
    def _zone_data(self) -> dict[str, Any]:
        """Return cached data for this zone from coordinator."""
        return (self.coordinator.data or {}).get("zones", {}).get(self.zone_id, {})

    @property
    def is_ac(self) -> bool:
        """Return True if this zone is an Air Conditioning zone."""
        return self._zone_data.get("type") == "AIR_CONDITIONING"

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return supported features according to zone type."""
        base_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if self.is_ac:
            return (
                base_features
                | ClimateEntityFeature.FAN_MODE
                | ClimateEntityFeature.SWING_MODE
            )
        return base_features

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return available HVAC modes."""
        if self.is_ac:
            return [
                HVACMode.AUTO,
                HVACMode.COOL,
                HVACMode.HEAT,
                HVACMode.DRY,
                HVACMode.FAN_ONLY,
                HVACMode.OFF,
            ]
        return [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]

    @property
    def fan_modes(self) -> list[str] | None:
        """Return available fan modes for AC."""
        if not self.is_ac:
            return None
        return ["auto", "quiet", "low", "middle", "high"]

    @property
    def fan_mode(self) -> str | None:
        """Return current fan mode for AC."""
        if not self.is_ac:
            return None
        speed = self._zone_data.get("fan_speed") or "AUTO"
        return speed.lower()

    @property
    def swing_modes(self) -> list[str] | None:
        """Return available swing modes for AC."""
        if not self.is_ac:
            return None
        return ["off", "on"]

    @property
    def swing_mode(self) -> str | None:
        """Return current swing mode for AC."""
        if not self.is_ac:
            return None
        sw = self._zone_data.get("swing") or "OFF"
        return sw.lower()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for Home Assistant registry."""
        devices = self._zone_data.get("devices") or []
        primary_serial = devices[0].get("serialNo") if devices else f"zone_{self.zone_id}"
        default_model = "Smart AC Control" if self.is_ac else "Smart Radiator Valve"
        model = devices[0].get("deviceType", default_model) if devices else default_model

        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_{self.zone_id}")},
            name=f"Tado {self._zone_data.get('name', 'Zone')}",
            manufacturer="Tado (DomoLink)",
            model=model,
            serial_number=primary_serial,
            suggested_area=self._zone_data.get("name"),
        )

    @property
    def current_temperature(self) -> float | None:
        """Return current measured room temperature."""
        return self._zone_data.get("inside_temperature")

    @property
    def current_humidity(self) -> float | None:
        """Return current measured room humidity."""
        return self._zone_data.get("humidity")

    @property
    def target_temperature(self) -> float | None:
        """Return current target temperature."""
        return self._zone_data.get("target_temperature")

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        power = self._zone_data.get("power", "OFF")
        is_overlay = self._zone_data.get("is_overlay_active", False)

        if power == "OFF":
            return HVACMode.OFF

        if not self.is_ac:
            if is_overlay:
                return HVACMode.HEAT
            return HVACMode.AUTO

        if not is_overlay:
            return HVACMode.AUTO

        mode = (self._zone_data.get("ac_mode") or "COOL").upper()
        if mode == "HEAT":
            return HVACMode.HEAT
        if mode == "DRY":
            return HVACMode.DRY
        if mode == "FAN":
            return HVACMode.FAN_ONLY
        return HVACMode.COOL

    @property
    def hvac_action(self) -> HVACAction:
        """Return current running action."""
        power = self._zone_data.get("power", "OFF")
        if power == "OFF":
            return HVACAction.OFF

        if not self.is_ac:
            heating_power = float(self._zone_data.get("heating_power") or 0.0)
            if heating_power > 0:
                return HVACAction.HEATING
            return HVACAction.IDLE

        mode = (self._zone_data.get("ac_mode") or "COOL").upper()
        if mode == "HEAT":
            return HVACAction.HEATING
        if mode == "COOL":
            return HVACAction.COOLING
        if mode == "DRY":
            return HVACAction.DRYING
        if mode == "FAN":
            return HVACAction.FAN
        return HVACAction.IDLE

    @property
    def icon(self) -> str:
        """Return icon according to physical device type and zone type."""
        if self.is_ac:
            return "mdi:air-conditioner"
        devs = self._zone_data.get("devices", [])
        if devs:
            dtype = str(devs[0].get("deviceType") or devs[0].get("type") or "").upper()
            if dtype.startswith("RU") or dtype.startswith("ST"):
                return "mdi:thermostat"
            if dtype.startswith("SU"):
                return "mdi:thermometer-water"
            if dtype.startswith("BU") or dtype.startswith("EK"):
                return "mdi:boiler"
        return "mdi:radiator"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        z = self._zone_data
        devs = z.get("devices") or []
        primary_type = (devs[0].get("deviceType") or devs[0].get("type") or "VA01") if devs else "VA01"
        attrs: dict[str, Any] = {
            "zone_id": self.zone_id,
            "zone_type": z.get("type", "HEATING"),
            "heating_power_percentage": float(z.get("heating_power") or 0.0),
            "is_overlay_active": z.get("is_overlay_active", False),
            "open_window_detected": z.get("open_window", False),
            "tado_mode": (z.get("state") or {}).get("tadoMode"),
            "device_type": primary_type,
            "labels": self.coordinator.get_zone_labels(self.zone_id),
            "devices": [
                {
                    "serial": d.get("serialNo") or d.get("serial") or "N/A",
                    "type": d.get("deviceType") or d.get("type") or "VA01",
                    "device_type": d.get("deviceType") or d.get("type") or "VA01",
                    "battery": d.get("batteryState") or d.get("battery") or "NORMAL",
                    "battery_state": d.get("batteryState") or d.get("battery") or "NORMAL",
                    "battery_percentage": d.get("batteryPercentage") if d.get("batteryPercentage") is not None else (100 if (d.get("batteryState") or d.get("battery")) == "NORMAL" else 20),
                    "connection_state": d.get("connectionState", {}).get("value") if isinstance(d.get("connectionState"), dict) else (d.get("connectionState") or "CONNECTED"),
                    "firmware": d.get("currentFirmwareVersion") or d.get("firmware") or "v98.1",
                    "child_lock": d.get("childLockEnabled") or d.get("child_lock") or False,
                    "offset": (
                        float(d.get("currentMountedOffset", {}).get("celsius", 0.0))
                        if isinstance(d.get("currentMountedOffset"), dict)
                        else float(d.get("characteristics", {}).get("temperatureOffset", {}).get("celsius", 0.0))
                    ),
                }
                for d in devs
            ],
            "raw_inside_temperature": z.get("raw_inside_temperature"),
            "zone_temp_sensors": self.coordinator.entry.options.get(CONF_ZONE_TEMP_ENTITIES, {}).get(str(self.zone_id), []),
            "valve_calibration_modes": self.coordinator.entry.options.get(CONF_VALVE_CALIBRATION_MODES, {}),
        }
        if self.is_ac:
            attrs["ac_mode"] = z.get("ac_mode")
            attrs["fan_speed"] = z.get("fan_speed")
            attrs["swing"] = z.get("swing")
        if z.get("is_external_temp"):
            attrs["external_temperature_used"] = True
            attrs["raw_tado_temperature"] = z.get("raw_inside_temperature")
        if z.get("is_external_humidity"):
            attrs["external_humidity_used"] = True
            attrs["raw_tado_humidity"] = z.get("raw_humidity")
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        # m-7: Support hvac_mode in kwargs (HA convention for combined mode+temp)
        if "hvac_mode" in kwargs:
            await self.async_set_hvac_mode(kwargs["hvac_mode"])

        temp = kwargs.get("temperature")
        if temp is None:
            return

        overlay_mode = self.entry.options.get(CONF_OVERLAY_MODE, DEFAULT_OVERLAY_MODE)
        duration = self.entry.options.get(CONF_OVERLAY_DURATION, DEFAULT_OVERLAY_DURATION)

        if self.is_ac:
            curr_mode = self._zone_data.get("ac_mode") or "COOL"
            # M-14: FAN mode n'accepte pas de température → basculer en COOL
            if curr_mode == "FAN":
                curr_mode = "COOL"
            await self.coordinator.async_set_ac_mode(
                zone_id=self.zone_id,
                mode=curr_mode,
                target_temp=temp,
                fan_speed=self.fan_mode.upper() if self.fan_mode else "AUTO",
                swing=self.swing_mode.upper() if self.swing_mode else "OFF",
                termination_type=overlay_mode,
                duration_seconds=duration,
            )
        else:
            await self.coordinator.async_set_temperature(
                zone_id=self.zone_id,
                target_temp=temp,
                termination_type=overlay_mode,
                duration_seconds=duration,
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target HVAC mode."""
        if hvac_mode == HVACMode.AUTO:
            await self.coordinator.async_resume_schedule(self.zone_id)
            return

        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_zone_off(self.zone_id)
            return

        if not self.is_ac:
            if hvac_mode == HVACMode.HEAT:
                target = self.target_temperature or 20.0
                await self.async_set_temperature(temperature=target)
            return

        # AC Zone Mode handling
        tado_mode_map = {
            HVACMode.COOL: "COOL",
            HVACMode.HEAT: "HEAT",
            HVACMode.DRY: "DRY",
            HVACMode.FAN_ONLY: "FAN",
        }
        tado_mode = tado_mode_map.get(hvac_mode, "COOL")
        target = self.target_temperature or (22.0 if tado_mode != "HEAT" else 20.0)
        overlay_mode = self.entry.options.get(CONF_OVERLAY_MODE, DEFAULT_OVERLAY_MODE)
        duration = self.entry.options.get(CONF_OVERLAY_DURATION, DEFAULT_OVERLAY_DURATION)

        await self.coordinator.async_set_ac_mode(
            zone_id=self.zone_id,
            mode=tado_mode,
            target_temp=target if tado_mode != "FAN" else None,
            fan_speed=self.fan_mode.upper() if self.fan_mode else "AUTO",
            swing=self.swing_mode.upper() if self.swing_mode else "OFF",
            termination_type=overlay_mode,
            duration_seconds=duration,
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode for AC."""
        if not self.is_ac:
            return

        overlay_mode = self.entry.options.get(CONF_OVERLAY_MODE, DEFAULT_OVERLAY_MODE)
        duration = self.entry.options.get(CONF_OVERLAY_DURATION, DEFAULT_OVERLAY_DURATION)
        curr_mode = self._zone_data.get("ac_mode") or "COOL"
        target = self.target_temperature or 22.0

        await self.coordinator.async_set_ac_mode(
            zone_id=self.zone_id,
            mode=curr_mode,
            target_temp=target if curr_mode != "FAN" else None,
            fan_speed=fan_mode.upper(),
            swing=self.swing_mode.upper() if self.swing_mode else "OFF",
            termination_type=overlay_mode,
            duration_seconds=duration,
        )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing mode for AC."""
        if not self.is_ac:
            return

        overlay_mode = self.entry.options.get(CONF_OVERLAY_MODE, DEFAULT_OVERLAY_MODE)
        duration = self.entry.options.get(CONF_OVERLAY_DURATION, DEFAULT_OVERLAY_DURATION)
        curr_mode = self._zone_data.get("ac_mode") or "COOL"
        target = self.target_temperature or 22.0

        await self.coordinator.async_set_ac_mode(
            zone_id=self.zone_id,
            mode=curr_mode,
            target_temp=target if curr_mode != "FAN" else None,
            fan_speed=self.fan_mode.upper() if self.fan_mode else "AUTO",
            swing=swing_mode.upper(),
            termination_type=overlay_mode,
            duration_seconds=duration,
        )

    async def async_turn_on(self) -> None:
        """Turn on the climate entity."""
        await self.coordinator.async_resume_schedule(self.zone_id)

    async def async_turn_off(self) -> None:
        """Turn off the climate entity."""
        await self.coordinator.async_set_zone_off(self.zone_id)
