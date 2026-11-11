"""Asynchronous Tado API client with bulletproof OAuth2 Device Flow & token persistence."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import json
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
    TADO_GRAPHQL_FALLBACK_URL,
    TADO_GRAPHQL_URL,
    TADO_HOPS_FALLBACK_URL,
    TADO_HOPS_API_URL,
    TADO_IVAR_FALLBACK_URL,
    TADO_IVAR_GRAPHQL_URL,
    TADO_MINDER_FALLBACK_URL,
    TADO_MINDER_API_URL,
    TADO_SCOPE,
    TADO_TOKEN_URL,
    VERSION,
)
from .quota_budget import QuotaBudget, QuotaSnapshot, Tier

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


class TadoRateLimitError(TadoError):
    """Exception raised when Tado API rate limit is exceeded."""

    def __init__(self, message: str, reset_seconds: float | None = None) -> None:
        super().__init__(message)
        self.reset_seconds = reset_seconds


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
        self.rate_limited_until: float = 0.0
        self.requests_count: int = 0
        self.budget: QuotaBudget = QuotaBudget()

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

    @staticmethod
    def extract_home_id_from_token(token: str) -> tuple[int | None, str | None]:
        """Extract home_id and home_name directly from JWT token payload without making API calls."""
        if not token or not isinstance(token, str):
            return None, None
        parts = token.split(".")
        if len(parts) < 2:
            return None, None
        payload_b64 = parts[1]
        rem = len(payload_b64) % 4
        if rem > 0:
            payload_b64 += "=" * (4 - rem)
        try:
            decoded_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(decoded_bytes.decode("utf-8"))
        except Exception:
            return None, None

        if not isinstance(payload, dict):
            return None, None

        home_id: int | None = None
        home_name: str | None = None

        for claim in ("tado_homes", "homes"):
            homes = payload.get(claim)
            if isinstance(homes, list) and len(homes) > 0:
                first = homes[0]
                if isinstance(first, dict):
                    raw_id = first.get("id") or first.get("homeId")
                    if raw_id:
                        try:
                            home_id = int(raw_id)
                            home_name = first.get("name")
                            break
                        except (ValueError, TypeError):
                            pass
                elif isinstance(first, (int, str)):
                    try:
                        home_id = int(first)
                        break
                    except (ValueError, TypeError):
                        pass

        if home_id is None:
            for claim in ("homeId", "home_id", "currentHomeId", "current_home_id"):
                raw_id = payload.get(claim)
                if raw_id is not None:
                    try:
                        home_id = int(raw_id)
                        break
                    except (ValueError, TypeError):
                        pass

        return home_id, home_name

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
        if not headers or not hasattr(headers, "get"):
            return

        def _get_str(k: str) -> str:
            v = headers.get(k)
            return str(v) if isinstance(v, (str, int, float)) else ""

        policy = _get_str("RateLimit-Policy") or _get_str("ratelimit-policy")
        rl = _get_str("RateLimit") or _get_str("ratelimit")
        reset_hdr = _get_str("RateLimit-Reset") or _get_str("ratelimit-reset")

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
            x_limit = _get_str("X-RateLimit-Limit") or _get_str("x-ratelimit-limit")
            if x_limit:
                try:
                    self.rate_limit_limit = int(x_limit)
                except (ValueError, TypeError):
                    pass

        if self.rate_limit_remaining is None:
            x_rem = _get_str("X-RateLimit-Remaining") or _get_str("x-ratelimit-remaining")
            if x_rem:
                try:
                    self.rate_limit_remaining = int(x_rem)
                except (ValueError, TypeError):
                    pass

        if self.rate_limit_reset_seconds is None:
            x_reset = _get_str("X-RateLimit-Reset") or _get_str("x-ratelimit-reset")
            if x_reset:
                try:
                    self.rate_limit_reset_seconds = int(x_reset)
                except (ValueError, TypeError):
                    pass

        if self.rate_limit_reset_seconds is None:
            retry_after = _get_str("Retry-After") or _get_str("retry-after")
            if retry_after:
                try:
                    ra_val = float(retry_after)
                    if ra_val > 1000000000:
                        self.rate_limit_reset_seconds = int(max(1, ra_val - time.time()))
                    else:
                        self.rate_limit_reset_seconds = int(ra_val)
                except (ValueError, TypeError):
                    pass

        if self.rate_limit_remaining is not None or self.rate_limit_limit is not None:
            now_ts = time.time()
            self.rate_limit_last_update = now_ts
            if self.rate_limit_remaining == 0:
                cooldown = float(self.rate_limit_reset_seconds) if self.rate_limit_reset_seconds and self.rate_limit_reset_seconds > 0 else 3600.0
                self.rate_limited_until = max(self.rate_limited_until, now_ts + cooldown)
            self.budget.update(
                QuotaSnapshot(
                    limit=self.rate_limit_limit,
                    remaining=self.rate_limit_remaining,
                    reset_in=float(self.rate_limit_reset_seconds) if self.rate_limit_reset_seconds is not None else None,
                    observed_at=now_ts,
                )
            )

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

        now = time.time()
        is_blocked = now < self.rate_limited_until
        remaining_cooldown = max(0.0, self.rate_limited_until - now) if is_blocked else 0.0

        return {
            "limit": limit,
            "remaining": rem,
            "used": used,
            "requests_count": self.requests_count,
            "reset_seconds": int(remaining_cooldown) if is_blocked else self.rate_limit_reset_seconds,
            "circuit_breaker_active": is_blocked,
            "cooldown_remaining_seconds": round(remaining_cooldown, 1),
            "last_update": self.rate_limit_last_update,
            "tier": self.budget.tier,
            "seconds_to_reset": round(self.budget.seconds_to_reset(now), 1),
        }

    async def async_refresh_token(self) -> str:
        """Refresh the access token using the stored refresh token."""
        now = time.time()
        if now < self.rate_limited_until:
            remaining_cooldown = self.rate_limited_until - now
            raise TadoRateLimitError(
                f"Rafraîchissement du jeton bloqué localement : quota Tado épuisé (réessai dans {remaining_cooldown:.0f}s)",
                reset_seconds=remaining_cooldown,
            )

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
                        self._parse_ratelimit_headers(resp.headers)
                        reset_sec = self.rate_limit_reset_seconds
                        rem = self.rate_limit_remaining
                        if rem == 0 or (reset_sec is not None and reset_sec > 60):
                            cooldown = float(reset_sec) if reset_sec and reset_sec > 0 else 3600.0
                            self.rate_limited_until = time.time() + cooldown
                            _LOGGER.error(
                                "Quota Tado API épuisé lors du rafraîchissement (remaining=%s, reset_in=%.0fs). Disjoncteur activé.",
                                rem,
                                cooldown,
                            )
                            raise TadoRateLimitError(
                                f"Quota Tado API épuisé lors du rafraîchissement ({rem} requêtes restantes). Prochaine réinitialisation dans {cooldown:.0f}s.",
                                reset_seconds=cooldown,
                            )

                        _rate_limit_wait = self._calculate_rate_limit_delay(resp, attempt, default_base=3.0, max_delay=10.0)
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
        now = time.time()
        if now < self.rate_limited_until:
            remaining_cooldown = self.rate_limited_until - now
            raise TadoRateLimitError(
                f"Appel API {endpoint} bloqué localement : quota Tado épuisé (réessai dans {remaining_cooldown:.0f}s)",
                reset_seconds=remaining_cooldown,
            )

        token = await self.async_get_valid_token()
        url = f"{TADO_API_BASE}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Referer": DEFAULT_REFERER,
            "User-Agent": DEFAULT_USER_AGENT,
        }

        for attempt in range(3):
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
                        reset_sec = self.rate_limit_reset_seconds
                        rem = self.rate_limit_remaining

                        if rem == 0 or (reset_sec is not None and reset_sec > 60):
                            cooldown = float(reset_sec) if reset_sec and reset_sec > 0 else 3600.0
                            self.rate_limited_until = time.time() + cooldown
                            _LOGGER.error(
                                "Tado API Quota épuisé sur %s (policy=%s, limit=%s, remaining=%s, reset_in=%.0fs). Disjoncteur activé pour %.0fs.",
                                endpoint,
                                policy or "N/A",
                                rl or "N/A",
                                rem,
                                cooldown,
                                cooldown,
                            )
                            raise TadoRateLimitError(
                                f"Quota API Tado épuisé sur {endpoint} ({rem} requêtes restantes). Disjoncteur actif pour {cooldown:.0f}s.",
                                reset_seconds=cooldown,
                            )

                        _rate_limit_wait = self._calculate_rate_limit_delay(resp, attempt, default_base=2.0, max_delay=10.0)
                        _LOGGER.warning(
                            "Tado API Rate Limit (429) sur %s (policy=%s, limit=%s). Attente de %.1fs (tentative %d/3)...",
                            endpoint,
                            policy or "N/A",
                            rl or "N/A",
                            _rate_limit_wait,
                            attempt + 1,
                        )
                        if attempt >= 2:
                            raise TadoRateLimitError(
                                f"API request to {endpoint} rate limited (429) après 3 tentatives.",
                                reset_seconds=_rate_limit_wait,
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
                if attempt < 2:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                raise TadoError(f"Network error requesting {endpoint}: {err}") from err

        raise TadoRateLimitError(
            f"API request to {endpoint} failed: Serveurs Tado temporairement saturés (Rate Limit 429).",
            reset_seconds=self.rate_limit_reset_seconds or 60.0,
        )

    async def _microservice_request(
        self,
        method: str,
        primary_url: str,
        fallback_url: str | None = None,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float = 15.0,
        tolerant_statuses: tuple[int, ...] = (204, 404),
    ) -> Any:
        """Execute an authenticated request against a Tado microservice with automatic fallback."""
        now = time.time()
        if now < self.rate_limited_until:
            remaining_cooldown = self.rate_limited_until - now
            raise TadoRateLimitError(
                f"Appel microservice {primary_url} bloqué localement : quota Tado épuisé (réessai dans {remaining_cooldown:.0f}s)",
                reset_seconds=remaining_cooldown,
            )

        token = await self.async_get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Amzn-Trace-Id": "tado=webapp-3922",
            "Referer": DEFAULT_REFERER,
            "User-Agent": DEFAULT_USER_AGENT,
        }

        urls_to_try = [primary_url]
        if fallback_url and fallback_url != primary_url:
            urls_to_try.append(fallback_url)

        last_error: Exception | None = None
        for target_url in urls_to_try:
            try:
                self.requests_count += 1
                client_timeout = (
                    aiohttp.ClientTimeout(total=timeout)
                    if hasattr(aiohttp, "ClientTimeout")
                    else timeout
                )
                async with self.session.request(
                    method, target_url, json=json_data, params=params, headers=headers, timeout=client_timeout
                ) as resp:
                    self._parse_ratelimit_headers(resp.headers)
                    if resp.status == 204:
                        return {}
                    if resp.status == 404:
                        if target_url != urls_to_try[-1]:
                            _LOGGER.debug("Microservice 404 on %s, trying fallback %s", target_url, urls_to_try[-1])
                            continue
                        if 404 in tolerant_statuses:
                            return {}
                    if resp.status == 429:
                        reset_sec = self.rate_limit_reset_seconds
                        rem = self.rate_limit_remaining
                        cooldown = float(reset_sec) if reset_sec and reset_sec > 0 else 3600.0
                        self.rate_limited_until = time.time() + cooldown
                        _LOGGER.error(
                            "Tado microservice Quota épuisé sur %s (remaining=%s, reset_in=%.0fs). Disjoncteur activé pour %.0fs.",
                            target_url,
                            rem,
                            cooldown,
                            cooldown,
                        )
                        raise TadoRateLimitError(
                            f"Microservice request to {target_url} rate limited (429)",
                            reset_seconds=cooldown,
                        )
                    if resp.status in (401, 403):
                        if target_url != urls_to_try[-1]:
                            _LOGGER.debug("Microservice auth/permission issue on %s (status %s), trying fallback", target_url, resp.status)
                            continue
                        text = await resp.text()
                        raise TadoAuthError(f"Microservice request to {target_url} unauthorized ({resp.status}): {text}")
                    if resp.status not in (200, 201):
                        text = await resp.text()
                        if target_url != urls_to_try[-1]:
                            _LOGGER.debug("Microservice error on %s (status %s), trying fallback", target_url, resp.status)
                            continue
                        raise TadoError(f"Microservice request to {target_url} failed ({resp.status}): {text}")

                    try:
                        data = await resp.json()
                        return data if data is not None else {}
                    except (ValueError, aiohttp.ContentTypeError):
                        return {}
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err
                _LOGGER.debug("Network error contacting microservice %s: %s", target_url, err)
                if target_url != urls_to_try[-1]:
                    continue

        if last_error:
            raise TadoError(f"Impossible de joindre le microservice Tado ({primary_url}): {last_error}") from last_error
        return {}

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

    # ── Microservices Tado v10.9 (GraphQL, Ivar, Minder, Hops) ──

    async def async_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        endpoint: str = TADO_GRAPHQL_URL,
        fallback_endpoint: str | None = TADO_GRAPHQL_FALLBACK_URL,
    ) -> dict[str, Any]:
        """Execute a GraphQL query or mutation against Tado GraphQL microservices."""
        payload: dict[str, Any] = {
            "query": query,
            "variables": variables or {},
        }
        if operation_name:
            payload["operationName"] = operation_name

        res = await self._microservice_request(
            "POST",
            endpoint,
            fallback_url=fallback_endpoint,
            json_data=payload,
        )
        if isinstance(res, dict) and "errors" in res and res["errors"]:
            _LOGGER.warning("Tado GraphQL query had errors: %s", res["errors"])
        return res.get("data") or {} if isinstance(res, dict) else {}

    async def get_graphql_devices(self, home_id: int) -> list[dict[str, Any]]:
        """Fetch low-level device attributes and hardware capabilities via GraphQL."""
        query = """
        query Devices($homeId: ID!) {
          home(id: $homeId) {
            devices {
              all {
                id
                serialNumber
                ... on CanDazzle { dazzleEnabled }
                ... on CanIdentify { supportsIdentify }
                ... on CanConfigureControlMode { controlMode }
                ... on CanConfigureRelayMode { relayMode }
                ... on HasThermInterface { thermInterfaceType }
                ... on ReportsBadSignal { hasBadSignal }
              }
            }
          }
        }
        """
        data = await self.async_graphql(query, variables={"homeId": str(home_id)})
        return (data.get("home", {}).get("devices", {}).get("all") or []) if isinstance(data, dict) else []

    async def identify_device(self, device_id: str) -> dict[str, Any]:
        """Blink the LED screen of a physical radiator valve or thermostat to locate it."""
        query = """
        mutation IdentifyDevice($deviceId: ID!) {
          identifyDevice(deviceId: $deviceId) {
            success
            failureReason
          }
        }
        """
        data = await self.async_graphql(query, variables={"deviceId": str(device_id)})
        return (data.get("identifyDevice") or {}) if isinstance(data, dict) else {}

    async def reboot_device(self, device_id: str) -> dict[str, Any]:
        """Remotely reboot a physical Tado device (bridge, valve, thermostat)."""
        query = """
        mutation RebootDevice($deviceId: ID!) {
          rebootDevice(deviceId: $deviceId) {
            success
            failureReason
          }
        }
        """
        data = await self.async_graphql(query, variables={"deviceId": str(device_id)})
        return (data.get("rebootDevice") or {}) if isinstance(data, dict) else {}

    async def set_device_dazzle(self, device_id: str, enabled: bool) -> dict[str, Any]:
        """Toggle inverted / bright LED display mode (Dazzle) on a device."""
        query = """
        mutation SetDeviceDazzleEnabled($deviceId: ID!, $enabled: Boolean!) {
          setDeviceDazzleEnabled(deviceId: $deviceId, enabled: $enabled) {
            success
            failureReason
          }
        }
        """
        data = await self.async_graphql(query, variables={"deviceId": str(device_id), "enabled": bool(enabled)})
        return (data.get("setDeviceDazzleEnabled") or {}) if isinstance(data, dict) else {}

    async def set_relay_mode(self, device_id: str, relay_mode: str) -> dict[str, Any]:
        """Configure relay operating mode on boiler interface."""
        query = """
        mutation SetRelayMode($deviceId: ID!, $relayMode: RelayMode!) {
          setRelayMode(deviceId: $deviceId, relayMode: $relayMode) {
            success
            failureReason
          }
        }
        """
        data = await self.async_graphql(query, variables={"deviceId": str(device_id), "relayMode": str(relay_mode)})
        return (data.get("setRelayMode") or {}) if isinstance(data, dict) else {}

    async def get_ivar_boiler_details(self, system_id: int) -> dict[str, Any]:
        """Lookup boiler manufacturer and model specifications via ivar.tado.com."""
        query = """
        query system($id: Int!) {
          system(id: $id) {
            id
            modelName
            shortModelName: modelName(type: SHORT)
            manufacturers {
              name
            }
          }
        }
        """
        data = await self.async_graphql(
            query,
            variables={"id": int(system_id)},
            endpoint=TADO_IVAR_GRAPHQL_URL,
            fallback_endpoint=TADO_IVAR_FALLBACK_URL,
        )
        return (data.get("system") or {}) if isinstance(data, dict) else {}

    async def get_heating_system(self, home_id: int) -> dict[str, Any]:
        """Fetch connected heating system details (boiler id, underfloor heating)."""
        return await self._request("GET", f"/homes/{home_id}/heatingSystem")

    async def get_boiler_incidents(self, home_id: int) -> list[dict[str, Any]]:
        """Retrieve active boiler incidents (pressure drop, burner error) from minder.tado.com."""
        primary = f"{TADO_MINDER_API_URL}/homes/{home_id}/incidents"
        fallback = f"{TADO_MINDER_FALLBACK_URL}/homes/{home_id}/incidents"
        res = await self._microservice_request("GET", primary, fallback_url=fallback)
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            return res.get("incidents", []) or []
        return []

    async def get_burner_running_times(self, home_id: int, from_date: str, to_date: str) -> dict[str, Any]:
        """Retrieve daily/zone burner active running times from minder.tado.com."""
        params = {
            "from": from_date,
            "to": to_date,
            "aggregate": "day",
            "summary_only": "false",
        }
        primary = f"{TADO_MINDER_API_URL}/homes/{home_id}/runningTimes"
        fallback = f"{TADO_MINDER_FALLBACK_URL}/homes/{home_id}/runningTimes"
        res = await self._microservice_request("GET", primary, fallback_url=fallback, params=params)
        return res if isinstance(res, dict) else {}

    async def get_energy_insights(self, home_id: int, year_month: str) -> dict[str, Any]:
        """Fetch unified energy savings, heat pump COP and notifications in one GraphQL call."""
        query = """
        query EnergyInsights($homeId: ID!, $month: YearMonth!) {
          home(id: $homeId) {
            energySavings(month: $month) {
              totalSavings {
                percentage
              }
              openWindowDetectionTimes
              sunshineDuration {
                duration
              }
              awayDuration {
                duration
              }
              manualControlSaving {
                percentage
              }
              hasAutoAssist
            }
            heatPump {
              consumption {
                cop {
                  heating
                  domesticHotWater
                }
              }
            }
            notifications(types: [MOLD_INDEX, OPEN_WINDOW_DETECTION_SAVINGS_ADVICE]) {
              id
              type
              ... on MoldIndexNotification {
                roomIds
                moldIndexNotificationType
              }
            }
          }
        }
        """
        data = await self.async_graphql(query, variables={"homeId": str(home_id), "month": str(year_month)})
        return (data.get("home") or {}) if isinstance(data, dict) else {}

    async def get_hops_diagnostics(self, home_id: int) -> list[dict[str, Any]]:
        """Retrieve actionable device alerts from hops.tado.com."""
        primary = f"{TADO_HOPS_API_URL}/homes/{home_id}/actionableDevices"
        fallback = f"{TADO_HOPS_FALLBACK_URL}/homes/{home_id}/actionableDevices"
        res = await self._microservice_request("GET", primary, fallback_url=fallback)
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            return res.get("actionableDevices") or res.get("devices") or []
        return []

    async def get_matter_provisioning(self, home_id: int, device_id: str) -> dict[str, Any]:
        """Retrieve secret Matter pairing codes (passcode & discriminator) for a Tado X device."""
        query = """
        query MatterProvisioningData($homeId: ID!, $deviceId: ID!) {
          home(id: $homeId) {
            device(id: $deviceId) {
              ... on MatterCommissionable {
                matterProvisioningData {
                  passcode
                  discriminator
                }
              }
            }
          }
        }
        """
        data = await self.async_graphql(query, variables={"homeId": str(home_id), "deviceId": str(device_id)})
        return (data.get("home", {}).get("device", {}).get("matterProvisioningData") or {}) if isinstance(data, dict) else {}
