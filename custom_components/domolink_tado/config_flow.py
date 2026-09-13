"""Config flow for DomoLink-Tado integration with OAuth2 Device Authorization Flow."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ADAPTIVE_POLLING,
    CONF_AUTO_WINDOW_DURATION,
    CONF_AUTO_WINDOW_ENABLED,
    CONF_ECO_TEMP,
    CONF_EXPIRES_AT,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_OVERLAY_DURATION,
    CONF_OVERLAY_MODE,
    CONF_REFRESH_TOKEN,
    CONF_ROOM_LABELS,
    DEFAULT_ADAPTIVE_POLLING,
    DEFAULT_AUTO_WINDOW_DURATION,
    DEFAULT_AUTO_WINDOW_ENABLED,
    DEFAULT_ECO_TEMP,
    DEFAULT_OVERLAY_DURATION,
    DEFAULT_OVERLAY_MODE,
    DOMAIN,
    NAME,
    OVERLAY_MANUAL,
    OVERLAY_NEXT_TIME_BLOCK,
    OVERLAY_TIMER,
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
            if not self._device_code:
                return await self.async_step_user()

            try:
                tokens = await TadoClient.poll_device_token(session, self._device_code)
                _LOGGER.info("DomoLink-Tado: Device Flow token received successfully")
                client = TadoClient(
                    session=session,
                    access_token=tokens["access_token"],
                    refresh_token=tokens.get("refresh_token"),
                    expires_at=tokens.get("expires_at"),
                )
                me = await client.get_me()
                homes = me.get("homes", [])
                if not homes:
                    return self.async_abort(reason="no_homes_found")

                primary_home = homes[0]
                home_id = primary_home["id"]
                home_name = primary_home.get("name", "Tado Home")

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

                self._tokens = tokens
                self._home_id = home_id
                self._home_name = home_name

                # Discover zones for the labels configuration step
                try:
                    self._discovered_zones = await client.get_zones(home_id)
                except Exception as err:
                    _LOGGER.warning("Could not pre-fetch zones for labeling: %s", err)
                    self._discovered_zones = []

                if self._discovered_zones:
                    return await self.async_step_labels()

                # Fallback if no zones or error
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

            except TadoDeviceFlowPending:
                _LOGGER.debug("DomoLink-Tado: Device authorization still pending on Tado...")
                errors["base"] = "authorization_pending"
            except TadoDeviceFlowExpired:
                _LOGGER.warning("DomoLink-Tado: Device code expired or invalidated")
                errors["base"] = "code_expired"
                self._device_code = None  # Restart flow next time
            except (TadoAuthError, TadoError) as err:
                _LOGGER.error("DomoLink-Tado: Error during Tado token polling/login: %s", err)
                errors["base"] = "cannot_connect"
                self._device_code = None
            except Exception as err:
                _LOGGER.exception("DomoLink-Tado: Unexpected error during Tado login: %s", err)
                errors["base"] = "unknown"
                self._device_code = None

        # If we do not have an active device code yet, request one
        if not self._device_code:
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
            data_schema=vol.Schema({}),
            errors=errors,
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
                    CONF_ECO_TEMP: DEFAULT_ECO_TEMP,
                    CONF_ADAPTIVE_POLLING: DEFAULT_ADAPTIVE_POLLING,
                },
            )

        schema_dict: dict[Any, Any] = {}
        for z in self._discovered_zones:
            name = z.get("name", f"Pièce {z.get('id')}")
            # Voluptuous optional string with room name
            schema_dict[vol.Optional(f"zone_{z['id']}", description={"suggested_value": ""})] = str

        room_names = ", ".join(z.get("name", "") for z in self._discovered_zones)
        return self.async_show_form(
            step_id="labels",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "room_names": room_names,
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication with Tado."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._device_code = None
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for DomoLink-Tado."""
        return DomolinkTadoOptionsFlow(config_entry)


class DomolinkTadoOptionsFlow(config_entries.OptionsFlow):
    """Handle options for DomoLink-Tado."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Preserve existing options (e.g. labels if not in this form)
            current_options = dict(self.config_entry.options)
            current_options.update(user_input)
            return self.async_create_entry(title="", data=current_options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
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
                }
            ),
        )
