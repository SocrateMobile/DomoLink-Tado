"""Support for Tado Domestic Hot Water (DHW) as water_heater entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DomolinkTadoCoordinator

_LOGGER = logging.getLogger(__name__)

# Modes de fonctionnement d'eau chaude sanitaire (alignés sur l'intégration Tado officielle)
MODE_AUTO = "auto"
MODE_HEAT = "heat"
MODE_OFF = "off"

# Alias rétrocompatibles
STATE_AUTO = MODE_AUTO
STATE_HEAT = MODE_HEAT
STATE_OFF = MODE_OFF

SUPPORTED_OPERATIONS = [MODE_AUTO, MODE_HEAT, MODE_OFF]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DomoLink-Tado water heater entities from config entry."""
    coordinator: DomolinkTadoCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    added_water_heaters: set[int] = set()

    def _check_and_add_water_heaters() -> None:
        new_water_heaters: list[DomolinkTadoWaterHeater] = []
        zones = (coordinator.data or {}).get("zones", {})

        for zone_id, zone_data in zones.items():
            if zone_id not in added_water_heaters and zone_data.get("type") in ("HOT_WATER", "DOMESTIC_HOT_WATER"):
                new_water_heaters.append(DomolinkTadoWaterHeater(coordinator, zone_id))
                added_water_heaters.add(zone_id)

        if new_water_heaters:
            async_add_entities(new_water_heaters)

    _check_and_add_water_heaters()
    entry.async_on_unload(coordinator.async_add_listener(_check_and_add_water_heaters))



class DomolinkTadoWaterHeater(CoordinatorEntity[DomolinkTadoCoordinator], WaterHeaterEntity):
    """Représentation d'un circuit d'eau chaude sanitaire Tado."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 30.0
    _attr_max_temp = 65.0
    _attr_operation_list = SUPPORTED_OPERATIONS
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_water_heater"
        self._attr_name = f"{self._zone_data.get('name', 'Eau Chaude')} Chauffe-eau"

    @property
    def _zone_data(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("zones", {}).get(self.zone_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_{self.zone_id}")},
            name=f"Tado {self._zone_data.get('name', 'Eau Chaude')}",
            manufacturer="Tado (DomoLink)",
            suggested_area=self._zone_data.get("name"),
        )

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        """Caractéristiques supportées par le circuit d'eau chaude."""
        features = WaterHeaterEntityFeature.OPERATION_MODE
        # Si la zone supporte un réglage de température de consigne
        if self.target_temperature is not None:
            features |= WaterHeaterEntityFeature.TARGET_TEMPERATURE
        return features

    @property
    def current_operation(self) -> str:
        """Mode de fonctionnement actuel (auto, heat, off)."""
        power = self._zone_data.get("power", "OFF")
        if power == "OFF":
            return STATE_OFF
        if self._zone_data.get("is_overlay_active", False):
            return STATE_HEAT
        return STATE_AUTO

    @property
    def current_temperature(self) -> float | None:
        """Température actuelle de l'eau chaude si disponible."""
        temp = self._zone_data.get("inside_temperature")
        return float(temp) if temp is not None else None

    @property
    def target_temperature(self) -> float | None:
        """Température de consigne d'eau chaude."""
        temp = self._zone_data.get("target_temperature")
        return float(temp) if temp is not None else None

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Définir le mode d'opération (auto, heat, off)."""
        if operation_mode not in SUPPORTED_OPERATIONS:
            _LOGGER.warning("DomoLink-Tado: Mode chauffe-eau non supporté: %s", operation_mode)
            return
        await self.coordinator.async_set_water_heater_mode(self.zone_id, operation_mode)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Définir la consigne de température d'eau chaude."""
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp is not None:
            await self.coordinator.async_set_water_heater_temperature(self.zone_id, float(target_temp))
