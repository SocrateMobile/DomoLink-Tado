"""Config flow for DomoLink-Tado integration with OAuth2 Device Authorization Flow."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ADAPTIVE_POLLING,
    CONF_AUTO_WINDOW_DURATION,
    CONF_AUTO_WINDOW_ENABLED,
    CONF_DYNAMIC_WINDOW_DROP,
    CONF_ECO_TEMP,
    CONF_EXPIRES_AT,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_OUTDOOR_WEATHER_ENTITY,
    CONF_OVERLAY_DURATION,
    CONF_OVERLAY_MODE,
    CONF_PREHEAT_ENABLED,
    CONF_PREHEAT_MAX_DURATION,
    CONF_PREHEAT_MODE,
    CONF_REFRESH_TOKEN,
    CONF_ROOM_LABELS,
    DEFAULT_ADAPTIVE_POLLING,
    DEFAULT_AUTO_WINDOW_DURATION,
    DEFAULT_AUTO_WINDOW_ENABLED,
    DEFAULT_DYNAMIC_WINDOW_DROP,
    DEFAULT_ECO_TEMP,
    DEFAULT_OVERLAY_DURATION,
    DEFAULT_OVERLAY_MODE,
    DEFAULT_PREHEAT_ENABLED,
    DEFAULT_PREHEAT_MAX_DURATION,
    DEFAULT_PREHEAT_MODE,
    DOMAIN,
    NAME,
    OVERLAY_MANUAL,
    OVERLAY_NEXT_TIME_BLOCK,
    OVERLAY_TIMER,
    PREHEAT_MODE_ADVISORY,
    PREHEAT_MODE_AUTONOMOUS,
)
from .tado_api import (
    TadoAuthError,
    TadoClient,
    TadoDeviceAuthResponse,
    TadoDeviceFlowExpired,
    TadoDeviceFlowPending,
    TadoError,
)

_LOGGER = logging.getLogger(__name__)


class DomolinkTadoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DomoLink-Tado."""

    VERSION = 1

    def __init__(self) -> None:
        self._device_code: str | None = None
        self._user_code: str | None = None
        self._verification_uri: str = "https://login.tado.com/oauth2/device"
        self._verification_uri_complete: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None
        self._tokens: dict[str, Any] | None = None
        self._home_id: int | None = None
        self._home_name: str = "Tado Home"
        self._discovered_zones: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step starting Device Flow."""
        session = async_get_clientsession(self.hass)
        errors: dict[str, str] = {}

        if user_input is not None:
            # User clicked submit to verify that they approved on tado.com/device
            if not self._device_code and not self._tokens:
                return await self.async_step_user()

            try:
                # 1. Échange du code contre les jetons OAuth2 (si pas déjà en mémoire)
                if not self._tokens:
                    _LOGGER.info("DomoLink-Tado: Polling Tado Device Flow token...")
                    tokens = await TadoClient.poll_device_token(session, self._device_code)
                    _LOGGER.info("DomoLink-Tado: Device Flow token received successfully!")
                    self._tokens = tokens
                else:
                    _LOGGER.info("DomoLink-Tado: Reusing previously fetched token")
                    tokens = self._tokens

                # Petite pause préventive de 1.2s pour éviter le rate limit en rafale (burst)
                await asyncio.sleep(1.2)

                # 2. Récupération du profil et de la maison
                client = TadoClient(
                    session=session,
                    access_token=tokens["access_token"],
                    refresh_token=tokens.get("refresh_token"),
                    expires_at=tokens.get("expires_at"),
                )
                me = await client.get_me()
                if not me or not isinstance(me, dict):
                    raise TadoError("Serveurs Tado temporairement indisponibles (profil non récupéré).")
                home_id: int | None = None
                home_name: str = "Tado Home"

                # 1. Si l'utilisateur a saisi manuellement son Home ID, l'utiliser directement (Bypass /me)
                raw_manual_id = user_input.get(CONF_HOME_ID)
                if raw_manual_id:
                    try:
                        val = int(str(raw_manual_id).strip())
                        if val > 0:
                            home_id = val
                            home_name = str(user_input.get(CONF_HOME_NAME, "Maison Tado")).strip() or "Maison Tado"
                    except (ValueError, TypeError):
                        pass

                # 2. Récupération automatique du profil et du domicile si non fourni manuellement
                if home_id is None:
                    client = TadoClient(
                        session=session,
                        access_token=tokens["access_token"],
                        refresh_token=tokens.get("refresh_token"),
                        expires_at=tokens.get("expires_at"),
                    )
                    me = await client.get_me()
                    if not me or not isinstance(me, dict):
                        raise TadoError("Serveurs Tado temporairement indisponibles (profil non récupéré).")
                    # Extraction multi-formats du domicile (compatible toutes variantes de l'API Tado)
                    homes = me.get("homes")
                    if isinstance(homes, list) and len(homes) > 0:
                        primary_home = homes[0]
                        if isinstance(primary_home, dict):
                            home_id = primary_home.get("id") or primary_home.get("homeId")
                            home_name = primary_home.get("name") or "Tado Home"
                        elif isinstance(primary_home, (int, str)):
                            try:
                                home_id = int(primary_home)
                            except (ValueError, TypeError):
                                pass

                    if home_id is None:
                        raw_home_id = me.get("homeId") or me.get("id")
                        if raw_home_id is not None:
                            try:
                                home_id = int(raw_home_id)
                            except (ValueError, TypeError):
                                pass
                        if isinstance(me.get("name"), str) and me.get("name"):
                            home_name = me["name"]

                    if not home_id:
                        return self.async_abort(reason="no_homes_found")

                if self._reauth_entry:
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry,
                        data={
                            **self._reauth_entry.data,
                            CONF_ACCESS_TOKEN: tokens["access_token"],
                            CONF_REFRESH_TOKEN: tokens.get("refresh_token"),
                            CONF_EXPIRES_AT: tokens["expires_at"],
                        },
                    )
                    await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

                await self.async_set_unique_id(str(home_id))
                self._abort_if_unique_id_configured()

                self._home_id = home_id
                self._home_name = home_name

                # Création directe de l'entrée avec options par défaut (expérience standard HA)
                return self.async_create_entry(
                    title=f"DomoLink Tado ({home_name})",
                    data={
                        CONF_HOME_ID: home_id,
                        CONF_HOME_NAME: home_name,
                        CONF_ACCESS_TOKEN: tokens["access_token"],
                        CONF_REFRESH_TOKEN: tokens.get("refresh_token"),
                        CONF_EXPIRES_AT: tokens["expires_at"],
                    },
                    options={
                        CONF_ROOM_LABELS: {},
                        CONF_OVERLAY_MODE: DEFAULT_OVERLAY_MODE,
                        CONF_OVERLAY_DURATION: DEFAULT_OVERLAY_DURATION,
                        CONF_AUTO_WINDOW_ENABLED: DEFAULT_AUTO_WINDOW_ENABLED,
                        CONF_AUTO_WINDOW_DURATION: DEFAULT_AUTO_WINDOW_DURATION,
                        CONF_ECO_TEMP: DEFAULT_ECO_TEMP,
                        CONF_ADAPTIVE_POLLING: DEFAULT_ADAPTIVE_POLLING,
                    },
                )

            except AbortFlow:
                raise
            except TadoDeviceFlowPending:
                _LOGGER.debug("DomoLink-Tado: Device authorization still pending on Tado...")
                errors["base"] = "authorization_pending"
                # Keep active device code! User validates on tado.com then clicks Valider again
            except TadoDeviceFlowExpired:
                _LOGGER.warning("DomoLink-Tado: Device code expired or invalidated")
                errors["base"] = "code_expired"
                self._device_code = None  # Restart flow next time
                self._tokens = None
            except (TadoAuthError, TadoError) as err:
                _LOGGER.error("DomoLink-Tado: Error during Tado token polling/login: %s", err)
                if "429" in str(err) or "Rate Limit" in str(err) or "saturé" in str(err):
                    errors["base"] = "rate_limit"
                    # Si les tokens OAuth sont déjà en mémoire mais que /me est bloqué :
                    # Basculer immédiatement vers la saisie manuelle du Home ID pour débloquer l'utilisateur
                    if self._tokens:
                        return await self.async_step_manual_home()
                else:
                    errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("DomoLink-Tado: Unexpected error during Tado login: %s", err)
                errors["base"] = "unknown"
                if not self._tokens:
                    self._device_code = None

        # If we do not have an active device code yet and no tokens, request one
        if not self._device_code and not self._tokens:
            try:
                auth_resp: TadoDeviceAuthResponse = await TadoClient.request_device_code(session)
                self._device_code = auth_resp.device_code
                self._user_code = auth_resp.user_code
                self._verification_uri = auth_resp.verification_uri
                self._verification_uri_complete = auth_resp.verification_uri_complete
            except Exception as err:
                _LOGGER.error("Could not start Tado device authorization flow: %s", err)
                return self.async_abort(reason="cannot_start_flow")

        link = self._verification_uri_complete or self._verification_uri
        return self.async_show_form(
            step_id="user",
            description_placeholders={
                "user_code": self._user_code or "",
                "verification_uri": link,
            },
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_HOME_ID): vol.Coerce(int),
                }
            ),
            errors=errors,
        )

    async def async_step_manual_home(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow manual entry of Home ID when Tado /me is rate-limited."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_id = user_input.get(CONF_HOME_ID)
            try:
                home_id = int(str(raw_id).strip())
                if home_id <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                errors["base"] = "invalid_home_id"
            else:
                home_name = str(user_input.get(CONF_HOME_NAME, "Maison Tado")).strip() or "Maison Tado"

                tokens = self._tokens or {}
                if self._reauth_entry:
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry,
                        data={
                            **self._reauth_entry.data,
                            CONF_ACCESS_TOKEN: tokens.get("access_token", ""),
                            CONF_REFRESH_TOKEN: tokens.get("refresh_token"),
                            CONF_EXPIRES_AT: tokens.get("expires_at", time.time() + 3600),
                        },
                    )
                    await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

                await self.async_set_unique_id(str(home_id))
                self._abort_if_unique_id_configured()

                self._home_id = home_id
                self._home_name = home_name

                return self.async_create_entry(
                    title=f"DomoLink Tado ({home_name})",
                    data={
                        CONF_HOME_ID: home_id,
                        CONF_HOME_NAME: home_name,
                        CONF_ACCESS_TOKEN: tokens.get("access_token", ""),
                        CONF_REFRESH_TOKEN: tokens.get("refresh_token"),
                        CONF_EXPIRES_AT: tokens.get("expires_at", time.time() + 3600),
                    },
                    options={
                        CONF_ROOM_LABELS: {},
                        CONF_OVERLAY_MODE: DEFAULT_OVERLAY_MODE,
                        CONF_OVERLAY_DURATION: DEFAULT_OVERLAY_DURATION,
                        CONF_AUTO_WINDOW_ENABLED: DEFAULT_AUTO_WINDOW_ENABLED,
                        CONF_AUTO_WINDOW_DURATION: DEFAULT_AUTO_WINDOW_DURATION,
                        CONF_DYNAMIC_WINDOW_DROP: DEFAULT_DYNAMIC_WINDOW_DROP,
                        CONF_PREHEAT_ENABLED: DEFAULT_PREHEAT_ENABLED,
                        CONF_PREHEAT_MODE: DEFAULT_PREHEAT_MODE,
                        CONF_PREHEAT_MAX_DURATION: DEFAULT_PREHEAT_MAX_DURATION,
                        CONF_ECO_TEMP: DEFAULT_ECO_TEMP,
                        CONF_ADAPTIVE_POLLING: DEFAULT_ADAPTIVE_POLLING,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOME_ID): int,
                vol.Optional(CONF_HOME_NAME, default="Maison Tado"): str,
            }
        )
        return self.async_show_form(
            step_id="manual_home",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "tado_url": "https://my.tado.com/webapp/",
            },
        )

    async def async_step_labels(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Allow user to assign custom labels/tags to each discovered room during initial setup."""
        if user_input is not None:
            labels_map: dict[str, list[str]] = {}
            for z in self._discovered_zones:
                zid = str(z["id"])
                # Key in form is either "zone_1" or the room name
                key = f"zone_{zid}"
                raw_val = user_input.get(key, "")
                if not raw_val and z.get("name") in user_input:
                    raw_val = user_input[z["name"]]
                tags = [t.strip() for t in str(raw_val).split(",") if t.strip()]
                if tags:
                    labels_map[zid] = tags

            return self.async_create_entry(
                title=f"DomoLink Tado ({self._home_name})",
                data={
                    CONF_HOME_ID: self._home_id,
                    CONF_HOME_NAME: self._home_name,
                    CONF_ACCESS_TOKEN: self._tokens["access_token"] if self._tokens else "",
                    CONF_REFRESH_TOKEN: self._tokens.get("refresh_token") if self._tokens else None,
                    CONF_EXPIRES_AT: self._tokens.get("expires_at") if self._tokens else None,
                },
                options={
                    CONF_ROOM_LABELS: labels_map,
                    CONF_OVERLAY_MODE: DEFAULT_OVERLAY_MODE,
                    CONF_OVERLAY_DURATION: DEFAULT_OVERLAY_DURATION,
                    CONF_AUTO_WINDOW_ENABLED: DEFAULT_AUTO_WINDOW_ENABLED,
                    CONF_AUTO_WINDOW_DURATION: DEFAULT_AUTO_WINDOW_DURATION,
                    CONF_DYNAMIC_WINDOW_DROP: DEFAULT_DYNAMIC_WINDOW_DROP,
                    CONF_PREHEAT_ENABLED: DEFAULT_PREHEAT_ENABLED,
                    CONF_PREHEAT_MODE: DEFAULT_PREHEAT_MODE,
                    CONF_PREHEAT_MAX_DURATION: DEFAULT_PREHEAT_MAX_DURATION,
                    CONF_ECO_TEMP: DEFAULT_ECO_TEMP,
                    CONF_ADAPTIVE_POLLING: DEFAULT_ADAPTIVE_POLLING,
                },
            )

        schema_dict: dict[Any, Any] = {}
        for z in self._discovered_zones:
            zid = str(z.get("id", ""))
            if not zid:
                continue
            schema_dict[vol.Optional(f"zone_{zid}", default="")] = str

        room_names = ", ".join(str(z.get("name") or f"Pièce {z.get('id', '')}") for z in self._discovered_zones)
        return self.async_show_form(
            step_id="labels",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "room_names": room_names,
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication request from Home Assistant."""
        entry_id = self.context.get("entry_id")
        if entry_id:
            self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        elif hasattr(self, "_get_reauth_entry"):
            self._reauth_entry = self._get_reauth_entry()
        self._device_code = None
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm and start device flow for re-authentication."""
        return await self.async_step_user(user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reconfiguration request from Home Assistant UI."""
        entry_id = self.context.get("entry_id")
        if entry_id:
            self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        elif hasattr(self, "_get_reconfigure_entry"):
            self._reauth_entry = self._get_reconfigure_entry()
        self._device_code = None
        return await self.async_step_user(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for DomoLink-Tado."""
        return DomolinkTadoOptionsFlow(config_entry)


class DomolinkTadoOptionsFlow(config_entries.OptionsFlow):
    """Handle options for DomoLink-Tado with optional re-authentication trigger."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._device_code: str | None = None
        self._user_code: str | None = None
        self._verification_uri: str = "https://login.tado.com/oauth2/device"
        self._verification_uri_complete: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            if user_input.get("reauth_trigger"):
                return await self.async_step_reauth_device()

            # Preserve existing options (e.g. labels if not in this form)
            current_options = dict(self.config_entry.options)
            clean_input = {k: v for k, v in user_input.items() if k != "reauth_trigger"}
            current_options.update(clean_input)
            return self.async_create_entry(title="", data=current_options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional("reauth_trigger", default=False): bool,
                    vol.Optional(
                        CONF_OVERLAY_MODE,
                        default=self.config_entry.options.get(CONF_OVERLAY_MODE, DEFAULT_OVERLAY_MODE),
                    ): vol.In(
                        {
                            OVERLAY_NEXT_TIME_BLOCK: "Jusqu'au prochain changement de programmation (Auto)",
                            OVERLAY_MANUAL: "Permanent (jusqu'à annulation manuelle)",
                            OVERLAY_TIMER: "Minuterie (durée personnalisée)",
                        }
                    ),
                    vol.Optional(
                        CONF_OVERLAY_DURATION,
                        default=self.config_entry.options.get(
                            CONF_OVERLAY_DURATION, DEFAULT_OVERLAY_DURATION
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                    vol.Optional(
                        CONF_AUTO_WINDOW_ENABLED,
                        default=self.config_entry.options.get(
                            CONF_AUTO_WINDOW_ENABLED, DEFAULT_AUTO_WINDOW_ENABLED
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_AUTO_WINDOW_DURATION,
                        default=self.config_entry.options.get(
                            CONF_AUTO_WINDOW_DURATION, DEFAULT_AUTO_WINDOW_DURATION
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=7200)),
                    vol.Optional(
                        CONF_DYNAMIC_WINDOW_DROP,
                        default=self.config_entry.options.get(
                            CONF_DYNAMIC_WINDOW_DROP, DEFAULT_DYNAMIC_WINDOW_DROP
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_PREHEAT_ENABLED,
                        default=self.config_entry.options.get(
                            CONF_PREHEAT_ENABLED, DEFAULT_PREHEAT_ENABLED
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_PREHEAT_MODE,
                        default=self.config_entry.options.get(
                            CONF_PREHEAT_MODE, DEFAULT_PREHEAT_MODE
                        ),
                    ): vol.In(
                        {
                            PREHEAT_MODE_ADVISORY: "Conseiller (Capteurs & Alertes uniquement)",
                            PREHEAT_MODE_AUTONOMOUS: "Autonome (Déclenchement automatique de la chauffe)",
                        }
                    ),
                    vol.Optional(
                        CONF_PREHEAT_MAX_DURATION,
                        default=self.config_entry.options.get(
                            CONF_PREHEAT_MAX_DURATION, DEFAULT_PREHEAT_MAX_DURATION
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=240)),
                    vol.Optional(
                        CONF_ECO_TEMP,
                        default=self.config_entry.options.get(
                            CONF_ECO_TEMP, DEFAULT_ECO_TEMP
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=25.0)),
                    vol.Optional(
                        CONF_ADAPTIVE_POLLING,
                        default=self.config_entry.options.get(
                            CONF_ADAPTIVE_POLLING, DEFAULT_ADAPTIVE_POLLING
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_OUTDOOR_WEATHER_ENTITY,
                        default=self.config_entry.options.get(
                            CONF_OUTDOOR_WEATHER_ENTITY, ""
                        ),
                    ): str,
                }
            ),
        )

    async def async_step_reauth_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step to allow generating and validating a new token directly from options."""
        session = async_get_clientsession(self.hass)
        errors: dict[str, str] = {}

        if user_input is not None and self._device_code:
            try:
                tokens = await TadoClient.poll_device_token(session, self._device_code)
                _LOGGER.info("DomoLink-Tado: Re-auth token received via Options Flow")
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        **self.config_entry.data,
                        CONF_ACCESS_TOKEN: tokens["access_token"],
                        CONF_REFRESH_TOKEN: tokens.get("refresh_token"),
                        CONF_EXPIRES_AT: tokens["expires_at"],
                    },
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data=self.config_entry.options)
            except TadoDeviceFlowPending:
                errors["base"] = "authorization_pending"
            except TadoDeviceFlowExpired:
                _LOGGER.warning("DomoLink-Tado: Re-auth device code expired")
                errors["base"] = "code_expired"
                self._device_code = None
            except (TadoAuthError, TadoError) as err:
                _LOGGER.error("DomoLink-Tado: Re-auth error: %s", err)
                if "429" in str(err) or "Rate Limit" in str(err) or "saturé" in str(err):
                    errors["base"] = "rate_limit"
                else:
                    errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.error("DomoLink-Tado: Re-auth unexpected error: %s", err)
                errors["base"] = "cannot_connect"
                self._device_code = None

        if not self._device_code:
            try:
                auth_resp = await TadoClient.request_device_code(session)
                self._device_code = auth_resp.device_code
                self._user_code = auth_resp.user_code
                self._verification_uri = auth_resp.verification_uri
                self._verification_uri_complete = auth_resp.verification_uri_complete
            except Exception as err:
                _LOGGER.error("Could not start device flow in options: %s", err)
                return self.async_abort(reason="cannot_start_flow")

        link = self._verification_uri_complete or self._verification_uri
        return self.async_show_form(
            step_id="reauth_device",
            description_placeholders={
                "user_code": self._user_code or "",
                "verification_uri": link,
            },
            data_schema=vol.Schema({}),
            errors=errors,
        )
