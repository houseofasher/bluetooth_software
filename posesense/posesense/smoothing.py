"""Temporal smoothing for landmark coordinates (reduces jitter)."""

from __future__ import annotations

import math
import time


class OneEuroFilter:
    """1€ filter — adaptive low-latency smoothing for tracking."""

    def __init__(self, min_cutoff: float = 1.2, beta: float = 0.008, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x: float | None = None
        self._dx = 0.0
        self._t: float | None = None

    def _alpha(self, cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def __call__(self, x: float, t: float | None = None) -> float:
        t = t or time.time()
        if self._x is None or self._t is None:
            self._x = x
            self._t = t
            return x

        dt = max(t - self._t, 1e-6)
        dx = (x - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff, dt)
        self._x = a * x + (1 - a) * self._x
        self._t = t
        return self._x


class LandmarkSmoother:
    """Per-person smoother bank for x, y, confidence channels."""

    def __init__(self, count: int, prefix: str = "") -> None:
        self._fx = [OneEuroFilter(min_cutoff=1.0, beta=0.01) for _ in range(count)]
        self._fy = [OneEuroFilter(min_cutoff=1.0, beta=0.01) for _ in range(count)]
        self._prefix = prefix

    def smooth(self, points: list[dict], t: float | None = None) -> list[dict]:
        out = []
        for i, p in enumerate(points):
            conf = p.get("confidence", 0.5)
            if conf < 0.15:
                out.append(dict(p))
                continue
            fx = self._fx[i] if i < len(self._fx) else OneEuroFilter()
            fy = self._fy[i] if i < len(self._fy) else OneEuroFilter()
            out.append({
                **p,
                "x": fx(p["x"], t),
                "y": fy(p["y"], t),
                "confidence": conf,
            })
        return out
