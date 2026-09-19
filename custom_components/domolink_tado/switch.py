"""Switch platform for DomoLink-Tado."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ECO_TEMP, DEFAULT_ECO_TEMP, DOMAIN
from .coordinator import DomolinkTadoCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DomoLink-Tado switches from config entry."""
    coordinator: DomolinkTadoCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # 1. Global Home Presence and Eco switches
    async_add_entities([
        DomolinkTadoPresenceSwitch(coordinator),
        DomolinkTadoGlobalEcoSwitch(coordinator),
    ])

    # 2. Dynamic Zone & Device Switches (Child Lock & Zone Overlay)
    added_child_locks: set[str] = set()
    added_zone_overlays: set[int] = set()

    def _check_and_add_dynamic_switches() -> None:
        new_switches: list[SwitchEntity] = []

        # 1. Child Lock switches for each physical radiator valve
        devices = (coordinator.data or {}).get("devices", {})
        for serial, dev in devices.items():
            if serial not in added_child_locks and "childLockEnabled" in dev:
                new_switches.append(DomolinkTadoChildLockSwitch(coordinator, serial))
                added_child_locks.add(serial)

        # 2. Zone Overlay switches (active vs schedule)
        zones = (coordinator.data or {}).get("zones", {})
        for zone_id in zones:
            if zone_id not in added_zone_overlays:
                new_switches.append(DomolinkTadoZoneOverlaySwitch(coordinator, zone_id))
                added_zone_overlays.add(zone_id)

        if new_switches:
            async_add_entities(new_switches)

    _check_and_add_dynamic_switches()
    entry.async_on_unload(coordinator.async_add_listener(_check_and_add_dynamic_switches))



class DomolinkTadoChildLockSwitch(CoordinatorEntity[DomolinkTadoCoordinator], SwitchEntity):
    """Switch to toggle physical child lock on a Tado radiator valve."""

    _attr_icon = "mdi:lock"

    def __init__(self, coordinator: DomolinkTadoCoordinator, serial_number: str) -> None:
        super().__init__(coordinator)
        self.serial_number = serial_number
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{serial_number}_child_lock"
        self._attr_name = f"Tado {serial_number} Sécurité Enfant"

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

    @property
    def is_on(self) -> bool:
        return bool(self._device_data.get("childLockEnabled", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable child lock."""
        await self.coordinator.async_set_child_lock(self.serial_number, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable child lock."""
        await self.coordinator.async_set_child_lock(self.serial_number, False)


class DomolinkTadoZoneOverlaySwitch(CoordinatorEntity[DomolinkTadoCoordinator], SwitchEntity):
    """Switch to activate manual override or resume automatic schedule."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: DomolinkTadoCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_{zone_id}_overlay_switch"
        self._attr_name = f"{self._zone_data.get('name', 'Zone')} Forçage Manuel"

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

    @property
    def is_on(self) -> bool:
        return bool(self._zone_data.get("is_overlay_active", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on manual overlay (defaults to 20°C or current target)."""
        temp = self._zone_data.get("target_temperature") or 20.0
        await self.coordinator.async_set_temperature(self.zone_id, temp)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off manual overlay (resume automatic schedule)."""
        await self.coordinator.async_resume_schedule(self.zone_id)


class DomolinkTadoPresenceSwitch(CoordinatorEntity[DomolinkTadoCoordinator], SwitchEntity):
    """Switch to toggle Home / Away presence."""

    _attr_icon = "mdi:home-account"

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_presence_switch"
        self._attr_name = "Tado Mode Domicile"

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
        return self.coordinator.data.get("presence") == "HOME"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set presence to HOME."""
        await self.coordinator.async_set_presence(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set presence to AWAY."""
        await self.coordinator.async_set_presence(False)


class DomolinkTadoGlobalEcoSwitch(CoordinatorEntity[DomolinkTadoCoordinator], SwitchEntity):
    """Switch pour activer/désactiver le Mode Éco sur l'ensemble des pièces."""

    _attr_icon = "mdi:leaf"

    def __init__(self, coordinator: DomolinkTadoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"domolink_tado_{coordinator.home_id}_global_eco_switch"
        self._attr_name = "Tado Mode Éco Global"

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
        """Retourne True si toutes les pièces de chauffage sont en overlay à température éco."""
        zones = self.coordinator.data.get("zones", {})
        heating_zones = [
            z for z in zones.values()
            if z.get("type") not in ("HOT_WATER", "DOMESTIC_HOT_WATER")
        ]
        if not heating_zones:
            return False
        eco_temp = self.coordinator.entry.options.get(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)
        return all(
            z.get("is_overlay_active") and abs((z.get("target_temperature") or 0.0) - eco_temp) < 0.2
            for z in heating_zones
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activer le mode éco sur toutes les pièces."""
        await self.coordinator.async_set_eco_all()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Désactiver le mode éco (reprendre le planning automatique)."""
        await self.coordinator.async_resume_all_schedules()
