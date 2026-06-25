/** WiFi CSI / RSSI presence and through-wall sensing. */

export interface CsiFrame {
  amplitudes: number[];
  phases: number[];
  rssi: number;
  timestamp: number;
  source: string;
}

export class WiFiCsiEngine {
  private frames: CsiFrame[] = [];
  private spectrogram: number[][] = [];
  private homeOccupied = false;
  private homeSince: number | null = null;
  private lightsOn = false;

  ingest(frame: CsiFrame): void {
    this.frames.push(frame);
    if (this.frames.length > 50) this.frames.shift();
    const motion = this.subcarrierMotion(frame);
    this.spectrogram.push(motion);
    if (this.spectrogram.length > 40) this.spectrogram.shift();
  }

  private subcarrierMotion(frame: CsiFrame): number[] {
    if (this.frames.length < 2) return frame.amplitudes.slice(0, 64);
    const prev = this.frames[this.frames.length - 2];
    const n = Math.min(frame.amplitudes.length, prev.amplitudes.length, 64);
    return Array.from({ length: n }, (_, i) => Math.abs(frame.amplitudes[i] - prev.amplitudes[i]));
  }

  analyze(cameraPersonCount = 0, wallMode = false): Record<string, unknown> {
    if (this.frames.length < 3) {
      return {
        occupied: false, motion_energy: 0, activity: "none", through_wall: false,
        through_wall_confidence: 0, zone: "unknown", zone_x: 0.5, home_detected: false,
        automation: this.automation(), message: "Calibrating WiFi sensing field…",
        subcarrier_motion: [], spectrogram: this.spectrogram.slice(-20),
      };
    }

    const motionSc = this.subcarrierMotion(this.frames[this.frames.length - 1]);
    const avgMotion = motionSc.reduce((a, b) => a + b, 0) / Math.max(motionSc.length, 1);
    const recent = this.frames.slice(-10);
    const rssis = recent.map((f) => f.rssi);
    const rssiMean = rssis.reduce((a, b) => a + b, 0) / rssis.length;
    const rssiVar = rssis.reduce((a, r) => a + (r - rssiMean) ** 2, 0) / rssis.length;
    const phases = this.frames[this.frames.length - 1].phases;
    const pm = phases.reduce((a, b) => a + b, 0) / Math.max(phases.length, 1);
    const phaseSpread = Math.sqrt(phases.reduce((a, p) => a + (p - pm) ** 2, 0) / Math.max(phases.length, 1));

    const motionEnergy = Math.min(1, avgMotion * 8 + Math.sqrt(rssiVar) * 0.15);
    const occupied = motionEnergy > 0.12 || rssiVar > 2 || phaseSpread > 0.4;
    const activity = motionEnergy < 0.15 ? (occupied ? "idle" : "none") : motionEnergy < 0.45 ? "walking" : "active";

    const n = motionSc.length;
    let zoneX = 0.5;
    let zone = "center";
    if (n >= 8) {
      const leftE = motionSc.slice(0, Math.floor(n / 3)).reduce((a, b) => a + b, 0);
      const rightE = motionSc.slice(Math.floor((2 * n) / 3)).reduce((a, b) => a + b, 0);
      zoneX = rightE / (leftE + rightE + 1e-6);
      zone = zoneX < 0.38 ? "left" : zoneX > 0.62 ? "right" : "center";
    }

    const throughWall = wallMode && occupied && cameraPersonCount === 0;
    let twConf = 0;
    if (throughWall) twConf = Math.min(1, motionEnergy * 1.2 + phaseSpread * 0.3);

    const now = Date.now() / 1000;
    if (occupied && motionEnergy > 0.08) {
      if (!this.homeOccupied) this.homeSince = now;
      this.homeOccupied = true;
    } else if (motionEnergy < 0.05 && rssiVar < 0.5 && this.homeOccupied && this.homeSince && now - this.homeSince > 8) {
      this.homeOccupied = false;
      this.homeSince = null;
    }
    this.lightsOn = this.homeOccupied && motionEnergy > 0.18;

    let message = "WiFi field clear — no body perturbations";
    if (throughWall && twConf > 0.35) message = `WiFi CSI: motion behind wall (${activity}) — zone ${zone}`;
    else if (this.homeOccupied) message = "Home occupied — WiFi body reflection detected";
    else if (occupied) message = `WiFi motion detected (${activity})`;

    return {
      occupied,
      motion_energy: Math.round(motionEnergy * 1000) / 1000,
      activity,
      through_wall: throughWall,
      through_wall_confidence: Math.round(twConf * 1000) / 1000,
      zone,
      zone_x: Math.round(zoneX * 1000) / 1000,
      home_detected: this.homeOccupied,
      automation: this.automation(),
      message,
      subcarrier_motion: motionSc.map((v) => Math.round(v * 10000) / 10000),
      spectrogram: this.spectrogram.slice(-20),
    };
  }

  private automation(): Record<string, unknown> {
    return {
      home: this.homeOccupied,
      lights: this.lightsOn ? "on" : "off",
      wifi_boost: this.homeOccupied,
      climate: this.homeOccupied ? "comfort" : "away",
    };
  }
}
