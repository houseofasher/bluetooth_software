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
    enrich_with_gatt_names,
    load_windows_paired_names,
    signals_to_record,
)

PORT = 8765
SCAN_SECONDS = 20
ZERO_RESULT_HINT = (
    "Scan finished with no advertisers. Check: Bluetooth ON, Windows Location ON, "
    "and at least one BLE device nearby and powered on (phone/watch/headphones)."
)

Phase = Literal["idle", "running", "resolving", "completed", "failed"]


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
            return {
                "phase": self.phase,
                "running": self.phase in ("running", "resolving"),
                "error": self.error,
                "devices": device_list,
                "count": len(device_list),
                "startedAt": self.started_at,
                "finishedAt": self.finished_at,
                "zeroResultHint": ZERO_RESULT_HINT if self.phase == "completed" and not device_list else None,
            }

    def begin(self) -> None:
        with self.lock:
            self.phase = "running"
            self.signals = {}
            self.devices = {}
            self.paired_names = load_windows_paired_names()
            self.error = None
            self.stop_flag.clear()
            self.started_at = time.time()
            self.finished_at = None

    def begin_resolve(self) -> None:
        with self.lock:
            self.phase = "resolving"

    def finish(self) -> None:
        with self.lock:
            self.phase = "failed" if self.error else "completed"
            self.finished_at = time.time()

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
            key = device.address
            existing = self.signals.get(key)
            if existing is None:
                existing = DeviceSignals(address=device.address)
                self.signals[key] = existing
            existing.merge(device, advertisement_data, source)
            record = signals_to_record(existing, self.paired_names)
            record["lastSeen"] = int(time.time() * 1000)
            self.devices[key] = record

    def apply_resolved_records(self) -> None:
        with self.lock:
            for key, signals in self.signals.items():
                record = signals_to_record(signals, self.paired_names)
                record["lastSeen"] = int(time.time() * 1000)
                self.devices[key] = record

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


async def resolve_names_phase() -> None:
    STATE.begin_resolve()
    with STATE.lock:
        signals_copy = dict(STATE.signals)
        paired = dict(STATE.paired_names)

    if not STATE.stop_flag.is_set():
        await enrich_with_gatt_names(signals_copy, paired)

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
            await resolve_names_phase()
    except BleakBluetoothNotAvailableError as exc:
        STATE.fail(reason_message(exc.reason))
        return
    except Exception as exc:
        STATE.fail(str(exc))
        return
    finally:
        if STATE.phase in ("running", "resolving"):
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
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
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
    .meta { color: #666; font-size: 0.8rem; display: block; }
    .empty { color: #888; font-style: italic; }
  </style>
</head>
<body>
  <h1>Bluetooth LE scan</h1>
  <div id="health">Checking Bluetooth…</div>
  <div class="row">
    <button id="startBtn" disabled>Start scan</button>
    <button id="stopBtn" disabled>Stop</button>
  </div>
  <div id="status">Idle.</div>
  <div id="hint"></div>
  <ul id="list"><li class="empty">No devices yet.</li></ul>

  <script>
    let pollTimer = null;
    const healthEl = document.getElementById("health");
    const statusEl = document.getElementById("status");
    const hintEl = document.getElementById("hint");
    const listEl = document.getElementById("list");
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");

    const SOURCE_LABELS = {
      broadcast: "advertised",
      paired: "paired",
      gatt: "GATT name",
      inferred: "inferred",
      address: "address only",
    };

    function escapeHtml(s) {
      return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    function render(devices) {
      if (!devices.length) {
        listEl.innerHTML = '<li class="empty">No devices yet.</li>';
        return;
      }
      listEl.innerHTML = devices.map((d) => {
        const src = d.nameSource || "address";
        const badge = `<span class="badge ${escapeHtml(src)}">${escapeHtml(SOURCE_LABELS[src] || src)}</span>`;
        const broadcast = d.broadcastName && d.broadcastName !== d.displayName
          ? `<span class="meta">Advertised as: ${escapeHtml(d.broadcastName)}</span>` : "";
        const mfg = d.manufacturer ? `<span class="meta">Manufacturer: ${escapeHtml(d.manufacturer)}</span>` : "";
        return `
        <li>
          <strong>${escapeHtml(d.displayName || d.name || "(unnamed)")}${badge}</strong>
          ${broadcast}
          ${mfg}
          <span class="meta">RSSI: ${d.rssi ?? "?"} dBm</span>
          <span class="meta">Address: ${escapeHtml(d.id)}</span>
          ${d.uuids?.length ? `<span class="meta">Services: ${d.uuids.map(escapeHtml).join(", ")}</span>` : ""}
        </li>`;
      }).join("");
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
      hintEl.textContent = data.zeroResultHint ?? "";

      if (data.phase === "running") {
        statusEl.textContent = `Scanning… ${data.count} device(s) seen`;
        startBtn.disabled = true;
        stopBtn.disabled = false;
        return;
      }
      if (data.phase === "resolving") {
        statusEl.textContent = `Resolving names… ${data.count} device(s)`;
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

        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/stop":
            STATE.request_stop()
            self._send_json(200, {"ok": True})
            return

        if path == "/api/scan":
            snap = STATE.snapshot()
            if snap["phase"] in ("running", "resolving"):
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
