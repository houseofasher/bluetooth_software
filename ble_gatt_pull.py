"""Pull permitted GATT data from a BLE device to the local dashboard."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from bleak import BleakClient

GATT_TIMEOUT_SEC = 8.0

# Standard read-only characteristics safe for testing pulls.
READABLE_CHARS: list[tuple[str, str, str]] = [
    ("00001800-0000-1000-8000-00805f9b34fb", "00002a00-0000-1000-8000-00805f9b34fb", "deviceName"),
    ("0000180f-0000-1000-8000-00805f9b34fb", "00002a19-0000-1000-8000-00805f9b34fb", "batteryLevel"),
    ("0000180a-0000-1000-8000-00805f9b34fb", "00002a29-0000-1000-8000-00805f9b34fb", "manufacturerName"),
    ("0000180a-0000-1000-8000-00805f9b34fb", "00002a24-0000-1000-8000-00805f9b34fb", "modelNumber"),
    ("0000180a-0000-1000-8000-00805f9b34fb", "00002a25-0000-1000-8000-00805f9b34fb", "serialNumber"),
    ("0000180a-0000-1000-8000-00805f9b34fb", "00002a26-0000-1000-8000-00805f9b34fb", "firmwareRevision"),
    ("0000180a-0000-1000-8000-00805f9b34fb", "00002a27-0000-1000-8000-00805f9b34fb", "hardwareRevision"),
]


def _decode_value(key: str, raw: bytearray) -> Any:
    if key == "batteryLevel" and len(raw) >= 1:
        return int(raw[0])
    text = raw.decode("utf-8", errors="ignore").replace("\x00", "").strip()
    return text or None


async def pull_device_data(address: str) -> dict[str, Any]:
    pulled: dict[str, Any] = {}
    errors: list[str] = []

    try:
        async with BleakClient(address, timeout=GATT_TIMEOUT_SEC) as client:
            for service_uuid, char_uuid, key in READABLE_CHARS:
                try:
                    raw = await client.read_gatt_char(char_uuid)
                    value = _decode_value(key, raw)
                    if value is not None:
                        pulled[key] = value
                except Exception as exc:
                    errors.append(f"{key}: {exc}")
    except Exception as exc:
        return {
            "ok": False,
            "address": address,
            "data": {},
            "errors": [str(exc)],
            "pulledAt": int(time.time() * 1000),
        }

    return {
        "ok": bool(pulled),
        "address": address,
        "data": pulled,
        "errors": errors,
        "pulledAt": int(time.time() * 1000),
    }


def pull_device_data_sync(address: str) -> dict[str, Any]:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(pull_device_data(address))
    finally:
        loop.close()
