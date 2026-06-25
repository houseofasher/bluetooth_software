"""Simulate RSSI from virtual beacons when no BLE hardware is available."""

from __future__ import annotations

import asyncio
import math
import random
import time
from typing import Callable

from .motion_engine import Activity

RssiCallback = Callable[[str, str, float, float], None]

# Three virtual beacons placed around a room (for multipath simulation)
VIRTUAL_BEACONS = [
    ("AA:BB:CC:00:00:01", "Beacon-North"),
    ("AA:BB:CC:00:00:02", "Beacon-East"),
    ("AA:BB:CC:00:00:03", "Beacon-South"),
]


class MotionSimulator:
    """Cycle through activities and emit realistic RSSI fluctuations."""

    def __init__(self, on_rssi: RssiCallback) -> None:
        self.on_rssi = on_rssi
        self._running = False
        self._activity = Activity.IDLE
        self._phase = 0.0
        self._lateral = 0.0

    async def run(self) -> None:
        self._running = True
        cycle = [
            (Activity.IDLE, 4.0),
            (Activity.WALKING, 6.0),
            (Activity.ARM_RAISE, 4.0),
            (Activity.CROUCH, 3.0),
            (Activity.ACTIVE, 4.0),
        ]
        idx = 0
        segment_start = time.time()

        while self._running:
            activity, duration = cycle[idx]
            self._activity = activity
            elapsed = time.time() - segment_start

            if elapsed >= duration:
                idx = (idx + 1) % len(cycle)
                segment_start = time.time()
                continue

            self._phase += 0.08
            self._lateral = math.sin(self._phase * 0.4) * 0.5
            ts = time.time()

            for i, (addr, name) in enumerate(VIRTUAL_BEACONS):
                base = -62 - i * 4
                noise = random.gauss(0, self._noise_level())
                motion = self._motion_signal(i)
                rssi = base + noise + motion
                self.on_rssi(addr, name, rssi, ts)

            await asyncio.sleep(0.12)

    def _noise_level(self) -> float:
        levels = {
            Activity.IDLE: 0.8,
            Activity.WALKING: 2.5,
            Activity.ARM_RAISE: 2.0,
            Activity.CROUCH: 1.8,
            Activity.ACTIVE: 3.0,
        }
        return levels.get(self._activity, 1.0)

    def _motion_signal(self, beacon_idx: int) -> float:
        a = self._activity
        p = self._phase

        if a == Activity.IDLE:
            return math.sin(p * 0.5 + beacon_idx) * 0.5

        if a == Activity.WALKING:
            walk = math.sin(p * 3.0 + beacon_idx * 1.2) * 5.0
            shift = self._lateral * (3.0 if beacon_idx == 1 else -1.5)
            return walk + shift

        if a == Activity.ARM_RAISE:
            # Upper beacon sees more change when arms go up
            return (4.0 if beacon_idx == 0 else 1.5) * math.sin(p * 1.5) + 2.0

        if a == Activity.CROUCH:
            return -3.0 - beacon_idx * 0.5 + math.sin(p) * 1.5

        return math.sin(p * 2.5 + beacon_idx) * 4.0

    def stop(self) -> None:
        self._running = False
