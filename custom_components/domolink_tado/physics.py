"""Building physics and atmospheric calculations for DomoLink-Tado."""
from __future__ import annotations

import math
from typing import Literal

MoldRiskLevel = Literal["normal", "low", "medium", "high"]


def calculate_dew_point(
    temperature: float | None,
    humidity: float | None,
) -> float | None:
    """Calculate dew point in degrees Celsius using the Magnus-Tetens approximation.

    Formula:
        gamma(T, RH) = (17.67 * T) / (243.5 + T) + ln(RH / 100)
        T_dew = (243.5 * gamma) / (17.67 - gamma)
    """
    if temperature is None or humidity is None:
        return None

    try:
        temp_f = float(temperature)
        rh_f = float(humidity)
    except (ValueError, TypeError):
        return None

    # RH must be strictly positive and within realistic percentage bounds
    if rh_f <= 0.0 or rh_f > 100.0:
        return None

    # Avoid division by zero on denominator 243.5 + T
    if temp_f <= -243.5:
        return None

    a = 17.67
    b = 243.5

    try:
        alpha = (a * temp_f) / (b + temp_f) + math.log(rh_f / 100.0)
        denominator = a - alpha
        if denominator == 0.0:
            return None
        t_dew = (b * alpha) / denominator
        return round(t_dew, 1)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def calculate_absolute_humidity(
    temperature: float | None,
    humidity: float | None,
) -> float | None:
    """Calculate absolute humidity in grams of water per cubic meter (g/m³).

    Formula:
        P_sat = 6.112 * exp((17.67 * T) / (243.5 + T)) (in hPa)
        P_v = (RH / 100) * P_sat
        AH = (216.7 * P_v) / (T + 273.15) (in g/m³)
    """
    if temperature is None or humidity is None:
        return None

    try:
        temp_f = float(temperature)
        rh_f = float(humidity)
    except (ValueError, TypeError):
        return None

    if rh_f < 0.0 or rh_f > 100.0:
        return None

    if temp_f <= -273.15 or temp_f <= -243.5:
        return None

    a = 17.67
    b = 243.5

    try:
        p_sat = 6.112 * math.exp((a * temp_f) / (b + temp_f))
        p_v = (rh_f / 100.0) * p_sat
        ah = (216.7 * p_v) / (temp_f + 273.15)
        return round(ah, 2)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def calculate_mold_risk_level(
    temperature: float | None,
    humidity: float | None,
) -> MoldRiskLevel | None:
    """Assess mold risk level based on temperature, humidity, and dew point spread.

    Spread Delta T = T_inside - T_dew:
      - > 7.0 °C: normal
      - > 5.0 °C: low
      - > 3.0 °C: medium
      - <= 3.0 °C: high

    If humidity >= 70.0%, risk is escalated to at least 'medium'.
    If humidity >= 80.0%, risk is escalated to 'high'.
    """
    dew_point = calculate_dew_point(temperature, humidity)
    if dew_point is None or temperature is None or humidity is None:
        return None

    temp_f = float(temperature)
    rh_f = float(humidity)
    spread = temp_f - dew_point

    if spread <= 3.0 or rh_f >= 80.0:
        return "high"
    if spread <= 5.0 or rh_f >= 70.0:
        return "medium"
    if spread <= 7.0 or rh_f >= 60.0:
        return "low"
    return "normal"


def calculate_mold_risk_problem(
    temperature: float | None,
    humidity: float | None,
) -> bool | None:
    """Return True if mold risk is in a problematic state ('medium' or 'high')."""
    risk_level = calculate_mold_risk_level(temperature, humidity)
    if risk_level is None:
        return None
    return risk_level in ("medium", "high")


def calculate_ventilation_recommended(
    indoor_temp: float | None,
    indoor_humidity: float | None,
    outdoor_temp: float | None,
    outdoor_humidity: float | None,
) -> bool | None:
    """Determine whether opening windows/ventilating will reduce indoor humidity.

    Ventilation is recommended if the indoor absolute moisture content (g/m³) is
    higher than the outdoor moisture content by at least 1.0 g/m³.
    If outdoor humidity is not available, falls back to a warning threshold
    if indoor humidity is high (>= 65.0%).
    """
    ah_in = calculate_absolute_humidity(indoor_temp, indoor_humidity)
    if ah_in is None:
        return None

    ah_out = calculate_absolute_humidity(outdoor_temp, outdoor_humidity)
    if ah_out is not None:
        return (ah_in - ah_out) >= 1.0

    # Fallback when outdoor humidity is not known
    if indoor_humidity is not None:
        return float(indoor_humidity) >= 65.0
    return False
