"""Local Bridge Bypass & Auto-pairing manager for Tado hardware (HomeKit LAN & Matter)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import Event, HomeAssistant
    from .coordinator import DomolinkTadoCoordinator

_LOGGER = logging.getLogger(__name__)


class LocalBridgeManager:
    """Manages local, cloudless communication with Tado Internet Bridge (HomeKit) and Tado X (Matter)."""

    def __init__(self, hass: HomeAssistant, coordinator: DomolinkTadoCoordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._zone_to_local_entity: dict[int, str] = {}
        self._serial_to_local_entity: dict[str, str] = {}
        self._unsub_listeners: list[Any] = []

    @property
    def has_local_entities(self) -> bool:
        """Return True if at least one zone is mapped to a local LAN entity."""
        return len(self._zone_to_local_entity) > 0

    def get_local_entity_for_zone(self, zone_id: int) -> str | None:
        """Return local climate entity ID for a given zone if mapped and available."""
        ent_id = self._zone_to_local_entity.get(zone_id)
        if not ent_id:
            return None
        st = self.hass.states.get(ent_id)
        if st and st.state not in ("unavailable", "unknown"):
            return ent_id
        return None

    def discover_local_entities(self) -> dict[int, str]:
        """Automatically match HA climate entities from homekit_controller/matter with Tado zones."""
        zone_map: dict[int, str] = {}
        serial_map: dict[str, str] = {}

        zones = (self.coordinator.data or {}).get("zones", {})
        devices = (self.coordinator.data or {}).get("devices", {})

        # Resolve entity registry cleanly without deprecated hass.helpers
        ent_reg = None
        try:
            from homeassistant.helpers import entity_registry as er
            if hasattr(er, "async_get"):
                ent_reg = er.async_get(self.hass)
        except Exception:
            pass

        # 1. Gather all local climate entities in HA
        climate_states = self.hass.states.async_all("climate")
        for st in climate_states:
            ent_id = st.entity_id
            attrs = getattr(st, "attributes", None) or {}
            if attrs.get("integration") == "domolink_tado" or "domolink" in ent_id.lower():
                continue

            friendly_name = (attrs.get("friendly_name") or "").lower()

            # Strictly verify platform via entity_registry when available
            if ent_reg is not None:
                try:
                    entry = ent_reg.async_get(ent_id)
                    plat = getattr(entry, "platform", None) if entry else None
                    if isinstance(plat, str) and plat not in ("homekit_controller", "matter"):
                        continue
                except Exception:
                    pass

            # Match by zone name
            for zid, zdata in zones.items():
                zname = (zdata.get("name") or "").lower()
                if zname and (zname in friendly_name or friendly_name in zname):
                    zone_map[zid] = ent_id
                    _LOGGER.info(
                        "DomoLink-Tado: Détection locale du pont pour Zone '%s' (ID %s) -> %s",
                        zdata.get("name"),
                        zid,
                        ent_id,
                    )
                    break

            # Match by device serial number
            for serial, dev in devices.items():
                s_lower = serial.lower()
                if s_lower in ent_id.lower() or s_lower in friendly_name:
                    serial_map[serial] = ent_id
                    # If this device has a zone ID
                    zid = dev.get("zoneId")
                    if zid and zid in zones and zid not in zone_map:
                        zone_map[zid] = ent_id

        self._zone_to_local_entity = zone_map
        self._serial_to_local_entity = serial_map
        return zone_map

    async def async_set_temperature_local(self, zone_id: int, target_temp: float) -> bool:
        """Set target temperature directly on the local bridge without any cloud call."""
        ent_id = self.get_local_entity_for_zone(zone_id)
        if not ent_id:
            return False

        _LOGGER.debug(
            "DomoLink-Tado [Local Bridge Bypass]: Envoi consigne %.1f°C directement en LAN à %s (Zone %d)",
            target_temp,
            ent_id,
            zone_id,
        )
        try:
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": ent_id, "temperature": target_temp},
                blocking=True,
            )
            return True
        except Exception as err:
            _LOGGER.warning("DomoLink-Tado: Échec de commande locale sur %s: %s", ent_id, err)
            return False

    async def async_turn_off_local(self, zone_id: int) -> bool:
        """Turn off zone directly on the local bridge (instantaneous WindowGuard cutoff, 0 tokens)."""
        ent_id = self.get_local_entity_for_zone(zone_id)
        if not ent_id:
            return False

        _LOGGER.debug(
            "DomoLink-Tado [Local Bridge Bypass]: Coupure locale chauffage sur %s (Zone %d)",
            ent_id,
            zone_id,
        )
        try:
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": ent_id, "hvac_mode": "off"},
                blocking=True,
            )
            return True
        except Exception as err:
            _LOGGER.warning("DomoLink-Tado: Échec coupure locale sur %s: %s", ent_id, err)
            return False

    async def async_turn_on_local(self, zone_id: int) -> bool:
        """Turn on heating zone directly on the local bridge."""
        ent_id = self.get_local_entity_for_zone(zone_id)
        if not ent_id:
            return False

        try:
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": ent_id, "hvac_mode": "heat"},
                blocking=True,
            )
            return True
        except Exception as err:
            _LOGGER.warning("DomoLink-Tado: Échec allumage local sur %s: %s", ent_id, err)
            return False

    def get_discovery_status(self) -> dict[str, Any]:
        """Inspect HomeKit Controller and Matter entries & pending flows in HA."""
        hk_entries = []
        matter_entries = []
        pending_hk = []
        pending_matter = []
        try:
            for ce in self.hass.config_entries.async_entries("homekit_controller"):
                hk_entries.append({"entry_id": ce.entry_id, "title": ce.title})
        except Exception:
            pass
        try:
            for ce in self.hass.config_entries.async_entries("matter"):
                matter_entries.append({"entry_id": ce.entry_id, "title": ce.title})
        except Exception:
            pass
        try:
            for fl in self.hass.config_entries.flow.async_progress():
                handler = fl.get("handler")
                ctx = fl.get("context", {})
                title = (ctx.get("title_placeholders") or {}).get("name") or ctx.get("title") or handler
                if handler == "homekit_controller":
                    pending_hk.append({"flow_id": fl.get("flow_id"), "title": title})
                elif handler == "matter":
                    pending_matter.append({"flow_id": fl.get("flow_id"), "title": title})
        except Exception:
            pass

        return {
            "homekit_entries": hk_entries,
            "matter_entries": matter_entries,
            "pending_homekit_flows": pending_hk,
            "pending_matter_flows": pending_matter,
            "mapped_count": len(self._zone_to_local_entity),
            "mapped_zones": {str(k): v for k, v in self._zone_to_local_entity.items()},
        }

    async def async_pair_homekit_bridge(self, pin: str) -> dict[str, Any]:
        """Automatically pair the Tado Internet Bridge in HomeKit Controller using the provided PIN."""
        clean_pin = pin.strip().replace(" ", "").replace("-", "")
        if len(clean_pin) == 8:
            formatted_pin = f"{clean_pin[:3]}-{clean_pin[3:5]}-{clean_pin[5:]}"
        else:
            formatted_pin = pin.strip()

        if not formatted_pin:
            return {"success": False, "message": "Veuillez saisir le code PIN HomeKit à 8 chiffres (XXX-XX-XXX)."}

        _LOGGER.info("DomoLink-Tado: Tentative d'appairage HomeKit automatique du pont Tado...")
        try:
            flows = self.hass.config_entries.flow.async_progress()
            hk_flows = [fl for fl in flows if fl.get("handler") == "homekit_controller"]
            tado_flow = None
            for fl in hk_flows:
                ctx = fl.get("context", {})
                title = str((ctx.get("title_placeholders") or {}).get("name", "")).lower()
                if "tado" in title or "bridge" in title or "ib" in title or "internet" in title:
                    tado_flow = fl
                    break
            if not tado_flow and len(hk_flows) == 1:
                tado_flow = hk_flows[0]

            if tado_flow:
                flow_id = tado_flow["flow_id"]
                result = await self.hass.config_entries.flow.async_configure(
                    flow_id, user_input={"pairing_code": formatted_pin}
                )
                _LOGGER.info("DomoLink-Tado: Résultat appairage HomeKit: %s", result.get("type"))
                self.discover_local_entities()
                return {
                    "success": result.get("type") == "create_entry",
                    "result": result.get("type"),
                    "mapped_count": len(self._zone_to_local_entity),
                    "message": (
                        f"Pont Tado associé en HomeKit Controller ! {len(self._zone_to_local_entity)} zone(s) détectée(s) en local."
                        if result.get("type") == "create_entry"
                        else f"Étape suivante requise ({result.get('type')}). Vérifiez le code PIN ou l'état du pont."
                    ),
                }

            return {
                "success": False,
                "message": "Aucun pont Tado en attente d'appairage HomeKit sur le LAN. S'il est déjà lié à Apple Maison, supprimez-le de l'app Maison iOS pour qu'il apparaisse ici.",
            }
        except Exception as err:
            _LOGGER.error("DomoLink-Tado: Erreur lors de l'appairage HomeKit: %s", err)
            return {"success": False, "message": str(err)}

    async def async_pair_matter_device(self, code: str) -> dict[str, Any]:
        """Commission a Tado X device via Home Assistant's local Matter integration."""
        clean_code = (code or "").strip()
        if not clean_code:
            return {"success": False, "message": "Veuillez saisir un code d'appairage Matter (11 ou 21 chiffres)."}
        if not self.hass.services.has_service("matter", "commission"):
            return {
                "success": False,
                "message": "L'intégration officielle 'Matter' n'est pas configurée dans ce Home Assistant (service matter.commission absent).",
            }
        try:
            _LOGGER.info("DomoLink-Tado: Lancement du commissioning Matter local...")
            await self.hass.services.async_call(
                "matter",
                "commission",
                {"code": clean_code},
                blocking=True,
            )
            self.discover_local_entities()
            return {
                "success": True,
                "mapped_count": len(self._zone_to_local_entity),
                "message": "Commissioning Matter envoyé au serveur Matter local ! Patientez quelques secondes puis scannez le réseau.",
            }
        except Exception as err:
            _LOGGER.error("DomoLink-Tado: Erreur lors du commissioning Matter: %s", err)
            return {"success": False, "message": str(err)}
