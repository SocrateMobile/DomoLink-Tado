"""WindowGuard: Détection événementielle et gestion des ouvertures de fenêtres.

Optimisé pour réduire à 0 les requêtes API Tado au repos :
- Abonnement événementiel local aux capteurs d'ouverture (binary_sensor.*).
- Abonnement aux variations des capteurs de température externes (chute rapide).
- Coupure automatique (OFF TIMER) avec délai d'ouverture (open_delay).
- Rétablissement du planning ou de la consigne précédente avec délai de fermeture (close_delay).
- Protection anti-écrasement des réglages manuels utilisateur pendant l'aération.
- Persistance de l'état des épisodes (Store) en cas de redémarrage Home Assistant.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Literal

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .adaptive_preheat import detect_rapid_temperature_drop
from .const import (
    CONF_AUTO_WINDOW_ENABLED,
    CONF_DYNAMIC_WINDOW_DROP,
    CONF_USE_NATIVE_WINDOW,
    CONF_WINDOW_CLOSE_DELAY,
    CONF_WINDOW_MAX_DURATION,
    CONF_WINDOW_OPEN_DELAY,
    CONF_WINDOW_RESTORE_MODE,
    CONF_ZONE_CONTACT_ENTITIES,
    CONF_ZONE_TEMP_ENTITIES,
    DEFAULT_AUTO_WINDOW_ENABLED,
    DEFAULT_DYNAMIC_WINDOW_DROP,
    DEFAULT_USE_NATIVE_WINDOW,
    DEFAULT_WINDOW_CLOSE_DELAY,
    DEFAULT_WINDOW_MAX_DURATION,
    DEFAULT_WINDOW_OPEN_DELAY,
    DEFAULT_WINDOW_RESTORE_MODE,
    EVENT_WINDOW_CLOSED,
    EVENT_WINDOW_OPENED,
    OVERLAY_TIMER,
    WINDOW_RESTORE_PREVIOUS,
)

if TYPE_CHECKING:
    from homeassistant.helpers.storage import Store
    from .coordinator import DomolinkTadoCoordinator

_LOGGER = logging.getLogger(__name__)

Reason = Literal["contact", "tado_native", "rapid_drop"]


@dataclass
class WindowEpisode:
    """Représente un épisode d'aération actif pour une pièce."""

    zone_id: int
    started_at: float
    reason: Reason
    previous_overlay: dict[str, Any] | None
    we_own_overlay: bool

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'épisode en dictionnaire pour la persistance."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WindowEpisode:
        """Crée une instance à partir d'un dictionnaire."""
        return cls(
            zone_id=int(data["zone_id"]),
            started_at=float(data.get("started_at", time.time())),
            reason=data.get("reason", "contact"),
            previous_overlay=data.get("previous_overlay"),
            we_own_overlay=bool(data.get("we_own_overlay", True)),
        )


class WindowGuard:
    """Gestionnaire événementiel d'ouverture des fenêtres et coupure de chauffage."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DomolinkTadoCoordinator,
        store: Store | None = None,
    ) -> None:
        """Initialise le WindowGuard."""
        self.hass = hass
        self.coordinator = coordinator
        self._store = store

        self._episodes: dict[int, WindowEpisode] = {}
        self._unsub_listeners: list[Callable[[], None]] = []
        self._pending_open_timers: dict[int, Callable[[], None]] = {}
        self._pending_close_timers: dict[int, Callable[[], None]] = {}

        self._zone_temp_history: dict[int, list[tuple[float, float]]] = {}
        self._contact_to_zones: dict[str, set[int]] = {}
        self._temp_to_zones: dict[str, set[int]] = {}

    @property
    def is_enabled(self) -> bool:
        """Indique si la gestion automatique de fenêtre est activée."""
        return self.coordinator.entry.options.get(
            CONF_AUTO_WINDOW_ENABLED, DEFAULT_AUTO_WINDOW_ENABLED
        )

    @property
    def open_delay(self) -> int:
        """Délai en secondes avant coupure lors de l'ouverture."""
        return int(
            self.coordinator.entry.options.get(
                CONF_WINDOW_OPEN_DELAY, DEFAULT_WINDOW_OPEN_DELAY
            )
        )

    @property
    def close_delay(self) -> int:
        """Délai en secondes après fermeture avant rétablissement."""
        return int(
            self.coordinator.entry.options.get(
                CONF_WINDOW_CLOSE_DELAY, DEFAULT_WINDOW_CLOSE_DELAY
            )
        )

    @property
    def max_duration(self) -> int:
        """Durée maximale de sécurité de la minuterie OFF en secondes."""
        return int(
            self.coordinator.entry.options.get(
                CONF_WINDOW_MAX_DURATION, DEFAULT_WINDOW_MAX_DURATION
            )
        )

    @property
    def restore_mode(self) -> str:
        """Mode de rétablissement (RESUME ou RESTORE_PREVIOUS)."""
        return self.coordinator.entry.options.get(
            CONF_WINDOW_RESTORE_MODE, DEFAULT_WINDOW_RESTORE_MODE
        )

    def is_window_open(self, zone_id: int) -> bool:
        """Retourne True si un épisode de fenêtre ouverte est en cours."""
        return zone_id in self._episodes

    def get_episode(self, zone_id: int) -> WindowEpisode | None:
        """Retourne les détails de l'épisode en cours pour une zone."""
        return self._episodes.get(zone_id)

    async def async_setup(self) -> None:
        """Configure les abonnements et restaure les épisodes enregistrés."""
        # 1. Chargement de la persistance (Store)
        if self._store:
            try:
                saved = await self._store.async_load()
                if saved and isinstance(saved, dict):
                    for zid_str, ep_data in saved.items():
                        try:
                            ep = WindowEpisode.from_dict(ep_data)
                            self._episodes[ep.zone_id] = ep
                        except Exception as parse_err:
                            _LOGGER.warning(
                                "DomoLink-Tado WindowGuard: Erreur lecture épisode sauvegardé %s: %s",
                                zid_str,
                                parse_err,
                            )
            except Exception as err:
                _LOGGER.warning(
                    "DomoLink-Tado WindowGuard: Impossible de charger l'état sauvegardé: %s",
                    err,
                )

        # 2. Configuration des abonnements aux capteurs
        self._setup_sensor_subscriptions()

    def async_unload(self) -> None:
        """Décharge WindowGuard et annule les minuteries et abonnements."""
        for unsub in self._pending_open_timers.values():
            try:
                unsub()
            except Exception:
                pass
        self._pending_open_timers.clear()

        for unsub in self._pending_close_timers.values():
            try:
                unsub()
            except Exception:
                pass
        self._pending_close_timers.clear()

        for unsub in self._unsub_listeners:
            try:
                unsub()
            except Exception:
                pass
        self._unsub_listeners.clear()
        self._contact_to_zones.clear()
        self._temp_to_zones.clear()

    def _setup_sensor_subscriptions(self) -> None:
        """Met en place les abonnements événementiels sur contact et température."""
        # Nettoyage des abonnements précédents
        for unsub in self._unsub_listeners:
            try:
                unsub()
            except Exception:
                pass
        self._unsub_listeners.clear()
        self._contact_to_zones.clear()
        self._temp_to_zones.clear()

        options = self.coordinator.entry.options

        # Mapping contact sensors
        contacts_config = options.get(CONF_ZONE_CONTACT_ENTITIES, {})
        for zid_str, entities in contacts_config.items():
            try:
                zid = int(zid_str)
            except (ValueError, TypeError):
                continue
            ent_list = [entities] if isinstance(entities, str) else list(entities)
            for ent_id in ent_list:
                if ent_id and isinstance(ent_id, str):
                    self._contact_to_zones.setdefault(ent_id.strip(), set()).add(zid)

        if self._contact_to_zones:
            contact_entities = list(self._contact_to_zones.keys())
            unsub_contact = async_track_state_change_event(
                self.hass, contact_entities, self._on_contact_event
            )
            self._unsub_listeners.append(unsub_contact)
            _LOGGER.debug(
                "DomoLink-Tado WindowGuard: Abonné à %d capteurs de contact pour %d zones",
                len(contact_entities),
                len(contacts_config),
            )

        # Mapping temperature sensors pour chute rapide
        dynamic_window = options.get(
            CONF_DYNAMIC_WINDOW_DROP, DEFAULT_DYNAMIC_WINDOW_DROP
        )
        if dynamic_window:
            temp_config = options.get(CONF_ZONE_TEMP_ENTITIES, {})
            for zid_str, entities in temp_config.items():
                try:
                    zid = int(zid_str)
                except (ValueError, TypeError):
                    continue
                ent_list = [entities] if isinstance(entities, str) else list(entities)
                for ent_id in ent_list:
                    if ent_id and isinstance(ent_id, str):
                        self._temp_to_zones.setdefault(ent_id.strip(), set()).add(zid)

            if self._temp_to_zones:
                temp_entities = list(self._temp_to_zones.keys())
                unsub_temp = async_track_state_change_event(
                    self.hass, temp_entities, self._on_temp_event
                )
                self._unsub_listeners.append(unsub_temp)
                _LOGGER.debug(
                    "DomoLink-Tado WindowGuard: Abonné à %d capteurs de température pour détection chute rapide",
                    len(temp_entities),
                )

    # ── Événements Contact Sensor ───────────────────────────────

    @callback
    def _on_contact_event(self, event: Event) -> None:
        """Gère un changement d'état d'un capteur de contact d'ouverture."""
        if not self.is_enabled:
            return

        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        entity_id = event.data.get("entity_id")
        zones = self._contact_to_zones.get(entity_id, set())
        is_open = new_state.state == STATE_ON

        for zid in zones:
            if is_open:
                self._handle_zone_opened(zid, "contact")
            else:
                self._handle_zone_closed_candidate(zid)

    def _handle_zone_opened(self, zone_id: int, reason: Reason) -> None:
        """Planifie la coupure de chauffage après open_delay."""
        # Annuler toute minuterie de fermeture en attente
        if zone_id in self._pending_close_timers:
            self._pending_close_timers.pop(zone_id)()

        # Si l'épisode est déjà actif, rien à faire
        if zone_id in self._episodes:
            return

        # Si une minuterie d'ouverture tourne déjà, ne pas la réinitialiser
        if zone_id in self._pending_open_timers:
            return

        delay = float(self.open_delay)

        def _execute_open_cut(_now: Any = None) -> None:
            self._pending_open_timers.pop(zone_id, None)
            self.hass.async_create_task(self._cut(zone_id, reason))

        if delay <= 0:
            _execute_open_cut()
        else:
            self._pending_open_timers[zone_id] = async_call_later(
                self.hass, delay, _execute_open_cut
            )

    def _handle_zone_closed_candidate(self, zone_id: int) -> None:
        """Vérifie si tous les capteurs de la zone sont fermés avant de planifier le rétablissement."""
        # Si un des capteurs de la zone est encore ouvert, la pièce reste aérée
        options = self.coordinator.entry.options
        contacts_config = options.get(CONF_ZONE_CONTACT_ENTITIES, {})
        entities = contacts_config.get(str(zone_id), [])
        ent_list = [entities] if isinstance(entities, str) else list(entities)

        for ent_id in ent_list:
            if not ent_id:
                continue
            st = self.hass.states.get(ent_id)
            if st and st.state == STATE_ON:
                # Encore au moins un capteur ouvert
                return

        # Tous les capteurs de contact sont fermés :
        # 1. Si une coupure était en attente (open_delay non écoulé), on l'annule !
        if zone_id in self._pending_open_timers:
            self._pending_open_timers.pop(zone_id)()
            _LOGGER.debug(
                "DomoLink-Tado WindowGuard: Fenêtre refermée avant open_delay pour zone %s, coupure annulée",
                zone_id,
            )

        # 2. Si un épisode de coupure est actif, on planifie le rétablissement après close_delay
        if zone_id in self._episodes:
            if zone_id in self._pending_close_timers:
                return  # Déjà en attente

            delay = float(self.close_delay)

            def _execute_restore(_now: Any = None) -> None:
                self._pending_close_timers.pop(zone_id, None)
                self.hass.async_create_task(self._restore(zone_id))

            if delay <= 0:
                _execute_restore()
            else:
                self._pending_close_timers[zone_id] = async_call_later(
                    self.hass, delay, _execute_restore
                )

    # ── Événements Température Chute Rapide ─────────────────────

    @callback
    def _on_temp_event(self, event: Event) -> None:
        """Gère un changement d'état d'un capteur de température pour détection rapide."""
        if not self.is_enabled:
            return

        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        try:
            temp_val = float(new_state.state)
        except (ValueError, TypeError):
            return

        entity_id = event.data.get("entity_id")
        zones = self._temp_to_zones.get(entity_id, set())
        now = time.time()

        for zid in zones:
            history = self._zone_temp_history.setdefault(zid, [])
            history.append((now, temp_val))
            # Conserver historique sur 10 minutes (600s)
            self._zone_temp_history[zid] = [(t, v) for t, v in history if now - t <= 600]

            # Vérifier si la zone est en chauffe
            zdata = (self.coordinator.data or {}).get("zones", {}).get(zid, {})
            heating_power = zdata.get("heating_power", 0)

            if heating_power > 0 and detect_rapid_temperature_drop(
                self._zone_temp_history[zid], threshold_drop=0.4, max_seconds=240.0
            ):
                _LOGGER.info(
                    "DomoLink-Tado WindowGuard: Chute rapide de température détectée zone %s (-0.4°C / 4min)",
                    zid,
                )
                self._handle_zone_opened(zid, "rapid_drop")

    # ── Repli Tado Natif (appelé par le Coordinator) ─────────────

    def on_tado_native_detected(self, zone_id: int, is_open: bool) -> None:
        """Gère la détection de fenêtre native de Tado lors des rafraîchissements."""
        if not self.is_enabled:
            return

        if is_open:
            if zone_id not in self._episodes:
                self.hass.async_create_task(self._cut(zone_id, "tado_native"))
        else:
            ep = self._episodes.get(zone_id)
            if ep and ep.reason == "tado_native":
                self.hass.async_create_task(self._restore(zone_id))

    # ── Coupure et Rétablissement ───────────────────────────────

    async def _cut(self, zone_id: int, reason: Reason) -> None:
        """Coupe le chauffage de la pièce suite à une détection d'ouverture."""
        zones = (self.coordinator.data or {}).get("zones", {})
        zdata = zones.get(zone_id)
        if not zdata:
            return

        # Si l'épisode est déjà en cours, rien à faire
        if zone_id in self._episodes:
            return

        current_setting = zdata.get("setting", {})
        current_power = current_setting.get("power", "OFF") if current_setting else "OFF"
        current_overlay = zdata.get("overlay")

        # Règle : Si la zone est déjà OFF, aucun appel API inutile nécessaire (économie quota)
        if current_power == "OFF":
            _LOGGER.debug(
                "DomoLink-Tado WindowGuard: Zone %s déjà éteinte, enregistrement sans appel API",
                zone_id,
            )
            episode = WindowEpisode(
                zone_id=zone_id,
                started_at=time.time(),
                reason=reason,
                previous_overlay=current_overlay,
                we_own_overlay=False,
            )
            self._episodes[zone_id] = episode
            await self._async_save_store()
            self.hass.bus.async_fire(
                EVENT_WINDOW_OPENED, {"zone_id": zone_id, "reason": reason}
            )
            self.coordinator.async_update_listeners()
            return

        # Vérification du budget API Tado
        budget = getattr(self.coordinator.client, "budget", None)
        if budget and not budget.can_spend("command"):
            _LOGGER.warning(
                "DomoLink-Tado WindowGuard: Quota API Tado trop bas pour couper la zone %s",
                zone_id,
            )
            return

        duration = self.max_duration
        zname = zdata.get("name", f"Zone {zone_id}")
        _LOGGER.info(
            "DomoLink-Tado WindowGuard: Fenêtre ouverte (%s) dans %s! Coupure pendant %ss",
            reason,
            zname,
            duration,
        )

        try:
            await self.coordinator.client.set_zone_overlay(
                home_id=self.coordinator.home_id,
                zone_id=zone_id,
                power="OFF",
                termination_type=OVERLAY_TIMER,
                duration_seconds=duration,
            )
            # Patch optimiste local
            if self.coordinator.data and "zones" in self.coordinator.data:
                if zone_id in self.coordinator.data["zones"]:
                    self.coordinator.data["zones"][zone_id]["setting"] = {"power": "OFF"}
                    self.coordinator.data["zones"][zone_id]["overlay"] = {
                        "setting": {"power": "OFF"},
                        "termination": {"type": OVERLAY_TIMER, "durationInSeconds": duration},
                    }

            episode = WindowEpisode(
                zone_id=zone_id,
                started_at=time.time(),
                reason=reason,
                previous_overlay=current_overlay,
                we_own_overlay=True,
            )
            self._episodes[zone_id] = episode
            await self._async_save_store()
            self.hass.bus.async_fire(
                EVENT_WINDOW_OPENED, {"zone_id": zone_id, "reason": reason}
            )
            self.coordinator.async_update_listeners()
        except Exception as err:
            _LOGGER.warning(
                "DomoLink-Tado WindowGuard: Échec coupure automatique zone %s: %s",
                zone_id,
                err,
            )

    async def _restore(self, zone_id: int) -> None:
        """Rétablit le chauffage de la pièce après la fermeture des fenêtres."""
        episode = self._episodes.get(zone_id)
        if not episode:
            return

        zones = (self.coordinator.data or {}).get("zones", {})
        zdata = zones.get(zone_id, {})

        # Règle anti-écrasement : vérifier si l'utilisateur a modifié la consigne manuellement
        # Si la zone n'est plus à l'arrêt ou a été modifiée par l'utilisateur, ne pas écraser
        current_setting = zdata.get("setting", {})
        current_power = current_setting.get("power", "OFF") if current_setting else "OFF"
        if episode.we_own_overlay and current_power != "OFF":
            _LOGGER.info(
                "DomoLink-Tado WindowGuard: L'utilisateur a modifié la consigne de la zone %s pendant l'aération. Rétablissement ignoré.",
                zone_id,
            )
            self._episodes.pop(zone_id, None)
            await self._async_save_store()
            self.hass.bus.async_fire(
                EVENT_WINDOW_CLOSED, {"zone_id": zone_id, "aborted_user_override": True}
            )
            self.coordinator.async_update_listeners()
            return

        if episode.we_own_overlay:
            budget = getattr(self.coordinator.client, "budget", None)
            if budget and not budget.can_spend("command"):
                _LOGGER.warning(
                    "DomoLink-Tado WindowGuard: Quota API Tado insuffisant pour rétablir la zone %s",
                    zone_id,
                )
                return

            try:
                if (
                    self.restore_mode == WINDOW_RESTORE_PREVIOUS
                    and episode.previous_overlay
                ):
                    prev_set = episode.previous_overlay.get("setting", {})
                    prev_power = prev_set.get("power", "ON")
                    prev_temp = (
                        prev_set.get("temperature", {}).get("celsius")
                        if prev_set.get("temperature")
                        else None
                    )
                    await self.coordinator.client.set_zone_overlay(
                        home_id=self.coordinator.home_id,
                        zone_id=zone_id,
                        power=prev_power,
                        temperature=prev_temp,
                    )
                else:
                    await self.coordinator.async_resume_schedule(zone_id)

                _LOGGER.info(
                    "DomoLink-Tado WindowGuard: Fenêtres refermées, chauffage rétabli dans la zone %s",
                    zone_id,
                )
            except Exception as err:
                _LOGGER.warning(
                    "DomoLink-Tado WindowGuard: Erreur lors du rétablissement de la zone %s: %s",
                    zone_id,
                    err,
                )

        self._episodes.pop(zone_id, None)
        await self._async_save_store()
        self.hass.bus.async_fire(
            EVENT_WINDOW_CLOSED, {"zone_id": zone_id, "restored": True}
        )
        self.coordinator.async_update_listeners()

    async def _async_save_store(self) -> None:
        """Sauvegarde les épisodes en cours dans le Store HA."""
        if not self._store:
            return
        try:
            data = {str(zid): ep.to_dict() for zid, ep in self._episodes.items()}
            await self._store.async_save(data)
        except Exception as err:
            _LOGGER.warning(
                "DomoLink-Tado WindowGuard: Erreur sauvegarde épisodes Store: %s", err
            )
