"""Shared NESTR domain utilities used across the AIoT stingless beehive system.

These helpers centralise the hive intelligence rules (harvest threshold,
readiness percentage, and condition classification) that were previously
duplicated between the Raspberry Pi gateway and the ML prediction module.
"""

from .hive_intelligence import (
    HARVEST_THRESHOLD_KG,
    HUMIDITY_MAX_PERCENT,
    HUMIDITY_MIN_PERCENT,
    TEMPERATURE_MAX_C,
    TEMPERATURE_MIN_C,
    classify_conditions,
    coerce_float,
    harvest_readiness_percent,
    is_harvest_ready,
)

__all__ = [
    "HARVEST_THRESHOLD_KG",
    "HUMIDITY_MAX_PERCENT",
    "HUMIDITY_MIN_PERCENT",
    "TEMPERATURE_MAX_C",
    "TEMPERATURE_MIN_C",
    "classify_conditions",
    "coerce_float",
    "harvest_readiness_percent",
    "is_harvest_ready",
]
