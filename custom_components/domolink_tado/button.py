"""Button platform for DomoLink-Tado."""
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
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
    """Set up DomoLink-Tado buttons from config entry."""
    coordinator: DomolinkTadoCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # 1. Global Buttons
    async_add_entities([
        DomolinkTadoResumeAllSchedulesButton(coordinator),
        DomolinkTadoAllOffButton(coordinator),
        DomolinkTadoSmartBoostButton(coordinator),
    ])

    # 2. Dynamic Zone Buttons
    added_zone_buttons: set[int] = set()
    added_device_buttons: set[str] = set()

    def _check_and_add_buttons() -> None:
        new_buttons: list[ButtonEntity] = []
        zones = (coordinator.data or {}).get("zones", {})
        for zone_id in zones:
            if zone_id not in added_zone_buttons:
                new_buttons.append(DomolinkTadoZoneResumeScheduleButton(coordinator, zone_id))
                new_buttons.append(DomolinkTadoZoneBoostButton(coordinator, zone_id))
                added_zone_buttons.add(zone_id)

        devices = (coordinator.data or {}).get("devices", {})
        for serial, dev in devices.items():
            if serial not in added_device_buttons:
                new_buttons.append(DomolinkTadoRebootDeviceButton(coordinator, serial))
                if dev.get("supportsIdentify") or dev.get("graphql_id") or str(dev.get("deviceType", "")).startswith(("VA", "RU", "SU")):
                    new_buttons.append(DomolinkTadoIdentifyDeviceButton(coordinator, serial))
                added_device_buttons.add(serial)

        if new_buttons:
            async_add_entities(new_buttons)

    _check_and_add_buttons()
    entry.async_on_unload(coordinator.async_add_listener(_check_and_add_buttons))


class DomolinkTadoResumeAllSchedulesButton(CoordinatorEntity[DomolinkTadoCoordinator], ButtonEntity):
    """Bouton pour reprendre la programmation automatique sur toutes les zones actives."""

    _attr_icon = "mdi:calendar-sync"

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_resume_all_schedules"
        self._attr_name = "Tado Reprendre Programmation Partout"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_home")},
            name=self.coordinator.formatted_home_name,
            manufacturer="Tado (DomoLink)",
            model="Home Hub",
        )

    async def async_press(self) -> None:
        """Reprendre les programmations."""
        await self.coordinator.async_resume_all_schedules()


class DomolinkTadoAllOffButton(CoordinatorEntity[DomolinkTadoCoordinator], ButtonEntity):
    """Bouton pour éteindre / mettre hors-gel toutes les pièces en 1 clic."""

    _attr_icon = "mdi:power-off"

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_all_off"
        self._attr_name = "Tado Tout Éteindre"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_home")},
            name=self.coordinator.formatted_home_name,
            manufacturer="Tado (DomoLink)",
            model="Home Hub",
        )

    async def async_press(self) -> None:
        """Éteindre tout le chauffage."""
        await self.coordinator.async_set_all_off()


class DomolinkTadoSmartBoostButton(CoordinatorEntity[DomolinkTadoCoordinator], ButtonEntity):
    """Bouton pour activer le Boost Intelligent global (selon paramètres ou défauts)."""

    _attr_icon = "mdi:rocket-launch"

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_smart_boost"
        self._attr_name = "Tado Boost Intelligent Partout"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.home_id}_home")},
            name=self.coordinator.formatted_home_name,
            manufacturer="Tado (DomoLink)",
            model="Home Hub",
        )

    async def async_press(self) -> None:
        """Déclencher le boost intelligent sur toute la maison."""
        await self.coordinator.async_smart_boost()


class DomolinkTadoZoneResumeScheduleButton(CoordinatorEntity[DomolinkTadoCoordinator], ButtonEntity):
    """Bouton pour réenclencher la programmation automatique sur une zone précise."""

    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_resume_schedule"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Reprendre Programmation"

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

    async def async_press(self) -> None:
        """Reprendre le planning de la zone."""
        await self.coordinator.async_resume_schedule(self.zone_id)


class DomolinkTadoZoneBoostButton(CoordinatorEntity[DomolinkTadoCoordinator], ButtonEntity):
    """Bouton pour activer le Boost Intelligent sur une seule zone."""

    _attr_icon = "mdi:fire-circle"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_smart_boost"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Boost Intelligent"

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

    async def async_press(self) -> None:
        """Déclencher le boost intelligent sur la pièce."""
        await self.coordinator.async_set_zone_boost(self.zone_id)


class DomolinkTadoIdentifyDeviceButton(CoordinatorEntity[DomolinkTadoCoordinator], ButtonEntity):
    """Bouton pour faire clignoter l'écran LED d'une tête de radiateur ou thermostat."""

    _attr_icon = "mdi:led-on"

    def __init__(self, coordinator: DomolinkTadoCoordinator, serial_number: str) -> None:
        super().__init__(coordinator)
        self.serial_number = serial_number
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{serial_number}_identify"
        self._attr_name = f"Tado {serial_number} Identifier (LED)"

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

    async def async_press(self) -> None:
        """Faire clignoter l'écran LED de l'appareil."""
        await self.coordinator.async_identify_device(self.serial_number)


class DomolinkTadoRebootDeviceButton(CoordinatorEntity[DomolinkTadoCoordinator], ButtonEntity):
    """Bouton pour redémarrer à distance une vanne, thermostat ou bridge Tado."""

    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: DomolinkTadoCoordinator, serial_number: str) -> None:
        super().__init__(coordinator)
        self.serial_number = serial_number
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{serial_number}_reboot"
        self._attr_name = f"Tado {serial_number} Redémarrer"

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

    async def async_press(self) -> None:
        """Redémarrer l'appareil."""
        await self.coordinator.async_reboot_device(self.serial_number)

