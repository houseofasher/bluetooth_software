"""Scanner geolocation + reverse geocode for co-location context."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "bluetooth-scanning/1.0 (local testing tool)"

# Devices within this radius are tagged as co-located with the scanner (same home/room).
CO_LOCATE_RADIUS_METERS = 15.0


@dataclass
class ScannerLocation:
    latitude: float | None = None
    longitude: float | None = None
    accuracy_meters: float | None = None
    address: str | None = None
    address_short: str | None = None
    source: str | None = None
    updated_at: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set_coords(
        self,
        latitude: float,
        longitude: float,
        accuracy_meters: float | None = None,
        source: str = "browser",
    ) -> None:
        with self.lock:
            self.latitude = latitude
            self.longitude = longitude
            self.accuracy_meters = accuracy_meters
            self.source = source
            self.address = None
            self.address_short = None
            self.updated_at = time.time()

    def set_address(self, full: str, short: str | None = None) -> None:
        with self.lock:
            self.address = full
            self.address_short = short or full
            self.updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "accuracyMeters": self.accuracy_meters,
                "address": self.address,
                "addressShort": self.address_short,
                "source": self.source,
                "updatedAt": self.updated_at,
                "ready": self.latitude is not None and self.longitude is not None,
            }


SCANNER_LOCATION = ScannerLocation()


def reverse_geocode(latitude: float, longitude: float) -> tuple[str, str]:
    """Return (full_address, short_label) via OpenStreetMap Nominatim."""
    params = urllib.parse.urlencode(
        {
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
        }
    )
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    address = data.get("display_name") or "Unknown location"
    parts = data.get("address") or {}
    short_parts = [
        parts.get("house_number"),
        parts.get("road"),
        parts.get("city") or parts.get("town") or parts.get("village"),
        parts.get("state"),
    ]
    short = ", ".join(p for p in short_parts if p) or address
    return address, short


def location_context_for_device(
    distance_meters: float | None,
    scanner: ScannerLocation,
) -> dict[str, Any]:
    """
    BLE devices do not broadcast GPS or street addresses.
    If a device is close enough while we know scanner position, we infer co-location.
    """
    snap = scanner.snapshot()
    co_located = (
        distance_meters is not None
        and distance_meters <= CO_LOCATE_RADIUS_METERS
        and snap["ready"]
    )
    return {
        "coLocated": co_located,
        "estimatedAddress": snap["address"] if co_located else None,
        "estimatedAddressShort": snap["addressShort"] if co_located else None,
        "scannerLatitude": snap["latitude"],
        "scannerLongitude": snap["longitude"],
        "contextNote": (
            "Device was in range while your PC was at this address (estimated co-location)."
            if co_located
            else "BLE cannot report a remote device's home address — only your scanner location is known."
        ),
    }
