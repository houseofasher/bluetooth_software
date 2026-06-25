"""Simulate WiFi CSI through-wall sensing (research-grade demo)."""

from __future__ import annotations

import asyncio
import math
import random
import time
from typing import Callable

from .wifi_csi_engine import CsiFrame

CsiCallback = Callable[[CsiFrame], None]

SUBCARRIERS = 64


class WiFiCsiSimulator:
    """
    Simulates router CSI perturbed by a person moving behind a wall.

    Models multipath change when body reflects 2.4/5 GHz signals through drywall.
    """

    def __init__(self, on_frame: CsiCallback, wall_mode: bool = True) -> None:
        self.on_frame = on_frame
        self.wall_mode = wall_mode
        self._running = False
        self._phase = 0.0
        self._person_x = 0.5
        self._activity = "idle"
        self._behind_wall = True

    async def run(self) -> None:
        self._running = True
        cycle = [
            ("idle", 3.0, False),
            ("walking", 5.0, True),
            ("active", 3.0, True),
            ("idle", 2.0, True),
        ]
        idx = 0
        seg_start = time.time()

        while self._running:
            activity, duration, person_active = cycle[idx]
            self._activity = activity
            self._behind_wall = person_active
            if time.time() - seg_start >= duration:
                idx = (idx + 1) % len(cycle)
                seg_start = time.time()
                continue

            self._phase += 0.06
            if person_active:
                self._person_x = 0.5 + math.sin(self._phase * 0.7) * 0.35

            amps, phases = self._synthesize_csi(person_active)
            rssi = -55 + (5.0 if person_active else 0) + random.gauss(0, 1.2)
            self.on_frame(CsiFrame(
                amplitudes=amps,
                phases=phases,
                rssi=rssi,
                timestamp=time.time(),
                source="sim",
            ))
            await asyncio.sleep(0.08)

    def _synthesize_csi(self, person_active: bool) -> tuple[list[float], list[float]]:
        amps, phases = [], []
        for i in range(SUBCARRIERS):
            freq_bin = i / SUBCARRIERS
            base_amp = 1.0 + 0.1 * math.sin(self._phase + freq_bin * 6)

            if person_active:
                # Body reflection peak shifts with lateral position
                body_peak = math.exp(-((freq_bin - self._person_x) ** 2) / 0.02)
                motion = 0.0
                if self._activity == "walking":
                    motion = math.sin(self._phase * 4) * 0.25
                elif self._activity == "active":
                    motion = math.sin(self._phase * 6) * 0.4
                wall_atten = 0.55 if self.wall_mode else 1.0
                base_amp += body_peak * wall_atten * (0.35 + motion)
                phase_shift = body_peak * wall_atten * math.sin(self._phase * 2 + i * 0.2) * 1.5
            else:
                phase_shift = 0.05 * math.sin(self._phase + i * 0.1)

            amps.append(base_amp + random.gauss(0, 0.03))
            phases.append(phase_shift + random.gauss(0, 0.02))

        return amps, phases

    def stop(self) -> None:
        self._running = False
