"""Hive intelligence rules shared across NESTR components.

Prototype-level thresholds for stingless beehive monitoring. Keeping them in a
single module avoids drift between the gateway API, the forecasting model, and
any other consumer of these rules.
"""

from __future__ import annotations

from typing import Any, Dict, List

HARVEST_THRESHOLD_KG = 8.0

TEMPERATURE_MIN_C = 24.0
TEMPERATURE_MAX_C = 34.0
HUMIDITY_MIN_PERCENT = 50.0
HUMIDITY_MAX_PERCENT = 85.0


def coerce_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float, falling back to ``default`` when invalid."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_harvest_ready(weight_kg: float) -> bool:
    """Return whether the hive weight has reached the harvest threshold."""
    return weight_kg >= HARVEST_THRESHOLD_KG


def harvest_readiness_percent(weight_kg: float) -> float:
    """Return harvest readiness as a percentage clamped to the 0-100 range."""
    return max(0.0, min(round((weight_kg / HARVEST_THRESHOLD_KG) * 100, 2), 100))


def classify_conditions(
    temperature_c: float,
    humidity_percent: float,
    weight_kg: float,
) -> Dict[str, Any]:
    """Prototype condition detection rules for stingless beehive monitoring."""
    temp = coerce_float(temperature_c)
    humidity = coerce_float(humidity_percent)
    weight = coerce_float(weight_kg)

    alerts: List[str] = []

    if temp < TEMPERATURE_MIN_C:
        alerts.append("Temperature Low")
    elif temp > TEMPERATURE_MAX_C:
        alerts.append("Temperature High")

    if humidity < HUMIDITY_MIN_PERCENT:
        alerts.append("Humidity Low")
    elif humidity > HUMIDITY_MAX_PERCENT:
        alerts.append("Humidity High")

    if is_harvest_ready(weight):
        alerts.append("Harvest Potential")

    return {
        "status": "Attention Required" if alerts else "Normal",
        "alerts": alerts,
        "harvest_ready": is_harvest_ready(weight),
        "readiness_percent": harvest_readiness_percent(weight),
    }
