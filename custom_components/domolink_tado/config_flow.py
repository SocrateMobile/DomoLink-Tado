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
    CONF_EXPIRES_AT,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_OVERLAY_DURATION,
    CONF_OVERLAY_MODE,
    CONF_REFRESH_TOKEN,
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
        self._verification_uri: str = "https://tado.com/device"
        self._verification_uri_complete: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

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
                # Success! Now fetch home info
                client = TadoClient(session, access_token=tokens["access_token"])
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

                return self.async_create_entry(
                    title=f"DomoLink Tado ({home_name})",
                    data={
                        CONF_HOME_ID: home_id,
                        CONF_HOME_NAME: home_name,
                        CONF_ACCESS_TOKEN: tokens["access_token"],
                        CONF_REFRESH_TOKEN: tokens.get("refresh_token"),
                        CONF_EXPIRES_AT: tokens["expires_at"],
                    },
                )

            except TadoDeviceFlowPending:
                errors["base"] = "authorization_pending"
            except TadoDeviceFlowExpired:
                errors["base"] = "code_expired"
                self._device_code = None  # Restart flow next time
            except (TadoAuthError, TadoError) as err:
                _LOGGER.error("Error during Tado token polling: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error during Tado login: %s", err)
                errors["base"] = "unknown"

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
            return self.async_create_entry(title="", data=user_input)

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
                }
            ),
        )
