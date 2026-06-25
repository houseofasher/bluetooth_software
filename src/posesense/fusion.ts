/** Fuse browser pose detections with BLE devices from ScanState. */

import { inferPlacement, personHoldingPhone } from "./body-placement.js";
import type { PersonDetection, TrackedTarget } from "./types.js";

interface BleDev {
  address: string;
  name: string;
  rssi: number;
  brand: string | null;
  model: string;
  display_name: string;
  device_type: string;
  is_phone: boolean;
  likely_body_zone: string;
  icon: string;
  type_confidence: number;
  last_seen: number;
  rssiHistory: number[];
}

export class FusionEngine {
  devices = new Map<string, BleDev>();
  bindings = new Map<number, string>();
  bindMethods = new Map<number, string>();
  companionBindings = new Map<number, string[]>();

  ingestBle(address: string, name: string, rssi: number, ts: number, meta: Record<string, unknown>): void {
    let dev = this.devices.get(address);
    if (!dev) {
      dev = {
        address, name, rssi, brand: null, model: "Unknown", display_name: name,
        device_type: "unknown", is_phone: false, likely_body_zone: "Unknown", icon: "📡",
        type_confidence: 0.3, last_seen: ts, rssiHistory: [],
      };
      this.devices.set(address, dev);
    }
    dev.name = name;
    dev.rssi = rssi;
    dev.brand = (meta.brand as string) ?? dev.brand;
    dev.model = (meta.model as string) ?? dev.model;
    dev.display_name = (meta.display_name as string) ?? name;
    dev.device_type = (meta.device_type as string) ?? dev.device_type;
    dev.is_phone = Boolean(meta.is_phone ?? dev.is_phone);
    dev.likely_body_zone = (meta.likely_body_zone as string) ?? dev.likely_body_zone;
    dev.icon = (meta.icon as string) ?? dev.icon;
    dev.type_confidence = (meta.confidence as number) ?? dev.type_confidence;
    dev.last_seen = ts;
    dev.rssiHistory.push(rssi);
    if (dev.rssiHistory.length > 40) dev.rssiHistory.shift();
  }

  bindManual(personId: number, address: string): boolean {
    if (!this.devices.has(address)) return false;
    for (const [pid, addr] of this.bindings) {
      if (addr === address) this.bindings.delete(pid);
    }
    this.bindings.set(personId, address);
    this.bindMethods.set(personId, "manual");
    return true;
  }

  unbind(personId: number): void {
    this.bindings.delete(personId);
    this.bindMethods.delete(personId);
    this.companionBindings.delete(personId);
  }

  private phoneCandidates(list: BleDev[]): BleDev[] {
    return list.filter((d) => d.is_phone || d.device_type === "phone" || d.device_type === "tablet" || (d.brand === "Apple" && d.device_type !== "audio" && d.device_type !== "watch"));
  }

  private tryAutoBind(persons: PersonDetection[]): void {
    const now = Date.now() / 1000;
    const bound = new Set(this.bindings.values());
    const unboundP = persons.filter((p) => !this.bindings.has(p.person_id));
    let unboundD = [...this.devices.values()].filter((d) => !bound.has(d.address) && now - d.last_seen < 20);
    if (!unboundP.length || !unboundD.length) return;

    for (const person of unboundP) {
      const [holding] = personHoldingPhone(person.pose, person.left_hand, person.right_hand);
      if (!holding) continue;
      const phones = this.phoneCandidates(unboundD);
      const pool = phones.length ? phones : unboundD.filter((d) => d.brand === "Apple");
      if (!pool.length) continue;
      const best = pool.reduce((a, b) => (a.rssi > b.rssi ? a : b));
      if (best.rssi >= -92) {
        this.bindings.set(person.person_id, best.address);
        this.bindMethods.set(person.person_id, "auto-hand-proximity");
        bound.add(best.address);
        unboundD = unboundD.filter((d) => d.address !== best.address);
        break;
      }
    }

    if (unboundP.length === 1) {
      const phones = this.phoneCandidates(unboundD);
      if (phones.length === 1) {
        this.bindings.set(unboundP[0].person_id, phones[0].address);
        this.bindMethods.set(unboundP[0].person_id, "auto-phone");
      } else if (phones.length > 0) {
        const best = phones.reduce((a, b) => (a.rssi > b.rssi ? a : b));
        if (best.rssi >= -88) {
          this.bindings.set(unboundP[0].person_id, best.address);
          this.bindMethods.set(unboundP[0].person_id, "auto-strongest-phone");
        }
      }
    }

    for (const person of persons) {
      if (!this.bindings.has(person.person_id)) continue;
      const companions = this.companionBindings.get(person.person_id) ?? [];
      for (const dev of unboundD.filter((d) => d.device_type === "audio").sort((a, b) => b.rssi - a.rssi)) {
        if (companions.includes(dev.address) || dev.rssi < -94) continue;
        companions.push(dev.address);
        if (companions.length >= 2) break;
      }
      this.companionBindings.set(person.person_id, companions);
    }
  }

  update(persons: PersonDetection[]): TrackedTarget[] {
    this.tryAutoBind(persons);
    const targets: TrackedTarget[] = [];

    for (const person of persons) {
      const addr = this.bindings.get(person.person_id);
      const dev = addr ? this.devices.get(addr) : undefined;
      let device = null;
      let placement = null;
      if (dev) {
        device = {
          brand: dev.brand, model: dev.model, display_name: dev.display_name,
          device_type: dev.device_type, is_phone: dev.is_phone, likely_body_zone: dev.likely_body_zone,
          icon: dev.icon, confidence: dev.type_confidence, address: dev.address, rssi: dev.rssi,
        };
        placement = inferPlacement(dev.device_type, person.pose, person.left_hand, person.right_hand);
      }

      const companion_devices = (this.companionBindings.get(person.person_id) ?? [])
        .map((a) => this.devices.get(a))
        .filter((d): d is BleDev => !!d && Date.now() / 1000 - d.last_seen < 20)
        .map((d) => ({
          brand: d.brand, model: d.model, display_name: d.display_name, device_type: d.device_type,
          is_phone: d.is_phone, likely_body_zone: d.likely_body_zone, icon: d.icon, confidence: d.type_confidence,
          address: d.address, rssi: d.rssi,
          placement: inferPlacement(d.device_type, person.pose, person.left_hand, person.right_hand),
        }));

      targets.push({
        person_id: person.person_id,
        ble_address: addr ?? null,
        device,
        placement,
        pose: person.pose,
        face: person.face,
        left_hand: person.left_hand,
        right_hand: person.right_hand,
        bbox: person.bbox,
        motion_energy: person.motion_energy,
        rssi: dev?.rssi ?? null,
        bind_method: this.bindMethods.get(person.person_id) ?? "none",
        metrics: person.metrics,
        companion_devices: companion_devices as TrackedTarget["companion_devices"],
      });
    }
    return targets;
  }

  unboundDevices(persons: PersonDetection[]): Array<Record<string, unknown>> {
    const bound = new Set(this.bindings.values());
    for (const addrs of this.companionBindings.values()) addrs.forEach((a) => bound.add(a));
    const now = Date.now() / 1000;
    const primary = persons[0];
    return [...this.devices.values()]
      .filter((d) => !bound.has(d.address) && now - d.last_seen < 25)
      .sort((a, b) => (Number(b.is_phone) - Number(a.is_phone)) || b.rssi - a.rssi)
      .slice(0, 40)
      .map((d) => ({
        address: d.address,
        name: d.display_name,
        brand: d.brand,
        model: d.model,
        display_name: d.display_name,
        rssi: d.rssi,
        device_type: d.device_type,
        is_phone: d.is_phone,
        likely_body_zone: d.likely_body_zone,
        icon: d.icon,
        type_confidence: d.type_confidence,
        placement_hint: primary ? inferPlacement(d.device_type, primary.pose, primary.left_hand, primary.right_hand) : null,
        suggested: primary ? personHoldingPhone(primary.pose, primary.left_hand, primary.right_hand)[0] && (d.is_phone || d.brand === "Apple") : d.is_phone,
      }));
  }

  bindSuggestions(persons: PersonDetection[]): Array<Record<string, unknown>> {
    if (!persons.length || this.bindings.has(persons[0].person_id)) return [];
    const [holding, side] = personHoldingPhone(persons[0].pose, persons[0].left_hand, persons[0].right_hand);
    const bound = new Set(this.bindings.values());
    const now = Date.now() / 1000;
    const picks = [...this.devices.values()]
      .filter((d) => !bound.has(d.address) && now - d.last_seen < 20)
      .sort((a, b) => b.rssi - a.rssi)
      .slice(0, 3);
    return picks.map((d) => ({
      address: d.address,
      display_name: d.display_name,
      brand: d.brand,
      device_type: d.device_type,
      icon: d.icon,
      rssi: d.rssi,
      reason: holding ? `Camera sees phone in ${side} hand — strongest match` : d.is_phone ? "Strongest phone signal nearby" : "Strongest BLE signal nearby",
    }));
  }

  boundSummary(): Array<Record<string, unknown>> {
    const out: Array<Record<string, unknown>> = [];
    for (const [pid, addr] of this.bindings) {
      const d = this.devices.get(addr);
      if (!d) continue;
      out.push({
        person_id: pid, address: addr, brand: d.brand, model: d.model, display_name: d.display_name,
        device_type: d.device_type, is_phone: d.is_phone, icon: d.icon, rssi: d.rssi,
        method: this.bindMethods.get(pid) ?? "unknown",
      });
    }
    return out;
  }
}
