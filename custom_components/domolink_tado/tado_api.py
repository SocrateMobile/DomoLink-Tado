"""Asynchronous Tado API client with bulletproof OAuth2 Device Flow & token persistence."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import time
from typing import Any, Callable, Coroutine

import aiohttp

from .const import (
    OVERLAY_MANUAL,
    OVERLAY_NEXT_TIME_BLOCK,
    OVERLAY_TIMER,
    TADO_API_BASE,
    TADO_CLIENT_ID,
    TADO_DEVICE_AUTH_URL,
    TADO_SCOPE,
    TADO_TOKEN_URL,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_USER_AGENT = "PyTado/0.18.16"
DEFAULT_REFERER = "https://app.tado.com/"

_QUOTA_REGEX = re.compile(r"q=(\d+)")
_REMAINING_REGEX = re.compile(r"r=(\d+)")
_RESET_REGEX = re.compile(r"t=(\d+)")


class TadoError(Exception):
    """Base exception for Tado client."""


class TadoAuthError(TadoError):
    """Exception raised when authentication fails."""


class TadoDeviceFlowPending(TadoError):
    """Exception raised when user has not yet authorized the device."""


class TadoDeviceFlowExpired(TadoError):
    """Exception raised when device code has expired."""


@dataclass
class TadoDeviceAuthResponse:
    """Device authorization initiation response."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_in: int
    interval: int


class TadoClient:
    """Asynchronous client for Tado API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str | None = None,
        refresh_token: str | None = None,
        expires_at: float | None = None,
        token_update_callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.session = session
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at if expires_at is not None else (time.time() + 3600 if access_token else 0.0)
        self.token_update_callback = token_update_callback
        self._refresh_lock = asyncio.Lock()
        self.rate_limit_limit: int | None = None
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset_seconds: int | None = None
        self.rate_limit_last_update: float | None = None
        self.requests_count: int = 0

    @staticmethod
    async def request_device_code(session: aiohttp.ClientSession) -> TadoDeviceAuthResponse:
        """Start the OAuth2 Device Authorization Flow with Tado."""
        data = {
            "client_id": TADO_CLIENT_ID,
            "scope": TADO_SCOPE,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": DEFAULT_REFERER,
            "User-Agent": DEFAULT_USER_AGENT,
        }

        try:
            async with session.post(TADO_DEVICE_AUTH_URL, data=data, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise TadoAuthError(f"Device code request failed ({resp.status}): {text}")
                res = await resp.json()
                verification_uri = res.get("verification_uri", "https://login.tado.com/oauth2/device")
                user_code = res["user_code"]
                complete_url = res.get("verification_uri_complete")
                if not complete_url:
                    complete_url = f"{verification_uri}?user_code={user_code}&client_id={TADO_CLIENT_ID}"
                elif "client_id=" not in complete_url:
                    sep = "&" if "?" in complete_url else "?"
                    complete_url = f"{complete_url}{sep}client_id={TADO_CLIENT_ID}"

                return TadoDeviceAuthResponse(
                    device_code=res["device_code"],
                    user_code=user_code,
                    verification_uri=verification_uri,
                    verification_uri_complete=complete_url,
                    expires_in=res.get("expires_in", 300),
                    interval=res.get("interval", 5),
                )
        except aiohttp.ClientError as err:
            raise TadoError(f"Network error during device code request: {err}") from err

    @staticmethod
    async def poll_device_token(session: aiohttp.ClientSession, device_code: str) -> dict[str, Any]:
        """Poll the Tado token endpoint during device flow."""
        data = {
            "client_id": TADO_CLIENT_ID,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": DEFAULT_REFERER,
            "User-Agent": DEFAULT_USER_AGENT,
        }

        try:
            async with session.post(TADO_TOKEN_URL, data=data, headers=headers) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    access_token = res.get("access_token")
                    if not access_token:
                        raise TadoAuthError("La réponse Tado ne contient pas de jeton d'accès valide (access_token manquant).")

                    expires_in = res.get("expires_in")
                    try:
                        expires_sec = float(expires_in) if expires_in is not None else 3600.0
                    except (ValueError, TypeError):
                        expires_sec = 3600.0

                    return {
                        "access_token": access_token,
                        "refresh_token": res.get("refresh_token"),
                        "expires_at": time.time() + expires_sec,
                    }

                if resp.status == 429:
                    _LOGGER.warning("Tado token polling rate limit (429), user should slow down")
                    raise TadoDeviceFlowPending("slow_down")

                try:
                    res = await resp.json()
                    error = res.get("error")
                    error_desc = res.get("error_description", error)
                except Exception:
                    error = None
                    error_desc = await resp.text()

                if error in ("authorization_pending", "slow_down"):
                    raise TadoDeviceFlowPending(error)
                if error in ("expired_token", "access_denied", "invalid_grant", "bad_verification_code"):
                    raise TadoDeviceFlowExpired(error)

                raise TadoAuthError(f"Token polling error ({resp.status}): {error_desc}")
        except aiohttp.ClientError as err:
            raise TadoError(f"Erreur de connexion lors du polling: {err}") from err

    async def async_get_valid_token(self) -> str:
        """Ensure the current access token is valid, refreshing if needed."""
        if self.access_token and time.time() < (self.expires_at - 120):
            return self.access_token

        async with self._refresh_lock:
            # Check again inside the lock
            if self.access_token and time.time() < (self.expires_at - 120):
                return self.access_token

            if not self.refresh_token:
                if self.access_token and time.time() < self.expires_at:
                    _LOGGER.warning("No refresh token available; using existing access token")
                    return self.access_token
                raise TadoAuthError("No refresh token available and access token has expired")

            return await self.async_refresh_token()

    @staticmethod
    def _calculate_rate_limit_delay(
        resp: aiohttp.ClientResponse,
        attempt: int,
        default_base: float = 2.5,
        max_delay: float = 30.0,
    ) -> float:
        """Extract Retry-After or RateLimit headers from Tado, fallback to exponential backoff."""
        wait_sec: float | None = None
        for hdr in (
            "Retry-After",
            "ratelimit-reset",
            "RateLimit-Reset",
            "X-RateLimit-Reset",
            "ratelimit",
            "RateLimit",
        ):
            val = resp.headers.get(hdr)
            if not val:
                continue
            # Match t=XXX in ratelimit header (ex: '"perday";r=0;t=120')
            m = re.search(r"t=([0-9]+(?:\.[0-9]+)?)", val)
            if m:
                try:
                    wait_sec = float(m.group(1))
                    break
                except (ValueError, TypeError):
                    pass
            try:
                f_val = float(val)
                if f_val > 1000000000:
                    wait_sec = max(1.0, f_val - time.time())
                else:
                    wait_sec = f_val
                break
            except (ValueError, TypeError):
                pass

        if wait_sec is None or wait_sec <= 0:
            wait_sec = default_base * (2 ** attempt)
        return min(wait_sec, max_delay)

    def _parse_ratelimit_headers(self, headers: Any) -> None:
        """Parse RFC RateLimit and RateLimit-Policy headers returned by Tado."""
        if not headers:
            return

        policy = headers.get("RateLimit-Policy") or headers.get("ratelimit-policy") or ""
        rl = headers.get("RateLimit") or headers.get("ratelimit") or ""
        reset_hdr = headers.get("RateLimit-Reset") or headers.get("ratelimit-reset") or ""

        limit_match = _QUOTA_REGEX.search(policy)
        if limit_match:
            try:
                self.rate_limit_limit = int(limit_match.group(1))
            except (ValueError, TypeError):
                pass

        rem_match = _REMAINING_REGEX.search(rl)
        if rem_match:
            try:
                self.rate_limit_remaining = int(rem_match.group(1))
            except (ValueError, TypeError):
                pass

        reset_match = _RESET_REGEX.search(rl)
        if reset_match:
            try:
                self.rate_limit_reset_seconds = int(reset_match.group(1))
            except (ValueError, TypeError):
                pass
        elif reset_hdr:
            try:
                self.rate_limit_reset_seconds = int(reset_hdr)
            except (ValueError, TypeError):
                pass

        # Fallback pour passerelles utilisant les en-têtes X-RateLimit-*
        if self.rate_limit_limit is None:
            x_limit = headers.get("X-RateLimit-Limit") or headers.get("x-ratelimit-limit")
            if x_limit:
                try:
                    self.rate_limit_limit = int(x_limit)
                except (ValueError, TypeError):
                    pass

        if self.rate_limit_remaining is None:
            x_rem = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
            if x_rem:
                try:
                    self.rate_limit_remaining = int(x_rem)
                except (ValueError, TypeError):
                    pass

        if self.rate_limit_reset_seconds is None:
            x_reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
            if x_reset:
                try:
                    self.rate_limit_reset_seconds = int(x_reset)
                except (ValueError, TypeError):
                    pass

        if self.rate_limit_remaining is not None or self.rate_limit_limit is not None:
            self.rate_limit_last_update = time.time()

    @property
    def rate_limit_info(self) -> dict[str, Any]:
        """Return structured rate limit telemetry."""
        limit = self.rate_limit_limit
        rem = self.rate_limit_remaining
        used = None
        if limit is not None and rem is not None:
            used = max(0, limit - rem)
        elif self.requests_count > 0:
            used = self.requests_count

        return {
            "limit": limit,
            "remaining": rem,
            "used": used,
            "requests_count": self.requests_count,
            "reset_seconds": self.rate_limit_reset_seconds,
            "last_update": self.rate_limit_last_update,
        }

    async def async_refresh_token(self) -> str:
        """Refresh the access token using the stored refresh token."""
        if not self.refresh_token:
            raise TadoAuthError("No refresh token available")

        data = {
            "client_id": TADO_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": DEFAULT_REFERER,
            "User-Agent": DEFAULT_USER_AGENT,
        }

        _LOGGER.debug("Refreshing Tado OAuth token...")
        for attempt in range(4):
            _rate_limit_wait: float | None = None
            try:
                self.requests_count += 1
                async with self.session.post(TADO_TOKEN_URL, data=data, headers=headers) as resp:
                    if resp.status == 429:
                        _rate_limit_wait = self._calculate_rate_limit_delay(resp, attempt, default_base=3.0, max_delay=30.0)
                        _LOGGER.warning(
                            "Tado token refresh rate limited (429). Retrying in %.1fs (attempt %d/4)...",
                            _rate_limit_wait,
                            attempt + 1,
                        )
                        # Connexion libérée en sortant du async with AVANT le sleep
                    elif resp.status != 200:
                        text = await resp.text()
                        _LOGGER.error("Failed to refresh Tado token (%s): %s", resp.status, text)
                        raise TadoAuthError(f"Token refresh failed ({resp.status}): {text}")
                    else:
                        try:
                            res = await resp.json()
                        except (ValueError, aiohttp.ContentTypeError) as parse_err:
                            raise TadoError(f"Token refresh: invalid JSON response: {parse_err}") from parse_err
                        self.access_token = res["access_token"]
                        self.refresh_token = res.get("refresh_token", self.refresh_token)
                        self.expires_at = time.time() + res.get("expires_in", 3600)

                        _LOGGER.info("Tado OAuth token refreshed successfully (valid for %ss)", res.get("expires_in"))

                        # Persist directly to Home Assistant config entry storage!
                        if self.token_update_callback:
                            try:
                                await self.token_update_callback(
                                    {
                                        "access_token": self.access_token,
                                        "refresh_token": self.refresh_token,
                                        "expires_at": self.expires_at,
                                    }
                                )
                            except Exception as err:
                                _LOGGER.warning("Could not persist refreshed token to config entry: %s", err)

                        return self.access_token

                # Sleep APRÈS la libération de la connexion (hors du async with)
                if _rate_limit_wait is not None:
                    await asyncio.sleep(_rate_limit_wait)
                    continue
            except aiohttp.ClientError as err:
                if attempt < 3:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                raise TadoError(f"Network error refreshing token: {err}") from err
        raise TadoAuthError("Could not refresh token after multiple attempts (rate limit / server error)")

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        """Execute an authenticated request against the Tado API with 429 rate limit backoff."""
        token = await self.async_get_valid_token()
        url = f"{TADO_API_BASE}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Referer": DEFAULT_REFERER,
            "User-Agent": DEFAULT_USER_AGENT,
        }

        for attempt in range(5):
            _rate_limit_wait: float | None = None
            try:
                self.requests_count += 1
                async with self.session.request(
                    method, url, json=json_data, params=params, headers=headers
                ) as resp:
                    self._parse_ratelimit_headers(resp.headers)
                    if resp.status == 429:
                        policy = resp.headers.get("RateLimit-Policy", "")
                        rl = resp.headers.get("RateLimit", "")
                        _rate_limit_wait = self._calculate_rate_limit_delay(resp, attempt, default_base=2.5, max_delay=30.0)
                        _LOGGER.warning(
                            "Tado API Rate Limit (429) sur %s (policy=%s, limit=%s). Attente de %.1fs (tentative %d/5)...",
                            endpoint,
                            policy or "N/A",
                            rl or "N/A",
                            _rate_limit_wait,
                            attempt + 1,
                        )
                        # Connexion libérée en sortant du async with AVANT le sleep

                    elif resp.status == 401 and retry_auth:
                        _LOGGER.warning("Received 401 Unauthorized from Tado API, forcing token refresh...")
                        # Sortir du async with AVANT le refresh + retry (évite M-2: récursion dans connexion ouverte)

                    elif resp.status == 204:
                        return {}

                    elif resp.status not in (200, 201):
                        text = await resp.text()
                        if resp.status == 401:
                            raise TadoAuthError(f"API request to {endpoint} failed (401): {text}")
                        raise TadoError(f"API request to {endpoint} failed ({resp.status}): {text}")

                    else:
                        try:
                            data = await resp.json()
                        except (ValueError, aiohttp.ContentTypeError) as parse_err:
                            raise TadoError(f"API request to {endpoint}: invalid JSON response: {parse_err}") from parse_err
                        return data if data is not None else {}

                # Actions APRÈS libération de la connexion (hors du async with)
                if _rate_limit_wait is not None:
                    await asyncio.sleep(_rate_limit_wait)
                    continue

                if resp.status == 401 and retry_auth:
                    # M-1 fix: utiliser async_get_valid_token (protégé par lock) au lieu d'appel direct
                    self.expires_at = 0  # Invalider le token pour forcer un refresh
                    if not self.refresh_token:
                        raise TadoAuthError(
                            f"API request to {endpoint} failed (401): jeton d'accès expiré et aucun jeton de rafraîchissement disponible"
                        )
                    try:
                        token = await self.async_get_valid_token()
                    except TadoAuthError as auth_err:
                        raise TadoAuthError(
                            f"API request to {endpoint} failed (401): renouvellement du jeton impossible ({auth_err})"
                        ) from auth_err
                    headers["Authorization"] = f"Bearer {token}"
                    return await self._request(
                        method, endpoint, json_data=json_data, params=params, retry_auth=False
                    )

            except aiohttp.ClientError as err:
                if attempt < 4:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                raise TadoError(f"Network error requesting {endpoint}: {err}") from err

        raise TadoError(f"API request to {endpoint} failed: Serveurs Tado temporairement saturés (Rate Limit 429). Veuillez patienter.")

    # ── High-level API endpoints ──────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """Fetch user profile and list of homes."""
        return await self._request("GET", "/me")

    async def get_home_info(self, home_id: int) -> dict[str, Any]:
        """Fetch general information for a home."""
        return await self._request("GET", f"/homes/{home_id}")

    async def get_zones(self, home_id: int) -> list[dict[str, Any]]:
        """Fetch all zones (rooms) in the home."""
        return await self._request("GET", f"/homes/{home_id}/zones")

    async def get_zone_states(self, home_id: int) -> dict[str, Any]:
        """Fetch states of all zones in a single call (temperatures, heating power, overlays)."""
        return await self._request("GET", f"/homes/{home_id}/zoneStates")

    async def get_devices(self, home_id: int) -> list[dict[str, Any]]:
        """Fetch all physical devices (Bridge, Radiator Valves, Thermostats)."""
        return await self._request("GET", f"/homes/{home_id}/devices")

    async def get_weather(self, home_id: int) -> dict[str, Any]:
        """Fetch outdoor weather and temperature for the home."""
        return await self._request("GET", f"/homes/{home_id}/weather")

    async def get_home_state(self, home_id: int) -> dict[str, Any]:
        """Fetch global home state (e.g. HOME vs AWAY)."""
        return await self._request("GET", f"/homes/{home_id}/state")

    async def get_active_timetable(self, home_id: int, zone_id: int) -> dict[str, Any]:
        """Fetch active schedule timetable for a zone."""
        return await self._request("GET", f"/homes/{home_id}/zones/{zone_id}/schedule/activeTimetable")

    async def get_timetable_blocks(self, home_id: int, zone_id: int, timetable_id: int) -> list[dict[str, Any]]:
        """Fetch schedule time blocks for a zone timetable."""
        return await self._request("GET", f"/homes/{home_id}/zones/{zone_id}/schedule/timetables/{timetable_id}/blocks")

    async def set_zone_overlay(
        self,
        home_id: int,
        zone_id: int,
        target_temp: float | None = None,
        power: str = "ON",
        termination_type: str = OVERLAY_NEXT_TIME_BLOCK,
        duration_seconds: int | None = None,
        zone_type: str = "HEATING",
        mode: str | None = None,
        fan_speed: str | None = None,
        swing: str | None = None,
    ) -> dict[str, Any]:
        """Set a manual overlay (temperature / power / AC mode) for a zone."""
        setting: dict[str, Any] = {
            "type": zone_type.upper(),
            "power": power.upper(),
        }
        if power.upper() == "ON":
            if target_temp is not None:
                setting["temperature"] = {"celsius": round(float(target_temp), 1)}
            if zone_type.upper() == "AIR_CONDITIONING":
                if mode:
                    setting["mode"] = mode.upper()
                if fan_speed:
                    setting["fanSpeed"] = fan_speed.upper()
                if swing:
                    setting["swing"] = swing.upper()

        termination: dict[str, Any] = {}
        if termination_type == OVERLAY_MANUAL:
            termination["typeSkillBasedApp"] = "MANUAL"
        elif termination_type == OVERLAY_TIMER:
            termination["typeSkillBasedApp"] = "TIMER"
            termination["durationInSeconds"] = int(duration_seconds if duration_seconds is not None else 3600)
        else:
            termination["typeSkillBasedApp"] = "NEXT_TIME_BLOCK"

        payload = {
            "setting": setting,
            "termination": termination,
        }
        _LOGGER.info(
            "Setting overlay for zone %s in home %s: %s (%s)",
            zone_id,
            home_id,
            payload,
            termination_type,
        )
        return await self._request("PUT", f"/homes/{home_id}/zones/{zone_id}/overlay", json_data=payload)

    async def resume_schedule(self, home_id: int, zone_id: int) -> None:
        """Delete manual overlay for a zone to resume automatic schedule."""
        _LOGGER.info("Resuming schedule for zone %s in home %s", zone_id, home_id)
        await self._request("DELETE", f"/homes/{home_id}/zones/{zone_id}/overlay")

    async def resume_all_schedules(self, home_id: int, zone_ids: list[int]) -> None:
        """Resume automatic schedule across all specified zones."""
        tasks = [self.resume_schedule(home_id, zid) for zid in zone_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            _LOGGER.warning("DomoLink-Tado: %d/%d erreurs lors de la reprise des plannings: %s", len(errors), len(tasks), errors[0])

    async def set_all_off(self, home_id: int, zone_ids: list[int]) -> None:
        """Turn off heating across all specified zones."""
        tasks = [
            self.set_zone_overlay(
                home_id=home_id,
                zone_id=zid,
                power="OFF",
                termination_type=OVERLAY_MANUAL,
            )
            for zid in zone_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            _LOGGER.warning("DomoLink-Tado: %d/%d erreurs lors de l'arrêt groupé: %s", len(errors), len(tasks), errors[0])

    async def set_boost(
        self,
        home_id: int,
        zone_ids: list[int],
        temp: float = 25.0,
        duration_seconds: int = 1800,
    ) -> None:
        """Apply a temporary boost to all specified zones."""
        tasks = [
            self.set_zone_overlay(
                home_id=home_id,
                zone_id=zid,
                target_temp=temp,
                power="ON",
                termination_type=OVERLAY_TIMER,
                duration_seconds=duration_seconds,
            )
            for zid in zone_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            _LOGGER.warning("DomoLink-Tado: %d/%d erreurs lors du boost groupé: %s", len(errors), len(tasks), errors[0])

    async def set_child_lock(self, device_serial: str, child_lock: bool) -> dict[str, Any]:
        """Enable or disable physical child lock on a radiator valve."""
        _LOGGER.info("Setting child lock to %s on device %s", child_lock, device_serial)
        return await self._request(
            "PUT",
            f"/devices/{device_serial}/childLock",
            json_data={"childLockEnabled": bool(child_lock)},
        )

    async def set_presence(self, home_id: int, home: bool) -> dict[str, Any]:
        """Lock presence to HOME or AWAY."""
        state = "HOME" if home else "AWAY"
        _LOGGER.info("Locking home presence to %s for home %s", state, home_id)
        return await self._request("PUT", f"/homes/{home_id}/presenceLock", json_data={"homePresence": state})

    async def set_temperature_offset(self, device_serial: str, offset: float) -> dict[str, Any]:
        """Set temperature calibration offset for a physical device in Celsius (-5.0 to 5.0)."""
        clamped = max(-5.0, min(5.0, round(float(offset), 2)))
        _LOGGER.info("Setting temperature offset to %s°C on device %s", clamped, device_serial)
        return await self._request(
            "PUT",
            f"/devices/{device_serial}/temperatureOffset",
            json_data={"celsius": clamped},
        )

    async def get_temperature_offset(self, device_serial: str) -> dict[str, Any]:
        """Get current temperature calibration offset for a device."""
        return await self._request("GET", f"/devices/{device_serial}/temperatureOffset")
