"""Binary sensors platform for DomoLink-Tado."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up DomoLink-Tado binary sensors from config entry."""
    coordinator: DomolinkTadoCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # 1. Global Home Binary Sensors
    async_add_entities([DomolinkTadoPresenceBinarySensor(coordinator)])

    # 2. Zone & Device Binary Sensors (Découverte dynamique)
    added_zone_binary_sensors: set[int] = set()
    added_device_binary_sensors: set[str] = set()

    def _check_and_add_dynamic_binary_sensors() -> None:
        new_binary_sensors: list[BinarySensorEntity] = []
        zones = (coordinator.data or {}).get("zones", {})
        for zone_id in zones:
            if zone_id not in added_zone_binary_sensors:
                new_binary_sensors.append(DomolinkTadoOpenWindowBinarySensor(coordinator, zone_id))
                new_binary_sensors.append(DomolinkTadoHeatingActiveBinarySensor(coordinator, zone_id))
                new_binary_sensors.append(DomolinkTadoOverlayActiveBinarySensor(coordinator, zone_id))
                new_binary_sensors.append(DomolinkTadoZoneMoldRiskProblemBinarySensor(coordinator, zone_id))
                new_binary_sensors.append(DomolinkTadoZoneVentilationRecommendedBinarySensor(coordinator, zone_id))
                new_binary_sensors.append(DomolinkTadoZonePreheatNowBinarySensor(coordinator, zone_id))
                new_binary_sensors.append(DomolinkTadoZoneRapidWindowDropBinarySensor(coordinator, zone_id))
                added_zone_binary_sensors.add(zone_id)

        devices = (coordinator.data or {}).get("devices", {})
        for serial in devices:
            if serial not in added_device_binary_sensors:
                new_binary_sensors.append(DomolinkTadoDeviceConnectionBinarySensor(coordinator, serial))
                dev = devices.get(serial, {})
                if "batteryState" in dev:
                    new_binary_sensors.append(DomolinkTadoDeviceBatteryAlertBinarySensor(coordinator, serial))
                added_device_binary_sensors.add(serial)

        if new_binary_sensors:
            async_add_entities(new_binary_sensors)

    _check_and_add_dynamic_binary_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_check_and_add_dynamic_binary_sensors))


# ── Global Presence ─────────────────────────────────────────

class DomolinkTadoPresenceBinarySensor(CoordinatorEntity[DomolinkTadoCoordinator], BinarySensorEntity):
    """Binary sensor for Home presence (Home vs Away)."""

    _attr_device_class = BinarySensorDeviceClass.PRESENCE

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_presence"
        self._attr_name = "Tado Présence Domicile"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_home")},
            name=self.coordinator.formatted_home_name,
            manufacturer="Tado (DomoLink)",
            model="Home Hub",
        )

    @property
    def is_on(self) -> bool:
        return (self.coordinator.data or {}).get("presence") == "HOME"


# ── Zone Binary Sensors ─────────────────────────────────────

class DomolinkTadoZoneBinarySensorBase(CoordinatorEntity[DomolinkTadoCoordinator], BinarySensorEntity):
    """Base class for zone binary sensors."""

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id

    @property
    def _zone_data(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("zones", {}).get(self.zone_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_{self.zone_id}")},
            name=f"Tado {self._zone_data.get('name', 'Zone')}",
            manufacturer="Tado (DomoLink)",
            suggested_area=self._zone_data.get("name"),
        )


class DomolinkTadoOpenWindowBinarySensor(DomolinkTadoZoneBinarySensorBase):
    """Binary sensor for open window detection in zone."""

    _attr_device_class = BinarySensorDeviceClass.WINDOW

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_open_window"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Fenêtre Ouverte"

    @property
    def is_on(self) -> bool:
        return bool(self._zone_data.get("open_window", False))


class DomolinkTadoHeatingActiveBinarySensor(DomolinkTadoZoneBinarySensorBase):
    """Binary sensor indicating if zone is actively heating."""

    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_heating_active"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Chauffe Active"

    @property
    def is_on(self) -> bool:
        return float(self._zone_data.get("heating_power") or 0.0) > 0


class DomolinkTadoOverlayActiveBinarySensor(DomolinkTadoZoneBinarySensorBase):
    """Binary sensor indicating if zone has an active manual overlay."""

    _attr_icon = "mdi:hand-back-right"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_overlay_active"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Dérogation Manuelle"

    @property
    def is_on(self) -> bool:
        return bool(self._zone_data.get("is_overlay_active", False))


class DomolinkTadoZoneMoldRiskProblemBinarySensor(DomolinkTadoZoneBinarySensorBase):
    """Binary sensor indicating high mold risk in zone."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_mold_problem"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Alerte Moisissure"

    @property
    def is_on(self) -> bool:
        return bool(self._zone_data.get("mold_risk_problem", False))


class DomolinkTadoZoneVentilationRecommendedBinarySensor(DomolinkTadoZoneBinarySensorBase):
    """Binary sensor indicating if ventilation will dry out room."""

    _attr_icon = "mdi:window-open-variant"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_ventilation_recommended"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Aération Recommandée"

    @property
    def is_on(self) -> bool:
        return bool(self._zone_data.get("ventilation_recommended", False))


class DomolinkTadoZonePreheatNowBinarySensor(DomolinkTadoZoneBinarySensorBase):
    """Binary sensor indicating if zone is currently actively preheating."""

    _attr_icon = "mdi:fire-alert"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_preheat_now"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Préchauffe en Cours"

    @property
    def is_on(self) -> bool:
        return bool(self._zone_data.get("preheat_now", False))


class DomolinkTadoZoneRapidWindowDropBinarySensor(DomolinkTadoZoneBinarySensorBase):
    """Binary sensor indicating a detected sudden temperature drop (open window)."""

    _attr_device_class = BinarySensorDeviceClass.WINDOW
    _attr_icon = "mdi:thermometer-chevron-down"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_rapid_window_drop"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Chute Brutale Température"

    @property
    def is_on(self) -> bool:
        return bool(self._zone_data.get("rapid_window_drop", False))


# ── Device Binary Sensors ───────────────────────────────────

class DomolinkTadoDeviceBinarySensorBase(CoordinatorEntity[DomolinkTadoCoordinator], BinarySensorEntity):
    """Base class for device binary sensors."""

    def __init__(self, coordinator: DomolinkTadoCoordinator, serial_number: str) -> None:
        super().__init__(coordinator)
        self.serial_number = serial_number

    @property
    def _device_data(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("devices", {}).get(self.serial_number, {})

    @property
    def device_info(self) -> DeviceInfo:
        d = self._device_data
        return DeviceInfo(
            identifiers={(DOMAIN, f"device_{self.serial_number}")},
            name=f"Tado {d.get('deviceType', 'Appareil')} ({self.serial_number})",
            manufacturer="Tado (DomoLink)",
            serial_number=self.serial_number,
        )


class DomolinkTadoDeviceBatteryAlertBinarySensor(DomolinkTadoDeviceBinarySensorBase):
    """Binary sensor indicating if device battery is low."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY

    def __init__(self, coordinator: DomolinkTadoCoordinator, serial_number: str) -> None:
        super().__init__(coordinator, serial_number)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{serial_number}_battery_alert"
        self._attr_name = f"Tado {serial_number} Alerte Batterie"

    @property
    def is_on(self) -> bool:
        return self._device_data.get("batteryState") != "NORMAL"


class DomolinkTadoDeviceConnectionBinarySensor(DomolinkTadoDeviceBinarySensorBase):
    """Binary sensor indicating if device is connected to bridge."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: DomolinkTadoCoordinator, serial_number: str) -> None:
        super().__init__(coordinator, serial_number)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{serial_number}_connection"
        self._attr_name = f"Tado {serial_number} Connexion Radio"

    @property
    def is_on(self) -> bool:
        return bool((self._device_data.get("connectionState") or {}).get("value", True))
