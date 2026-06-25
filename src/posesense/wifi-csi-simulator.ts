/** Simulate WiFi CSI through-wall demo frames. */

import type { CsiFrame } from "./wifi-csi-engine.js";

type CsiCallback = (frame: CsiFrame) => void;

export class WiFiCsiSimulator {
  private running = false;
  private phase = 0;
  private personX = 0.5;
  private activity = "idle";
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private onFrame: CsiCallback, public wallMode = true) {}

  start(): void {
    if (this.running) return;
    this.running = true;
    const cycle: Array<[string, number, boolean]> = [
      ["idle", 3000, false], ["walking", 5000, true], ["active", 3000, true], ["idle", 2000, true],
    ];
    let idx = 0;
    let segStart = Date.now();

    this.timer = setInterval(() => {
      if (!this.running) return;
      const [act, dur, active] = cycle[idx];
      this.activity = act;
      if (Date.now() - segStart >= dur) {
        idx = (idx + 1) % cycle.length;
        segStart = Date.now();
        return;
      }
      this.phase += 0.06;
      if (active) this.personX = 0.5 + Math.sin(this.phase * 0.7) * 0.35;

      const amps: number[] = [];
      const phases: number[] = [];
      for (let i = 0; i < 64; i++) {
        const freqBin = i / 64;
        let base = 1 + 0.1 * Math.sin(this.phase + freqBin * 6);
        if (active) {
          const peak = Math.exp(-((freqBin - this.personX) ** 2) / 0.02);
          const motion = act === "walking" ? Math.sin(this.phase * 4) * 0.25 : act === "active" ? Math.sin(this.phase * 6) * 0.4 : 0;
          const atten = this.wallMode ? 0.55 : 1;
          base += peak * atten * (0.35 + motion);
          phases.push(peak * atten * Math.sin(this.phase * 2 + i * 0.2) * 1.5);
        } else {
          phases.push(0.05 * Math.sin(this.phase + i * 0.1));
        }
        amps.push(base + (Math.random() - 0.5) * 0.06);
      }
      this.onFrame({
        amplitudes: amps,
        phases,
        rssi: -55 + (active ? 5 : 0) + (Math.random() - 0.5) * 2.4,
        timestamp: Date.now() / 1000,
        source: "sim",
      });
    }, 80);
  }

  stop(): void {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
  }
}
