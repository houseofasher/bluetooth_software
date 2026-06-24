"""Merge naming, distance, location context, and pulled GATT data into device records."""

from __future__ import annotations

from typing import Any

from ble_device_naming import DeviceSignals, signals_to_record
from ble_distance import distance_payload
from ble_location import ScannerLocation, location_context_for_device


def build_device_record(
    signals: DeviceSignals,
    paired_names: dict[str, str],
    scanner: ScannerLocation,
    pulled_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = signals_to_record(signals, paired_names)
    dist = distance_payload(signals.rssi, signals.tx_power)
    record.update(dist)
    record["location"] = location_context_for_device(dist["distanceMeters"], scanner)
    record["pulledData"] = pulled_data
    record["pullStatus"] = "ready" if pulled_data is None else ("ok" if pulled_data.get("ok") else "failed")
    return record
