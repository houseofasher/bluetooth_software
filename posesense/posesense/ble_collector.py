"""BLE advertisement scanner with device classification metadata."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from typing import Callable

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .ble_classifier import classify_device
from .windows_bluetooth_registry import paired_bluetooth_devices, paired_device_meta

BleCallback = Callable[[str, str, float, float, dict], None]


class BleCollector:
    """Scan BLE advertisements and report RSSI + device identity metadata."""

    def __init__(self, on_device: BleCallback, name_filter: str | None = None) -> None:
        self.on_device = on_device
        self.name_filter = name_filter.lower() if name_filter else None
        self._running = False
        self._thread: threading.Thread | None = None
        self._paired_thread: threading.Thread | None = None

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
        meta["source"] = "ble_advertisement"
        meta["is_paired"] = False
        meta["is_live_signal"] = True
        meta["scan_note"] = "Live BLE advertisement."

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

    def _paired_poll_loop(self) -> None:
        while self._running:
            for paired in paired_bluetooth_devices():
                if self.name_filter and self.name_filter not in paired.name.lower():
                    continue
                meta = classify_device(paired.name, address=paired.address)
                meta.update(paired_device_meta(paired))
                if not meta.get("brand") and meta.get("device_type") == "phone":
                    meta["brand"] = "Phone"
                meta["display_name"] = paired.name
                meta["model"] = paired.name
                # Windows paired fallback has no RSSI. Use a fixed weak value so
                # it is bindable but never mistaken for live signal strength.
                self.on_device(paired.address, paired.name, -92.0, time.time(), meta)
            time.sleep(5.0 if sys.platform == "win32" else 30.0)

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        self._paired_thread = threading.Thread(target=self._paired_poll_loop, daemon=True)
        self._paired_thread.start()
        while self._running:
            await asyncio.sleep(0.5)

    def stop(self) -> None:
        self._running = False
