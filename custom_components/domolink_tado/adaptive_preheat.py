"""Adaptive Preheat and Thermal Drop Analysis for DomoLink-Tado."""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
import logging
import math
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Jours de la semaine utilisés par Tado API
DAY_MAP = {
    0: "MONDAY",
    1: "TUESDAY",
    2: "WEDNESDAY",
    3: "THURSDAY",
    4: "FRIDAY",
    5: "SATURDAY",
    6: "SUNDAY",
}


def estimate_preheat_duration(
    target_temp: float | None,
    current_temp: float | None,
    heating_rate: float,
    max_duration_minutes: int = 120,
) -> int:
    """Calculate required preheat duration in minutes.

    Formula:
        delta_T = target_temp - current_temp
        duration_minutes = (delta_T / heating_rate) * 60
    """
    if target_temp is None or current_temp is None:
        return 0

    try:
        t_target = float(target_temp)
        t_current = float(current_temp)
        rate = float(heating_rate)
    except (ValueError, TypeError):
        return 0

    if t_target <= t_current:
        return 0

    # Ensure rate is strictly positive and realistic (min 0.2 °C/h)
    effective_rate = max(rate, 0.2)
    delta_t = t_target - t_current

    duration = int(math.ceil((delta_t / effective_rate) * 60.0))
    return max(0, min(duration, max_duration_minutes))


def update_heating_rate(
    current_rate: float,
    temp_start: float,
    temp_end: float,
    duration_hours: float,
) -> float:
    """Update heating rate (°C/hour) using Exponential Moving Average (EMA).

    Formula:
        measured_rate = (temp_end - temp_start) / duration_hours
        new_rate = 0.8 * current_rate + 0.2 * measured_rate
    """
    if duration_hours < 0.2:  # Moins de 12 minutes : durée trop courte pour une mesure fiable
        return round(current_rate, 2)

    delta_temp = temp_end - temp_start
    if delta_temp <= 0.0:  # La température n'a pas monté (ex: fenêtre ouverte ou chaudière éteinte)
        return round(current_rate, 2)

    measured_rate = delta_temp / duration_hours

    # Borner les valeurs mesurées pour éviter les anomalies aberrantes
    clamped_measured = max(0.5, min(measured_rate, 6.0))

    new_rate = (0.8 * current_rate) + (0.2 * clamped_measured)
    return round(new_rate, 2)


def detect_rapid_temperature_drop(
    temp_history: list[tuple[float, float]],
    threshold_drop: float = 0.5,
    max_seconds: float = 300.0,
) -> bool:
    """Detect rapid temperature drop indicative of an open window.

    temp_history is a list of (timestamp, temperature) tuples sorted by timestamp.
    Returns True if temperature dropped by at least threshold_drop within max_seconds.
    """
    if not temp_history or len(temp_history) < 2:
        return False

    latest_time, latest_temp = temp_history[-1]

    # Chercher la température maximale observée dans la fenêtre des max_seconds
    for ts, temp in reversed(temp_history[:-1]):
        time_diff = latest_time - ts
        if time_diff > max_seconds:
            break
        drop = temp - latest_temp
        if drop >= threshold_drop:
            return True

    return False


def find_next_scheduled_change(
    blocks: list[dict[str, Any]],
    current_dt: datetime,
) -> dict[str, Any] | None:
    """Find the next upcoming schedule change in Tado timetable blocks.

    Returns a dict with:
        - "start_dt": datetime of the transition
        - "target_temp": float target temperature
        - "power": "ON" | "OFF"
    """
    if not blocks:
        return None

    current_weekday = current_dt.weekday()
    current_day_name = DAY_MAP.get(current_weekday, "MONDAY")

    # Group blocks by day
    # Note: Tado API blocks can have dayType: "MONDAY", "TUESDAY", ... or "ALL", "ONE_DAY"
    # Filter blocks for today and tomorrow
    candidates: list[dict[str, Any]] = []

    for day_offset in range(2):  # Today and tomorrow
        target_date = (current_dt + timedelta(days=day_offset)).date()
        target_weekday = (current_weekday + day_offset) % 7
        target_day_name = DAY_MAP.get(target_weekday, "MONDAY")

        for b in blocks:
            day_type = str(b.get("dayType", "")).upper()
            if day_type not in (target_day_name, "ALL", "MONDAY_TO_FRIDAY", "MONDAY_TO_SUNDAY") and day_type:
                # Handle MONDAY_TO_FRIDAY
                if day_type == "MONDAY_TO_FRIDAY" and target_weekday >= 5:
                    continue
                if day_type == "SATURDAY_TO_SUNDAY" and target_weekday < 5:
                    continue
                if day_type != target_day_name and day_type not in ("ALL", "ONE_DAY", "EVERY_DAY"):
                    continue

            start_str = b.get("start")
            if not start_str or ":" not in start_str:
                continue

            try:
                parts = start_str.split(":")
                hour = int(parts[0])
                minute = int(parts[1])
                block_dt = datetime.combine(target_date, dtime(hour, minute))
            except (ValueError, IndexError):
                continue

            if block_dt > current_dt:
                setting = b.get("setting") or {}
                power = setting.get("power", "OFF")
                temp_obj = setting.get("temperature") or {}
                temp = temp_obj.get("celsius") if power == "ON" else None
                candidates.append({
                    "start_dt": block_dt,
                    "target_temp": temp,
                    "power": power,
                    "block": b,
                })

    if not candidates:
        return None

    # Return earliest upcoming change
    candidates.sort(key=lambda c: c["start_dt"])
    return candidates[0]
