#!/usr/bin/env python3
"""Local BLE scan server — Windows native Bluetooth via bleak."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from urllib.parse import urlparse

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakBluetoothNotAvailableError, BleakBluetoothNotAvailableReason

from ble_device_naming import (
    DeviceSignals,
    format_mac,
    normalize_mac,
    resolve_name,
)
from ble_enrichment import build_device_record, remember_paired_aliases
from ble_gatt_pull import pull_device_data_sync, pull_devices_sequential
from ble_hop_graph import HOP_GRAPH
from ble_location import SCANNER_LOCATION, reverse_geocode
from ble_paired_windows import load_all_paired_names

PORT = 8765
SCAN_SECONDS = 20
ZERO_RESULT_HINT = (
    "Scan finished with no advertisers. Check: Bluetooth ON, Windows Location ON, "
    "and at least one BLE device nearby and powered on (phone/watch/headphones)."
)

Phase = Literal["idle", "running", "resolving", "pulling", "completed", "failed"]
AUTO_PULL_MAX = 10


def reason_message(reason: BleakBluetoothNotAvailableReason) -> str:
    match reason:
        case BleakBluetoothNotAvailableReason.POWERED_OFF:
            return "Bluetooth is OFF. Turn it on in Settings > Bluetooth & devices."
        case BleakBluetoothNotAvailableReason.DENIED_BY_SYSTEM:
            return "Windows blocked BLE scanning. Enable Location services and try again."
        case BleakBluetoothNotAvailableReason.DENIED_BY_USER:
            return "Bluetooth access denied. Allow Bluetooth for this app in Windows privacy settings."
        case BleakBluetoothNotAvailableReason.NO_BLUETOOTH:
            return "No Bluetooth adapter found on this PC."
        case BleakBluetoothNotAvailableReason.NO_BLE_CENTRAL_ROLE:
            return "This Bluetooth adapter does not support BLE central (scan) role."
        case _:
            return "Bluetooth is not available for scanning."


@dataclass
class ScanState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    phase: Phase = "idle"
    signals: dict[str, DeviceSignals] = field(default_factory=dict)
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    paired_names: dict[str, str] = field(default_factory=dict)
    pulled_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: str | None = None
    stop_flag: threading.Event = field(default_factory=threading.Event)
    started_at: float | None = None
    finished_at: float | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            device_list = sorted(
                self.devices.values(),
                key=lambda d: d.get("rssi") if d.get("rssi") is not None else -999,
                reverse=True,
            )
            hop_graph = HOP_GRAPH.snapshot()
            depth_map = {
                normalize_mac(n["address"]): n.get("hopDepth")
                for n in hop_graph.get("nodes", [])
                if n.get("address")
            }
            for d in device_list:
                mac = normalize_mac(d.get("macAddress") or d.get("id", ""))
                d["hopDepth"] = depth_map.get(mac)
            return {
                "phase": self.phase,
                "running": self.phase in ("running", "resolving", "pulling"),
                "error": self.error,
                "devices": device_list,
                "count": len(device_list),
                "scannerLocation": SCANNER_LOCATION.snapshot(),
                "pairedDevices": [
                    {"mac": format_mac(k), "name": v}
                    for k, v in sorted(self.paired_names.items(), key=lambda x: x[1])
                ],
                "startedAt": self.started_at,
                "finishedAt": self.finished_at,
                "zeroResultHint": ZERO_RESULT_HINT if self.phase == "completed" and not device_list else None,
                "hopGraph": hop_graph,
            }

    def begin(self) -> None:
        with self.lock:
            self.phase = "running"
            self.signals = {}
            self.devices = {}
            self.pulled_data = {}
            self.paired_names = load_all_paired_names()
            self.error = None
            self.stop_flag.clear()
            self.started_at = time.time()
            self.finished_at = None

    def begin_resolve(self) -> None:
        with self.lock:
            self.phase = "resolving"

    def begin_pull(self) -> None:
        with self.lock:
            self.phase = "pulling"

    def finish(self) -> None:
        device_list: list[dict[str, Any]] = []
        with self.lock:
            self.phase = "failed" if self.error else "completed"
            self.finished_at = time.time()
            if self.phase == "completed":
                device_list = list(self.devices.values())
        if device_list:
            HOP_GRAPH.ingest_pc_scan(device_list)

    def fail(self, message: str) -> None:
        with self.lock:
            self.error = message
            self.phase = "failed"
            self.finished_at = time.time()

    def merge_advertisement(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
        source: str,
    ) -> None:
        with self.lock:
            key = format_mac(device.address)
            existing = self.signals.get(key)
            if existing is None:
                existing = DeviceSignals(address=device.address)
                self.signals[key] = existing
            existing.merge(device, advertisement_data, source)
            pulled = self.pulled_data.get(key)
            record = build_device_record(existing, self.paired_names, SCANNER_LOCATION, pulled)
            record["lastSeen"] = int(time.time() * 1000)
            self.devices[key] = record

    def apply_resolved_records(self) -> None:
        with self.lock:
            for key, signals in self.signals.items():
                pulled = self.pulled_data.get(key)
                record = build_device_record(signals, self.paired_names, SCANNER_LOCATION, pulled)
                record["lastSeen"] = int(time.time() * 1000)
                self.devices[key] = record

    def set_pulled_data(self, address: str, payload: dict[str, Any]) -> None:
        key = format_mac(address)
        with self.lock:
            self.pulled_data[key] = payload
            signals = self.signals.get(key)
            if signals:
                data = payload.get("data") or {}
                if data.get("osDeviceName"):
                    signals.os_name = str(data["osDeviceName"])
                    signals.gatt_name = signals.os_name
                remember_paired_aliases(self.paired_names, key, payload)
                record = build_device_record(signals, self.paired_names, SCANNER_LOCATION, payload)
                record["lastSeen"] = int(time.time() * 1000)
                self.devices[key] = record

    def has_device(self, address: str) -> bool:
        key = format_mac(address)
        with self.lock:
            return key in self.signals or key in self.devices

    def request_stop(self) -> None:
        self.stop_flag.set()


STATE = ScanState()


async def check_bluetooth_ready() -> dict[str, Any]:
    try:
        scanner = BleakScanner(scanning_mode="active")
        await scanner.start()
        await scanner.stop()
        return {"ready": True, "message": "Bluetooth is on and ready to scan."}
    except BleakBluetoothNotAvailableError as exc:
        return {
            "ready": False,
            "message": reason_message(exc.reason),
            "reason": exc.reason.name,
        }
    except Exception as exc:
        return {"ready": False, "message": str(exc), "reason": "UNKNOWN"}


def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData) -> None:
    STATE.merge_advertisement(device, advertisement_data, "live")


async def merge_discover_results(timeout: float) -> None:
    discovered = await BleakScanner.discover(timeout=timeout, scanning_mode="active", return_adv=True)
    for device, adv in discovered.values():
        STATE.merge_advertisement(device, adv, "discover")


async def resolve_and_pull_phase() -> None:
    STATE.begin_resolve()
    with STATE.lock:
        signals_copy = dict(STATE.signals)
        paired = dict(STATE.paired_names)

    if STATE.stop_flag.is_set():
        with STATE.lock:
            STATE.signals = signals_copy
        STATE.apply_resolved_records()
        return

    # Pull data from strongest devices — sequential connect required on Windows.
    ranked = sorted(
        signals_copy.values(),
        key=lambda s: s.rssi if s.rssi is not None else -999,
        reverse=True,
    )
    unnamed = [
        s for s in ranked
        if resolve_name(s, paired).name_source in ("inferred", "address")
    ]
    targets = unnamed[:AUTO_PULL_MAX] if unnamed else ranked[:AUTO_PULL_MAX]

    if targets:
        STATE.begin_pull()

        def on_each(address: str, result: dict[str, Any]) -> None:
            key = format_mac(address)
            if key in signals_copy:
                data = result.get("data") or {}
                if data.get("osDeviceName"):
                    signals_copy[key].os_name = str(data["osDeviceName"])
                    signals_copy[key].gatt_name = signals_copy[key].os_name
                elif data.get("deviceName"):
                    signals_copy[key].gatt_name = str(data["deviceName"])
            with STATE.lock:
                remember_paired_aliases(STATE.paired_names, key, result)
            STATE.set_pulled_data(key, result)

        await pull_devices_sequential([s.address for s in targets], on_each=on_each)

    with STATE.lock:
        STATE.signals = signals_copy
    STATE.apply_resolved_records()


async def run_scan(duration: float) -> None:
    STATE.begin()
    scanner = BleakScanner(detection_callback=detection_callback, scanning_mode="active")

    try:
        await scanner.start()
        deadline = time.monotonic() + max(duration - 5.0, 5.0)
        while time.monotonic() < deadline:
            if STATE.stop_flag.is_set():
                break
            await asyncio.sleep(0.2)
        await scanner.stop()

        if not STATE.stop_flag.is_set():
            await merge_discover_results(timeout=3.0)
            await resolve_and_pull_phase()
    except BleakBluetoothNotAvailableError as exc:
        STATE.fail(reason_message(exc.reason))
        return
    except Exception as exc:
        STATE.fail(str(exc))
        return
    finally:
        if STATE.phase in ("running", "resolving", "pulling"):
            STATE.finish()


def run_scan_in_thread(duration: float) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_scan(duration))
    finally:
        loop.close()


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>BLE Scan</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; max-width: 820px; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.25rem; }
    .row { display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }
    button { padding: 0.5rem 1rem; cursor: pointer; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    #status { color: #555; margin-bottom: 0.5rem; min-height: 1.25rem; }
    #health { font-size: 0.85rem; margin-bottom: 0.75rem; padding: 0.5rem 0.75rem; border-radius: 6px; }
    #health.ok { background: #eef9ee; color: #1a5c1a; }
    #health.bad { background: #fff0f0; color: #8a1f1f; }
    #hint { color: #666; font-size: 0.85rem; margin-bottom: 0.75rem; }
    #list { list-style: none; padding: 0; margin: 0; }
    #list li {
      border: 1px solid #ddd; border-radius: 6px; padding: 0.6rem 0.75rem;
      margin-bottom: 0.5rem; font-size: 0.9rem;
    }
    #list li strong { display: block; }
    .badge {
      display: inline-block; font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
      padding: 0.1rem 0.35rem; border-radius: 4px; margin-left: 0.35rem; vertical-align: middle;
      background: #eee; color: #555;
    }
    .badge.broadcast { background: #e8f4e8; color: #1a5c1a; }
    .badge.paired { background: #e8eef9; color: #1a3d8a; }
    .badge.gatt { background: #f3e8f9; color: #5c1a8a; }
    .badge.inferred { background: #fff6e6; color: #8a5a1a; }
    .badge.immediate { background: #e8f4e8; color: #1a5c1a; }
    .badge.near { background: #e8eef9; color: #1a3d8a; }
    .badge.far { background: #f5f5f5; color: #666; }
    .pull-box { margin-top: 0.5rem; padding: 0.5rem; background: #f8f9fa; border-radius: 4px; font-size: 0.78rem; }
    .pull-box code { word-break: break-all; }
    .legend { font-size: 0.82rem; color: #444; background: #f8f9fa; border: 1px solid #e5e5e5; border-radius: 6px; padding: 0.6rem 0.75rem; margin-bottom: 1rem; }
    .legend dt { font-weight: 600; margin-top: 0.35rem; }
    .legend dd { margin: 0.15rem 0 0 0; color: #666; }
    .meta { color: #666; font-size: 0.8rem; display: block; }
    .empty { color: #888; font-style: italic; }
  </style>
</head>
<body>
  <h1>Bluetooth LE scan</h1>
  <div id="health">Checking Bluetooth…</div>
  <div id="location" class="meta" style="margin-bottom:0.75rem;padding:0.5rem 0.75rem;border:1px solid #ddd;border-radius:6px;">
    Location not set — <button id="locBtn" type="button">Share my location</button> (for home street address)
  </div>
  <div id="paired" class="meta" style="margin-bottom:0.75rem;"></div>
  <dl class="legend">
    <dt>Device name</dt>
    <dd>Pulled automatically from the device when possible (Bluetooth name, model, or paired name).</dd>
    <dt>RSSI (signal strength)</dt>
    <dd>Measured in dBm. <strong>Closer to 0 = stronger.</strong> Example: -45 = very close, -80 = farther away. Walls and interference affect this.</dd>
    <dt>Bluetooth MAC</dt>
    <dd>A hardware ID like <code>AA:BB:CC:DD:EE:FF</code> — <strong>not</strong> a home street address. Street address comes from your shared location.</dd>
  </dl>
  <div class="row">
    <button id="startBtn" disabled>Start scan</button>
    <button id="stopBtn" disabled>Stop</button>
  </div>
  <div id="status">Idle.</div>
  <div id="hint"></div>
  <section id="hopSection" style="margin:1.25rem 0;padding:0.75rem;border:1px solid #ddd;border-radius:8px;">
    <h2 style="font-size:1rem;margin:0 0 0.5rem;">Hop map (domino discovery)</h2>
    <p class="meta" id="hopNote">Each scanner reports what it hears. When a heard device is also a hop scanner, the chain continues.</p>
    <div id="hopStats" class="meta"></div>
    <ul id="hopChains" style="padding-left:1.2rem;font-size:0.85rem;"></ul>
    <pre id="hopMermaid" style="font-size:0.75rem;overflow:auto;background:#f8f9fa;padding:0.5rem;border-radius:4px;"></pre>
  </section>
  <ul id="list"><li class="empty">No devices yet.</li></ul>

  <script>
    let pollTimer = null;
    const healthEl = document.getElementById("health");
    const statusEl = document.getElementById("status");
    const hintEl = document.getElementById("hint");
    const listEl = document.getElementById("list");
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const locEl = document.getElementById("location");
    const locBtn = document.getElementById("locBtn");
    const pairedEl = document.getElementById("paired");
    const hopStats = document.getElementById("hopStats");
    const hopChains = document.getElementById("hopChains");
    const hopMermaid = document.getElementById("hopMermaid");

    const SOURCE_LABELS = {
      broadcast: "advertised",
      paired: "paired",
      gatt: "GATT name",
      inferred: "inferred",
      address: "address only",
    };

    const ZONE_LABELS = { immediate: "same room", near: "nearby", far: "far", unknown: "?" };
    const PULL_LABELS = {
      deviceName: "Device name",
      batteryLevel: "Battery %",
      manufacturerName: "Manufacturer",
      modelNumber: "Model",
      serialNumber: "Serial",
      firmwareRevision: "Firmware",
      hardwareRevision: "Hardware",
    };

    function escapeHtml(s) {
      return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    function renderHopGraph(hop) {
      if (!hop) return;
      hopStats.textContent = `${hop.scannerCount} scanner(s), ${hop.nodeCount} node(s), max hop depth ${hop.maxHopDepth} — ${hop.note || ""}`;
      if (!hop.chains?.length) {
        hopChains.innerHTML = "<li>No multi-hop chains yet. Run hop_reporter.py on another device to extend the domino map.</li>";
      } else {
        hopChains.innerHTML = hop.chains.map((c) =>
          `<li><strong>${escapeHtml(c.target)}</strong> — ${c.hopDepth} hop(s): ${c.path.map(escapeHtml).join(" → ")}</li>`
        ).join("");
      }
      const lines = ["flowchart LR", "  root[This PC]"];
      for (const s of hop.scanners || []) {
        if (!s.isRoot) lines.push(`  ${s.nodeId.replace(/-/g,"_")}[${s.label}]`);
      }
      for (const e of (hop.edges || []).slice(0, 24)) {
        const a = e.from.replace(/[^a-zA-Z0-9_]/g, "_");
        const b = e.to.replace(/[^a-zA-Z0-9_]/g, "_");
        lines.push(`  ${a} --> ${b}`);
      }
      hopMermaid.textContent = lines.join("\\n");
    }

    function render(devices) {
      if (!devices.length) {
        listEl.innerHTML = '<li class="empty">No devices yet.</li>';
        return;
      }
      listEl.innerHTML = devices.map((d) => {
        const src = d.nameSource || "address";
        const badge = `<span class="badge ${escapeHtml(src)}">${escapeHtml(SOURCE_LABELS[src] || src)}</span>`;
        const zone = d.proximityZone || "unknown";
        const zoneBadge = `<span class="badge ${escapeHtml(zone)}">${escapeHtml(ZONE_LABELS[zone] || zone)}</span>`;
        const dist = d.distanceLabel
          ? `<span class="meta"><strong>~${escapeHtml(d.distanceLabel)} away</strong> ${zoneBadge}</span>
             <span class="meta" title="${escapeHtml(d.rssiNote || "")}">RSSI: ${d.rssi ?? "?"} dBm — ${escapeHtml(d.rssiHuman || "signal unknown")}</span>`
          : `<span class="meta">${escapeHtml(d.rssiHuman || "")}</span>`;
        const street = d.location?.coLocated && d.location.estimatedAddressShort
          ? `<span class="meta"><strong>Street address (your location):</strong> ${escapeHtml(d.location.estimatedAddressShort)}</span>`
          : "";
        const locNote = d.location?.contextNote
          ? `<span class="meta">${escapeHtml(d.location.contextNote)}</span>` : "";
        const mfg = d.manufacturer ? `<span class="meta">Manufacturer (advertised): ${escapeHtml(d.manufacturer)}</span>` : "";
        let pull = "";
        if (d.pulledData?.data && Object.keys(d.pulledData.data).length) {
          pull = `<div class="pull-box"><strong>Data pulled to this PC:</strong><br>${Object.entries(d.pulledData.data).map(([k,v]) => {
            const label = PULL_LABELS[k] || k;
            const val = k === "batteryLevel" ? `${v}%` : v;
            return `${escapeHtml(label)}: <code>${escapeHtml(val)}</code>`;
          }).join("<br>")}</div>`;
        } else if (d.pullStatus === "pending") {
          pull = `<div class="pull-box">Waiting to connect and pull device data…</div>`;
        } else if (d.pullStatus === "failed" && d.pulledData?.errors?.length) {
          pull = `<div class="pull-box">Could not pull data: ${escapeHtml(d.pulledData.errors[0])} — device may not allow connections.</div>`;
        } else if (d.pullStatus === "empty") {
          pull = `<div class="pull-box">Connected but no readable data exposed by this device.</div>`;
        }
        const pullBtn = `<button type="button" class="pullBtn" data-id="${escapeHtml(d.id)}">Retry pull</button>`;
        const hopBadge = d.hopDepth != null && d.hopDepth > 0
          ? `<span class="badge near">${d.hopDepth} hop(s) from PC</span>` : "";
        return `
        <li>
          <strong>${escapeHtml(d.displayName || d.name || "Unknown device")}${badge}${hopBadge}</strong>
          ${dist}
          ${street}
          ${locNote}
          ${mfg}
          <span class="meta">Bluetooth MAC: <code>${escapeHtml(d.macAddress || d.id)}</code> — ${escapeHtml(d.macNote || "hardware ID, not street address")}</span>
          ${d.uuids?.length ? `<span class="meta">Services: ${d.uuids.map(escapeHtml).join(", ")}</span>` : ""}
          ${pull}
          ${pullBtn}
        </li>`;
      }).join("");
      document.querySelectorAll(".pullBtn").forEach((btn) => {
        btn.addEventListener("click", () => pullData(btn.dataset.id));
      });
    }

    async function shareLocation() {
      if (!navigator.geolocation) {
        locEl.textContent = "Geolocation not supported in this browser.";
        return;
      }
      locEl.textContent = "Requesting location permission…";
      navigator.geolocation.getCurrentPosition(async (pos) => {
        const res = await fetch("/api/location", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            accuracyMeters: pos.coords.accuracy,
          }),
        });
        const data = await res.json();
        if (data.addressShort) {
          locEl.innerHTML = `<strong>Your location:</strong> ${escapeHtml(data.addressShort)} <span class="meta">(used to estimate if nearby devices are at your home)</span>`;
        } else {
          locEl.textContent = data.message || "Location saved.";
        }
      }, (err) => {
        locEl.textContent = `Location denied: ${err.message}`;
      }, { enableHighAccuracy: true, timeout: 15000 });
    }

    async function pullData(address) {
      statusEl.textContent = `Pulling GATT data from ${address}…`;
      const res = await fetch("/api/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address }),
      });
      const data = await res.json();
      if (!res.ok) {
        statusEl.textContent = data.error || "Pull failed.";
        return;
      }
      statusEl.textContent = data.ok ? `Pulled data from ${address}` : `No readable data from ${address}`;
      await poll();
    }

    async function refreshHealth() {
      try {
        const res = await fetch("/api/health");
        const data = await res.json();
        healthEl.className = data.ready ? "ok" : "bad";
        healthEl.textContent = data.message;
        startBtn.disabled = !data.ready || pollTimer !== null;
        return data.ready;
      } catch {
        healthEl.className = "bad";
        healthEl.textContent = "Scan server not reachable. Run: python ble-scan-server.py";
        startBtn.disabled = true;
        return false;
      }
    }

    function applySnapshot(data) {
      render(data.devices ?? []);
      if (data.scannerLocation?.addressShort) {
        locEl.innerHTML = `<strong>Your location:</strong> ${escapeHtml(data.scannerLocation.addressShort)}`;
      }
      if (data.pairedDevices?.length) {
        pairedEl.innerHTML = `<strong>Paired on this PC:</strong> ${data.pairedDevices.map((p) => escapeHtml(p.name)).join(", ")} — names appear after connect phase if BLE uses a random MAC while scanning.`;
      }
      renderHopGraph(data.hopGraph);
      hintEl.textContent = data.zeroResultHint ?? "";

      if (data.phase === "running") {
        statusEl.textContent = `Scanning… ${data.count} device(s) seen`;
        startBtn.disabled = true;
        stopBtn.disabled = false;
        return;
      }
      if (data.phase === "resolving") {
        statusEl.textContent = `Resolving device names… ${data.count} device(s)`;
        startBtn.disabled = true;
        stopBtn.disabled = false;
        return;
      }
      if (data.phase === "pulling") {
        statusEl.textContent = `Connecting & pulling data from devices… ${data.count} found so far`;
        startBtn.disabled = true;
        stopBtn.disabled = false;
        return;
      }

      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }

      startBtn.disabled = false;
      stopBtn.disabled = true;

      if (data.phase === "failed") {
        statusEl.textContent = data.error || "Scan failed.";
      } else if (data.phase === "completed") {
        statusEl.textContent = data.count
          ? `Done. ${data.count} device(s) found.`
          : "Done. 0 devices found.";
      }
    }

    async function poll() {
      const res = await fetch("/api/devices");
      const data = await res.json();
      applySnapshot(data);
    }

    async function startScan() {
      hintEl.textContent = "";
      statusEl.textContent = "Starting scan…";
      startBtn.disabled = true;

      const res = await fetch("/api/scan", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        statusEl.textContent = data.error || "Could not start scan.";
        await refreshHealth();
        return;
      }

      statusEl.textContent = `Scanning up to ${data.duration}s…`;
      stopBtn.disabled = false;
      pollTimer = setInterval(poll, 400);
      poll();
    }

    async function stopScan() {
      await fetch("/api/stop", { method: "POST" }).catch(() => {});
      await poll();
    }

    startBtn.addEventListener("click", startScan);
    stopBtn.addEventListener("click", stopScan);
    locBtn.addEventListener("click", shareLocation);
    refreshHealth();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        pass

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path in ("/", "/ble-scan.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/health":
            ready = asyncio.run(check_bluetooth_ready())
            self._send_json(200, ready)
            return

        if path == "/api/devices":
            self._send_json(200, STATE.snapshot())
            return

        if path == "/api/location":
            self._send_json(200, SCANNER_LOCATION.snapshot())
            return

        if path == "/api/hop/graph":
            self._send_json(200, HOP_GRAPH.snapshot())
            return

        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/hop/report":
            payload = self._read_json()
            try:
                HOP_GRAPH.register_scanner_report(payload)
                self._send_json(200, {"ok": True, "hopGraph": HOP_GRAPH.snapshot()})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            return

        if path == "/api/location":
            payload = self._read_json()
            lat = payload.get("latitude")
            lon = payload.get("longitude")
            if lat is None or lon is None:
                self._send_json(400, {"error": "latitude and longitude required"})
                return
            SCANNER_LOCATION.set_coords(
                float(lat),
                float(lon),
                payload.get("accuracyMeters"),
                payload.get("source", "browser"),
            )
            try:
                full, short = reverse_geocode(float(lat), float(lon))
                SCANNER_LOCATION.set_address(full, short)
                self._send_json(200, {**SCANNER_LOCATION.snapshot(), "message": "Location updated"})
            except Exception as exc:
                self._send_json(200, {
                    **SCANNER_LOCATION.snapshot(),
                    "message": f"Coords saved; address lookup failed: {exc}",
                })
            STATE.apply_resolved_records()
            return

        if path == "/api/pull":
            payload = self._read_json()
            address = payload.get("address")
            if not address:
                self._send_json(400, {"error": "address required"})
                return
            if not STATE.has_device(address):
                self._send_json(404, {"error": "Device not in last scan — scan first"})
                return
            result = pull_device_data_sync(address)
            STATE.set_pulled_data(address, result)
            self._send_json(200, result)
            return

        if path == "/api/stop":
            STATE.request_stop()
            self._send_json(200, {"ok": True})
            return

        if path == "/api/scan":
            snap = STATE.snapshot()
            if snap["phase"] in ("running", "resolving", "pulling"):
                self._send_json(409, {"error": "Scan already running"})
                return

            ready = asyncio.run(check_bluetooth_ready())
            if not ready["ready"]:
                self._send_json(503, {"error": ready["message"], "reason": ready.get("reason")})
                return

            threading.Thread(
                target=run_scan_in_thread,
                args=(SCAN_SECONDS,),
                daemon=True,
            ).start()
            self._send_json(200, {"ok": True, "duration": SCAN_SECONDS})
            return

        self.send_error(404)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"BLE scan server: http://127.0.0.1:{PORT}/")
    print("Open the page — names resolve from broadcast, paired, GATT, and inference.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
