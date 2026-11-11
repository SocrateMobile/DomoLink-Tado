"""Centralized API Quota & Rate-Limit Budgeting for DomoLink-Tado."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
import logging
import time
from typing import Literal

_LOGGER = logging.getLogger(__name__)

Tier = Literal["FREE", "STANDARD", "ASSIST", "UNKNOWN"]
Resource = Literal["discovery", "weather", "home_state", "schedule", "day_report", "graphql_devices", "minder", "energy_insights"]
SpendKind = Literal["command", "poll", "background"]


@dataclass(frozen=True)
class QuotaSnapshot:
    """Immutable snapshot of the current Tado API rate limit state."""

    limit: int | None
    remaining: int | None
    reset_in: float | None
    observed_at: float


class QuotaBudget:
    """Manages the daily API budget, dynamic poll intervals and cache TTLs."""

    COMMAND_RESERVE: float = 0.25  # 25% of remaining quota reserved strictly for commands
    MIN_INTERVAL: int = 60         # 1 minute minimum polling
    MAX_INTERVAL: int = 3600       # 1 hour maximum polling

    def __init__(self) -> None:
        self.snapshot: QuotaSnapshot | None = None
        self._manual_tier_override: Tier | None = None

    def update(self, snap: QuotaSnapshot) -> None:
        """Update budget from an observed API response snapshot."""
        self.snapshot = snap
        _LOGGER.debug(
            "DomoLink-Tado: Quota snapshot mis à jour: tier=%s limit=%s rem=%s reset_in=%.0fs",
            self.tier,
            snap.limit,
            snap.remaining,
            snap.reset_in if snap.reset_in is not None else -1,
        )

    @property
    def tier(self) -> Tier:
        """Detect Tado quota tier (FREE ~100/day, STANDARD ~1000/day, ASSIST ~20000/day, or UNKNOWN)."""
        if self._manual_tier_override:
            return self._manual_tier_override
        if not self.snapshot or self.snapshot.limit is None:
            return "UNKNOWN"
        if self.snapshot.limit <= 250:
            return "FREE"
        if self.snapshot.limit <= 2000:
            return "STANDARD"
        if self.snapshot.limit >= 2000:
            return "ASSIST"
        return "UNKNOWN"

    def set_manual_tier(self, tier: Tier | None) -> None:
        """Allow manual override of quota tier via config options."""
        self._manual_tier_override = tier

    def seconds_to_reset(self, now: float | None = None) -> float:
        """Return estimated seconds until daily quota reset (noon 12:00 CET/CEST)."""
        curr = now if now is not None else time.time()
        if self.snapshot and self.snapshot.reset_in is not None and self.snapshot.reset_in > 0:
            # Adjust reset_in by elapsed time since snapshot
            elapsed = max(0.0, curr - self.snapshot.observed_at)
            adjusted = max(1.0, self.snapshot.reset_in - elapsed)
            return adjusted

        # Fallback: estimate time until next 12:00 local time
        now_dt = datetime.fromtimestamp(curr)
        reset_today = datetime.combine(now_dt.date(), dt_time(12, 0, 0))
        if now_dt >= reset_today:
            reset_next = reset_today + timedelta(days=1)
        else:
            reset_next = reset_today
        return max(60.0, (reset_next - now_dt).total_seconds())

    def poll_interval(
        self,
        now: float | None = None,
        *,
        heating_active: bool = False,
        quiet_hours: bool = False,
    ) -> int:
        """Compute the optimal next polling interval in seconds based on available quota."""
        curr = now if now is not None else time.time()
        tier = self.tier

        # Tier ASSIST (20,000 req/day): fast polling
        if tier == "ASSIST":
            if heating_active:
                return 120  # 2 minutes during active heating
            if quiet_hours:
                return 600  # 10 minutes at night
            return 300      # 5 minutes normal rest

        # Tier FREE (~100 req/day) & STANDARD (~1000 req/day): strictly smooth remaining calls until reset
        if tier in ("FREE", "STANDARD") and self.snapshot and self.snapshot.remaining is not None:
            rem = max(0, self.snapshot.remaining)
            reserve_pct = 0.25 if tier == "FREE" else 0.15
            min_reserve = 5 if tier == "FREE" else 20
            min_floor = 180 if tier == "FREE" else 90

            if rem <= min_reserve:
                return 3600  # Safety fallback: 1 hour if almost exhausted

            poll_budget = max(1.0, rem * (1.0 - reserve_pct))
            reset_secs = self.seconds_to_reset(curr)
            calculated = int(reset_secs / poll_budget)

            if quiet_hours and not heating_active:
                calculated = int(calculated * 1.5)

            return max(min_floor, min(self.MAX_INTERVAL, calculated))

        # Tier UNKNOWN (fallback to adaptive logic preserving compatibility)
        if self.snapshot and self.snapshot.remaining is not None:
            rem = self.snapshot.remaining
            if rem < 50:
                return 900   # 15 min
            if rem < 150:
                return 600   # 10 min
            if rem < 300:
                return 300   # 5 min

        return 120 if heating_active else 300

    def ttl(
        self,
        resource: Resource,
        *,
        has_ha_weather: bool = False,
        has_ha_geofencing: bool = False,
    ) -> int | None:
        """Return resource cache TTL in seconds. None means do not fetch periodically."""
        tier = self.tier

        if tier == "FREE":
            if resource == "discovery":
                return 86400  # 24 hours
            if resource == "weather":
                # If HA already has outdoor weather entity configured, don't waste Tado quota
                return None if has_ha_weather else 21600  # 6 hours
            if resource == "home_state":
                # If HA person geofencing is enabled, skip polling home state
                return None if has_ha_geofencing else 7200  # 2 hours
            if resource in ("schedule", "day_report"):
                return None  # Never background poll schedules in Free tier
            if resource == "graphql_devices":
                return 21600  # 6 hours
            if resource == "minder":
                return 21600  # 6 hours
            if resource == "energy_insights":
                return 43200  # 12 hours

        elif tier == "STANDARD":
            if resource == "discovery":
                return 43200  # 12 hours
            if resource == "weather":
                return None if has_ha_weather else 7200  # 2 hours
            if resource == "home_state":
                return None if has_ha_geofencing else 3600  # 1 hour
            if resource == "schedule":
                return 21600  # 6 hours
            if resource == "day_report":
                return 86400
            if resource in ("graphql_devices", "minder"):
                return 21600  # 6 hours
            if resource == "energy_insights":
                return 43200  # 12 hours

        elif tier == "ASSIST":
            if resource == "discovery":
                return 14400  # 4 hours
            if resource == "weather":
                return 900 if not has_ha_weather else 3600
            if resource == "home_state":
                return 300 if not has_ha_geofencing else 1800
            if resource == "schedule":
                return 21600  # 6 hours
            if resource == "day_report":
                return 86400
            if resource == "graphql_devices":
                return 1800  # 30 min
            if resource == "minder":
                return 1800  # 30 min
            if resource == "energy_insights":
                return 3600  # 1 hour

        # UNKNOWN fallback
        if resource == "discovery":
            return 14400
        if resource == "weather":
            return 1800 if not has_ha_weather else 7200
        if resource == "home_state":
            return 900 if not has_ha_geofencing else 3600
        if resource == "schedule":
            return 21600
        if resource in ("graphql_devices", "minder"):
            return 7200
        if resource == "energy_insights":
            return 14400
        return 86400

    def can_spend(self, kind: SpendKind, cost: int = 1) -> bool:
        """Check whether the requested operation can proceed within quota limits."""
        if not self.snapshot or self.snapshot.remaining is None:
            return True

        rem = self.snapshot.remaining
        if rem <= 0:
            return False

        if kind == "command":
            # Commands have absolute priority as long as at least 1 call is left
            return rem >= cost

        if kind == "poll":
            if self.tier == "FREE":
                # Keep the command reserve intact
                reserved = max(5, int((self.snapshot.limit or 100) * self.COMMAND_RESERVE))
                return (rem - cost) >= reserved
            if self.tier == "STANDARD":
                reserved = max(15, int((self.snapshot.limit or 1000) * 0.15))
                return (rem - cost) >= reserved
            return rem >= cost

        if kind == "background":
            # Background tasks (schedule pre-fetch, automatic offset adjustments)
            # require sufficient quota buffer
            if self.tier == "FREE":
                return rem > 30
            if self.tier == "STANDARD":
                return rem > 150
            if self.tier == "ASSIST":
                return rem > 100
            return rem > 50

        return True
