"""BLE advertisement scanner with device classification metadata."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .ble_classifier import classify_device

BleCallback = Callable[[str, str, float, float, dict], None]


class BleCollector:
    """Scan BLE advertisements and report RSSI + device identity metadata."""

    def __init__(self, on_device: BleCallback, name_filter: str | None = None) -> None:
        self.on_device = on_device
        self.name_filter = name_filter.lower() if name_filter else None
        self._running = False
        self._thread: threading.Thread | None = None

    def _handle(self, device: BLEDevice, adv: AdvertisementData) -> None:
        raw_name = adv.local_name or device.name or "Unknown"
        addr = device.address

        if self.name_filter and self.name_filter not in raw_name.lower():
            return

        rssi = adv.rssi if adv.rssi is not None else getattr(device, "rssi", None)
        if rssi is None:
            return

        mfg = {k: bytes(v) for k, v in (adv.manufacturer_data or {}).items()}
        uuids = list(adv.service_uuids or [])
        meta = classify_device(raw_name, mfg, uuids, address=addr)
        meta["manufacturer_data"] = {hex(k): v.hex() for k, v in mfg.items()}
        meta["service_uuids"] = uuids

        display = meta["display_name"]
        self.on_device(addr, display, float(rssi), time.time(), meta)

    async def _scan_loop(self) -> None:
        async with BleakScanner(self._handle) as _scanner:
            while self._running:
                await asyncio.sleep(0.2)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._scan_loop())
        finally:
            loop.close()

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        while self._running:
            await asyncio.sleep(0.5)

    def stop(self) -> None:
        self._running = False
