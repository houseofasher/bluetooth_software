"""Extract motion features from BLE RSSI time series."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import math
import time


class Activity(str, Enum):
    IDLE = "idle"
    WALKING = "walking"
    ARM_RAISE = "arm_raise"
    CROUCH = "crouch"
    ACTIVE = "active"


@dataclass
class MotionState:
    activity: Activity
    energy: float  # 0-1 overall motion intensity
    lateral: float  # -1 left to +1 right
    vertical: float  # -1 down/crouch to +1 up/reach
    confidence: float
    device_count: int
    timestamp: float = field(default_factory=time.time)


class RssiBuffer:
    """Rolling window of RSSI samples for one BLE address."""

    def __init__(self, window: int = 40) -> None:
        self.window = window
        self.samples: deque[tuple[float, float]] = deque(maxlen=window)

    def add(self, rssi: float, ts: float | None = None) -> None:
        self.samples.append((ts or time.time(), rssi))

    @property
    def values(self) -> list[float]:
        return [r for _, r in self.samples]

    def stats(self) -> dict[str, float]:
        vals = self.values
        if len(vals) < 3:
            return {"mean": vals[-1] if vals else -70, "std": 0.0, "range": 0.0, "slope": 0.0}

        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance)
        rng = max(vals) - min(vals)

        # Simple linear trend over recent samples
        n = len(vals)
        xs = list(range(n))
        x_mean = sum(xs) / n
        num = sum((xs[i] - x_mean) * (vals[i] - mean) for i in range(n))
        den = sum((x - x_mean) ** 2 for x in xs) or 1.0
        slope = num / den

        return {"mean": mean, "std": std, "range": rng, "slope": slope}


class MotionEngine:
    """
    Fuse RSSI streams from multiple BLE beacons into coarse motion state.

    This is not full body pose — BLE RSSI cannot resolve skeleton joints.
    We infer activity class and drive a procedural skeleton animation.
    """

    def __init__(self, window: int = 40) -> None:
        self.window = window
        self.buffers: dict[str, RssiBuffer] = {}
        self._last_state = MotionState(Activity.IDLE, 0.0, 0.0, 0.0, 0.0, 0)

    def ingest(self, address: str, rssi: float, ts: float | None = None) -> None:
        if address not in self.buffers:
            self.buffers[address] = RssiBuffer(self.window)
        self.buffers[address].add(rssi, ts)

    def analyze(self) -> MotionState:
        if not self.buffers:
            return MotionState(Activity.IDLE, 0.0, 0.0, 0.0, 0.0, 0)

        stats_list = [(addr, buf.stats()) for addr, buf in self.buffers.items() if len(buf.values) >= 3]
        if not stats_list:
            return MotionState(Activity.IDLE, 0.0, 0.0, 0.0, 0.1, len(self.buffers))

        # Aggregate motion energy from RSSI variance across all observed beacons
        stds = [s["std"] for _, s in stats_list]
        ranges = [s["range"] for _, s in stats_list]
        avg_std = sum(stds) / len(stds)
        avg_range = sum(ranges) / len(ranges)

        # Normalize: typical idle std ~0.5-1.5 dBm, walking ~3-8 dBm
        energy = min(1.0, (avg_std / 6.0) * 0.6 + (avg_range / 15.0) * 0.4)

        # Lateral: compare strongest vs weakest mean RSSI (proxy for position shift)
        means = [(addr, s["mean"]) for addr, s in stats_list]
        means.sort(key=lambda x: x[1], reverse=True)
        spread = means[0][1] - means[-1][1] if len(means) > 1 else 0.0
        slopes = [s["slope"] for _, s in stats_list]
        avg_slope = sum(slopes) / len(slopes)
        lateral = max(-1.0, min(1.0, avg_slope * 0.15 + (spread / 20.0) * 0.3))

        # Vertical: sudden mean drop across beacons suggests crouch; high variance + positive slope suggests reach
        mean_of_means = sum(s["mean"] for _, s in stats_list) / len(stats_list)
        vertical = 0.0
        if mean_of_means < -78 and energy > 0.25:
            vertical = -0.7  # weaker signal often = lower body position / farther
        elif energy > 0.55 and avg_slope > 0.3:
            vertical = 0.75  # rising RSSI pattern while moving = arm raise proxy

        activity = self._classify(energy, vertical, avg_std)
        confidence = min(1.0, len(stats_list) / 3.0) * min(1.0, 0.3 + energy)

        state = MotionState(activity, energy, lateral, vertical, confidence, len(stats_list))
        self._last_state = state
        return state

    @staticmethod
    def _classify(energy: float, vertical: float, avg_std: float) -> Activity:
        if energy < 0.12:
            return Activity.IDLE
        if vertical > 0.6:
            return Activity.ARM_RAISE
        if vertical < -0.5:
            return Activity.CROUCH
        if energy > 0.35 and avg_std > 2.5:
            return Activity.WALKING
        if energy > 0.2:
            return Activity.ACTIVE
        return Activity.IDLE
