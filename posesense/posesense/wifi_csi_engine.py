"""Process WiFi CSI / RSSI for presence, motion, and through-wall sensing."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class CsiFrame:
    """One CSI snapshot — amplitude & phase per subcarrier."""
    amplitudes: list[float]
    phases: list[float]
    rssi: float
    timestamp: float
    source: str = "unknown"  # sim, rssi, esp32


@dataclass
class WiFiPresenceState:
    occupied: bool
    motion_energy: float
    activity: str  # idle, walking, active, none
    through_wall: bool
    through_wall_confidence: float
    zone: str  # center, left, right, unknown
    zone_x: float  # 0-1 normalized lateral position estimate
    person_count_est: int
    subcarrier_motion: list[float]
    spectrogram_row: list[float]
    home_detected: bool
    automation: dict
    message: str


class WiFiCsiEngine:
    """
    Detect human presence from WiFi signal perturbations (CSI or RSSI proxy).

    Smart-home logic: sustained presence + motion → home occupied → trigger automations.
    Through-wall: motion detected when camera has no line-of-sight person.
    """

    def __init__(self, history: int = 50, subcarriers: int = 64) -> None:
        self.history_len = history
        self.subcarriers = subcarriers
        self._frames: deque[CsiFrame] = deque(maxlen=history)
        self._spectrogram: deque[list[float]] = deque(maxlen=40)
        self._home_occupied = False
        self._home_since: float | None = None
        self._lights_on = False
        self._last_motion = 0.0

    def ingest(self, frame: CsiFrame) -> None:
        self._frames.append(frame)
        motion_per_sc = self._subcarrier_motion(frame)
        self._spectrogram.append(motion_per_sc)

    def _subcarrier_motion(self, frame: CsiFrame) -> list[float]:
        if len(self._frames) < 2:
            return [0.0] * min(len(frame.amplitudes), self.subcarriers)
        prev = self._frames[-2]
        n = min(len(frame.amplitudes), len(prev.amplitudes), self.subcarriers)
        return [abs(frame.amplitudes[i] - prev.amplitudes[i]) for i in range(n)]

    def analyze(self, camera_person_count: int = 0, wall_mode: bool = False) -> WiFiPresenceState:
        if len(self._frames) < 3:
            return WiFiPresenceState(
                occupied=False,
                motion_energy=0.0,
                activity="none",
                through_wall=False,
                through_wall_confidence=0.0,
                zone="unknown",
                zone_x=0.5,
                person_count_est=0,
                subcarrier_motion=[0.0] * self.subcarriers,
                spectrogram_row=[0.0] * self.subcarriers,
                home_detected=False,
                automation=self._automation_state(),
                message="Calibrating WiFi sensing field…",
            )

        recent = list(self._frames)[-10:]
        motion_sc = self._subcarrier_motion(self._frames[-1])
        avg_motion = sum(motion_sc) / max(len(motion_sc), 1)

        # RSSI variance across recent frames
        rssis = [f.rssi for f in recent]
        rssi_mean = sum(rssis) / len(rssis)
        rssi_var = sum((r - rssi_mean) ** 2 for r in rssis) / len(rssis)

        motion_energy = min(1.0, avg_motion * 8.0 + math.sqrt(rssi_var) * 0.15)
        self._last_motion = motion_energy

        # Phase dispersion — body reflections shift phase patterns
        phases = self._frames[-1].phases
        phase_spread = 0.0
        if len(phases) > 4:
            pm = sum(phases) / len(phases)
            phase_spread = math.sqrt(sum((p - pm) ** 2 for p in phases) / len(phases))

        occupied = motion_energy > 0.12 or rssi_var > 2.0 or phase_spread > 0.4

        # Activity classification from motion energy profile
        if motion_energy < 0.15:
            activity = "idle" if occupied else "none"
        elif motion_energy < 0.45:
            activity = "walking"
        else:
            activity = "active"

        # Lateral zone from subcarrier bin energy asymmetry (RF imaging heuristic)
        n = len(motion_sc)
        if n >= 8:
            left_e = sum(motion_sc[: n // 3])
            right_e = sum(motion_sc[2 * n // 3 :])
            total = left_e + right_e + 1e-6
            zone_x = right_e / total
            if zone_x < 0.38:
                zone = "left"
            elif zone_x > 0.62:
                zone = "right"
            else:
                zone = "center"
        else:
            zone_x, zone = 0.5, "center"

        # Through-wall: WiFi sees occupant but camera does not
        through_wall = wall_mode and occupied and camera_person_count == 0
        tw_conf = 0.0
        if through_wall:
            tw_conf = min(1.0, motion_energy * 1.2 + phase_spread * 0.3)
        elif wall_mode and occupied and camera_person_count > 0:
            tw_conf = 0.2  # both sensors agree someone is present

        person_est = 0
        if occupied:
            person_est = 1 if motion_energy < 0.55 else min(3, 1 + int(motion_energy * 2))

        # Smart home: hysteresis for "someone is home"
        now = time.time()
        if occupied and motion_energy > 0.08:
            if not self._home_occupied:
                self._home_since = now
            self._home_occupied = True
        elif motion_energy < 0.05 and rssi_var < 0.5:
            if self._home_occupied and self._home_since and now - self._home_since > 8:
                self._home_occupied = False
                self._home_since = None

        # Automation triggers (simulated smart home)
        if self._home_occupied and motion_energy > 0.18:
            self._lights_on = True
        elif not self._home_occupied:
            self._lights_on = False

        spec_row = list(self._spectrogram)[-1] if self._spectrogram else motion_sc

        if through_wall and tw_conf > 0.35:
            msg = f"WiFi CSI: motion behind wall ({activity}) — zone {zone}"
        elif self._home_occupied:
            msg = "Home occupied — WiFi body reflection detected"
        elif occupied:
            msg = f"WiFi motion detected ({activity})"
        else:
            msg = "WiFi field clear — no body perturbations"

        return WiFiPresenceState(
            occupied=occupied,
            motion_energy=round(motion_energy, 3),
            activity=activity,
            through_wall=through_wall,
            through_wall_confidence=round(tw_conf, 3),
            zone=zone,
            zone_x=round(zone_x, 3),
            person_count_est=person_est,
            subcarrier_motion=[round(v, 4) for v in motion_sc],
            spectrogram_row=[round(v, 4) for v in spec_row],
            home_detected=self._home_occupied,
            automation=self._automation_state(),
            message=msg,
        )

    def _automation_state(self) -> dict:
        return {
            "home": self._home_occupied,
            "lights": "on" if self._lights_on else "off",
            "wifi_boost": self._home_occupied,
            "climate": "comfort" if self._home_occupied else "away",
            "trigger": "wifi_csi_body_reflection",
        }

    @property
    def spectrogram(self) -> list[list[float]]:
        return [list(row) for row in self._spectrogram]
