"""Windows WiFi RSSI scanner — coarse motion proxy when CSI hardware unavailable."""

from __future__ import annotations

import asyncio
import random
import re
import subprocess
import time
from typing import Callable

from .wifi_csi_engine import CsiFrame

CsiCallback = Callable[[CsiFrame], None]
SUBCARRIERS = 64


class WiFiRssiScanner:
    """
    Scan nearby WiFi BSSIDs via netsh; treat RSSI variance as body-motion proxy.

    Not true CSI, but mimics smart-home 'WiFi sensing' products on consumer hardware.
    """

    def __init__(self, on_frame: CsiCallback) -> None:
        self.on_frame = on_frame
        self._running = False
        self._thread = None

    async def run(self) -> None:
        self._running = True
        while self._running:
            rssis = self._scan_rssi()
            if rssis:
                mean = sum(rssis) / len(rssis)
                # Synthesize pseudo-CSI from RSSI spread across networks
                amps = []
                phases = []
                for i, r in enumerate(rssis[:SUBCARRIERS]):
                    delta = (r - mean) / 100.0
                    amps.append(1.0 + delta + random.gauss(0, 0.02))
                    phases.append(delta * 2 + random.gauss(0, 0.01))
                while len(amps) < SUBCARRIERS:
                    amps.append(1.0 + random.gauss(0, 0.01))
                    phases.append(random.gauss(0, 0.01))
                self.on_frame(CsiFrame(
                    amplitudes=amps[:SUBCARRIERS],
                    phases=phases[:SUBCARRIERS],
                    rssi=mean,
                    timestamp=time.time(),
                    source="rssi",
                ))
            await asyncio.sleep(0.5)

    @staticmethod
    def _scan_rssi() -> list[float]:
        try:
            out = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            signals = []
            for line in out.stdout.splitlines():
                m = re.search(r"Signal\s*:\s*(\d+)%", line)
                if m:
                    pct = int(m.group(1))
                    signals.append(-100 + pct * 0.5)
            return signals
        except Exception:
            return []

    def stop(self) -> None:
        self._running = False
