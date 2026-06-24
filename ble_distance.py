"""Estimate distance from RSSI using a log-distance path loss model."""

from __future__ import annotations

import math
from typing import Any, Literal

DEFAULT_TX_POWER = -59  # dBm at 1 m (typical BLE fallback)
PATH_LOSS_EXPONENT = 2.0  # indoor-ish; free space is ~2.0, cluttered home ~2.5-3.5

ProximityZone = Literal["immediate", "near", "far", "unknown"]

METERS_TO_FEET = 3.28084
METERS_TO_MILES = 1 / 1609.344


def estimate_distance_meters(
    rssi: int | None,
    tx_power: int | None = None,
    path_loss_exponent: float = PATH_LOSS_EXPONENT,
) -> float | None:
    if rssi is None:
        return None
    measured_tx = tx_power if tx_power is not None else DEFAULT_TX_POWER
    try:
        exponent = (measured_tx - rssi) / (10.0 * path_loss_exponent)
        distance = 10.0**exponent
        if not math.isfinite(distance) or distance < 0:
            return None
        return max(0.1, min(distance, 500.0))  # clamp to plausible BLE range
    except (OverflowError, ValueError):
        return None


def proximity_zone(distance_meters: float | None) -> ProximityZone:
    if distance_meters is None:
        return "unknown"
    if distance_meters <= 3.0:
        return "immediate"
    if distance_meters <= 15.0:
        return "near"
    return "far"


def format_distance(distance_meters: float | None) -> str:
    if distance_meters is None:
        return "Unknown"
    feet = distance_meters * METERS_TO_FEET
    if feet < 528:  # ~0.1 mile
        return f"{feet:.0f} ft"
    miles = distance_meters * METERS_TO_MILES
    if miles < 0.1:
        return f"{feet:.0f} ft"
    return f"{miles:.2f} mi"


def distance_payload(
    rssi: int | None,
    tx_power: int | None = None,
) -> dict[str, Any]:
    meters = estimate_distance_meters(rssi, tx_power)
    feet = meters * METERS_TO_FEET if meters is not None else None
    miles = meters * METERS_TO_MILES if meters is not None else None
    zone = proximity_zone(meters)
    return {
        "distanceMeters": round(meters, 2) if meters is not None else None,
        "distanceFeet": round(feet, 1) if feet is not None else None,
        "distanceMiles": round(miles, 4) if miles is not None else None,
        "distanceLabel": format_distance(meters),
        "proximityZone": zone,
        "rssi": rssi,
        "txPower": tx_power,
        "distanceNote": "Estimated from RSSI - walls and interference affect accuracy.",
    }
