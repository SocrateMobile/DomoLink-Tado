"""Sensors platform for DomoLink-Tado."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DomolinkTadoCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DomoLink-Tado sensors from config entry."""
    coordinator: DomolinkTadoCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = []

    # 1. Global Home Sensors
    entities.append(DomolinkTadoOutdoorTempSensor(coordinator))
    entities.append(DomolinkTadoOutdoorHumiditySensor(coordinator))
    entities.append(DomolinkTadoActiveHeatingZonesSensor(coordinator))
    entities.append(DomolinkTadoTotalHeatingPowerSensor(coordinator))

    # 2. Zone Sensors
    zones = coordinator.data.get("zones", {})
    for zone_id, zone_data in zones.items():
        entities.append(DomolinkTadoZoneTempSensor(coordinator, zone_id))
        entities.append(DomolinkTadoZoneTargetTempSensor(coordinator, zone_id))
        entities.append(DomolinkTadoZoneHumiditySensor(coordinator, zone_id))
        entities.append(DomolinkTadoZoneHeatingPowerSensor(coordinator, zone_id))
        entities.append(DomolinkTadoZoneDewPointSensor(coordinator, zone_id))
        entities.append(DomolinkTadoZoneAbsoluteHumiditySensor(coordinator, zone_id))
        entities.append(DomolinkTadoZoneMoldRiskSensor(coordinator, zone_id))

    # 3. Device Battery Sensors (Valves & Thermostats)
    devices = coordinator.data.get("devices", {})
    for serial, dev in devices.items():
        if "batteryState" in dev:
            entities.append(DomolinkTadoDeviceBatterySensor(coordinator, serial))

    async_add_entities(entities)


# ── Global Sensors ──────────────────────────────────────────

class DomolinkTadoOutdoorTempSensor(CoordinatorEntity[DomolinkTadoCoordinator], SensorEntity):
    """Sensor for outdoor temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_outdoor_temp"
        self._attr_name = "Tado Température Extérieure"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_home")},
            name=f"Tado {self.coordinator.home_name}",
            manufacturer="Tado (DomoLink)",
            model="Home Hub",
        )

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("weather", {}).get("outdoor_temperature")


class DomolinkTadoOutdoorHumiditySensor(CoordinatorEntity[DomolinkTadoCoordinator], SensorEntity):
    """Sensor for outdoor humidity."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_outdoor_humidity"
        self._attr_name = "Tado Humidité Extérieure"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_home")},
            name=f"Tado {self.coordinator.home_name}",
            manufacturer="Tado (DomoLink)",
            model="Home Hub",
        )

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("weather", {}).get("outdoor_humidity")


class DomolinkTadoActiveHeatingZonesSensor(CoordinatorEntity[DomolinkTadoCoordinator], SensorEntity):
    """Sensor for number of zones currently actively heating."""

    _attr_icon = "mdi:radiator"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_active_zones"
        self._attr_name = "Tado Pièces en Chauffe Active"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_home")},
            name=f"Tado {self.coordinator.home_name}",
            manufacturer="Tado (DomoLink)",
            model="Home Hub",
        )

    @property
    def native_value(self) -> int:
        return self.coordinator.data.get("active_heating_zones", 0)


class DomolinkTadoTotalHeatingPowerSensor(CoordinatorEntity[DomolinkTadoCoordinator], SensorEntity):
    """Sensor for overall heating power / load."""

    _attr_icon = "mdi:fire"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_total_power"
        self._attr_name = "Tado Puissance de Chauffe Totale"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_home")},
            name=f"Tado {self.coordinator.home_name}",
            manufacturer="Tado (DomoLink)",
            model="Home Hub",
        )

    @property
    def native_value(self) -> float:
        zones = self.coordinator.data.get("zones", {})
        if not zones:
            return 0.0
        total = sum(z.get("heating_power", 0.0) for z in zones.values())
        return round(total / len(zones), 1)


# ── Zone Sensors ────────────────────────────────────────────

class DomolinkTadoZoneSensorBase(CoordinatorEntity[DomolinkTadoCoordinator], SensorEntity):
    """Base class for zone-specific sensors."""

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id

    @property
    def _zone_data(self) -> dict[str, Any]:
        return self.coordinator.data.get("zones", {}).get(self.zone_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_{self.zone_id}")},
            name=f"Tado {self._zone_data.get('name', 'Zone')}",
            manufacturer="Tado (DomoLink)",
            suggested_area=self._zone_data.get("name"),
        )


class DomolinkTadoZoneTempSensor(DomolinkTadoZoneSensorBase):
    """Sensor for zone ambient temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_temp"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Température"

    @property
    def native_value(self) -> float | None:
        return self._zone_data.get("inside_temperature")


class DomolinkTadoZoneTargetTempSensor(DomolinkTadoZoneSensorBase):
    """Sensor for zone target temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_target_temp"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Consigne"

    @property
    def native_value(self) -> float | None:
        return self._zone_data.get("target_temperature")


class DomolinkTadoZoneHumiditySensor(DomolinkTadoZoneSensorBase):
    """Sensor for zone relative humidity."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_humidity"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Humidité"

    @property
    def native_value(self) -> float | None:
        return self._zone_data.get("humidity")


class DomolinkTadoZoneHeatingPowerSensor(DomolinkTadoZoneSensorBase):
    """Sensor for zone valve heating power percentage."""

    _attr_icon = "mdi:fire"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_heating_power"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Puissance de Chauffe"

    @property
    def native_value(self) -> float:
        return round(float(self._zone_data.get("heating_power", 0.0)), 1)


class DomolinkTadoZoneDewPointSensor(DomolinkTadoZoneSensorBase):
    """Sensor for zone calculated dew point."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:water-thermometer"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_dew_point"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Point de Rosée"

    @property
    def native_value(self) -> float | None:
        return self._zone_data.get("dew_point")


class DomolinkTadoZoneAbsoluteHumiditySensor(DomolinkTadoZoneSensorBase):
    """Sensor for zone calculated absolute humidity in g/m³."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "g/m³"
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_absolute_humidity"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Humidité Absolue"

    @property
    def native_value(self) -> float | None:
        return self._zone_data.get("absolute_humidity")


class DomolinkTadoZoneMoldRiskSensor(DomolinkTadoZoneSensorBase):
    """Sensor for zone mold risk assessment level."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["normal", "low", "medium", "high"]
    _attr_icon = "mdi:alert-decagram-outline"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_mold_risk"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Risque Moisissure"

    @property
    def native_value(self) -> str | None:
        return self._zone_data.get("mold_risk_level")


# ── Device Battery Sensor ───────────────────────────────────

class DomolinkTadoDeviceBatterySensor(CoordinatorEntity[DomolinkTadoCoordinator], SensorEntity):
    """Sensor for physical device battery state."""

    _attr_icon = "mdi:battery"

    def __init__(self, coordinator: DomolinkTadoCoordinator, serial_number: str) -> None:
        super().__init__(coordinator)
        self.serial_number = serial_number
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{serial_number}_battery"
        self._attr_name = f"Tado {serial_number} État Batterie"

    @property
    def _device_data(self) -> dict[str, Any]:
        return self.coordinator.data.get("devices", {}).get(self.serial_number, {})

    @property
    def device_info(self) -> DeviceInfo:
        d = self._device_data
        return DeviceInfo(
            identifiers={(DOMAIN, f"device_{self.serial_number}")},
            name=f"Tado {d.get('deviceType', 'Appareil')} ({self.serial_number})",
            manufacturer="Tado (DomoLink)",
            model=d.get("deviceType", "Smart Radiator Valve"),
            serial_number=self.serial_number,
        )

    @property
    def native_value(self) -> str:
        state = self._device_data.get("batteryState", "NORMAL")
        return "Normale" if state == "NORMAL" else "Faible"
