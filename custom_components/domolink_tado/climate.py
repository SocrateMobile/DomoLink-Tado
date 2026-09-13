"""Climate platform for DomoLink-Tado."""
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
    zones = coordinator.data.get("zones", {})

    for zone_id, zone_data in zones.items():
        if zone_data.get("type") == "HEATING":
            entities.append(DomolinkTadoClimate(coordinator, entry, zone_id))

    async_add_entities(entities)


class DomolinkTadoClimate(CoordinatorEntity[DomolinkTadoCoordinator], ClimateEntity):
    """Representation of a DomoLink-Tado climate zone/thermostat."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_HALVES
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

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
        return self.coordinator.data.get("zones", {}).get(self.zone_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for Home Assistant registry."""
        devices = self._zone_data.get("devices", [])
        primary_serial = devices[0].get("serialNo") if devices else f"zone_{self.zone_id}"
        model = devices[0].get("deviceType", "Smart Radiator Valve") if devices else "Tado Zone"

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
        if is_overlay:
            return HVACMode.HEAT
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction:
        """Return current running action (heating or idle)."""
        power = self._zone_data.get("power", "OFF")
        heating_power = self._zone_data.get("heating_power", 0.0)

        if power == "OFF":
            return HVACAction.OFF
        if heating_power > 0:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def icon(self) -> str:
        """Return icon according to physical device type."""
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
        devs = z.get("devices", [])
        primary_type = (devs[0].get("deviceType") or devs[0].get("type") or "VA01") if devs else "VA01"
        return {
            "zone_id": self.zone_id,
            "heating_power_percentage": z.get("heating_power", 0.0),
            "is_overlay_active": z.get("is_overlay_active", False),
            "open_window_detected": z.get("open_window", False),
            "tado_mode": z.get("state", {}).get("tadoMode"),
            "device_type": primary_type,
            "labels": self.coordinator.get_zone_labels(self.zone_id),
            "devices": [
                {
                    "serial": d.get("serialNo") or d.get("serial") or "N/A",
                    "type": d.get("deviceType") or d.get("type") or "VA01",
                    "device_type": d.get("deviceType") or d.get("type") or "VA01",
                    "battery": d.get("batteryState") or d.get("battery") or "NORMAL",
                    "battery_state": d.get("batteryState") or d.get("battery") or "NORMAL",
                    "battery_percentage": d.get("batteryPercentage") or (100 if (d.get("batteryState") or d.get("battery")) == "NORMAL" else 20),
                    "connection_state": d.get("connectionState", {}).get("value") if isinstance(d.get("connectionState"), dict) else (d.get("connectionState") or "CONNECTED"),
                    "firmware": d.get("currentFirmwareVersion") or d.get("firmware") or "v98.1",
                    "child_lock": d.get("childLockEnabled") or d.get("child_lock") or False,
                }
                for d in devs
            ],
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get("temperature")
        if temp is None:
            return

        overlay_mode = self.entry.options.get(CONF_OVERLAY_MODE, DEFAULT_OVERLAY_MODE)
        duration = self.entry.options.get(CONF_OVERLAY_DURATION, DEFAULT_OVERLAY_DURATION)

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
        elif hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_zone_off(self.zone_id)
        elif hvac_mode == HVACMode.HEAT:
            target = self.target_temperature or 20.0
            await self.async_set_temperature(temperature=target)
