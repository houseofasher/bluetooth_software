#!/usr/bin/env python3
"""Local BLE scan server — Windows native Bluetooth via bleak."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

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
from ble_tactical import SCENARIOS, TACTICAL, mission_label
from ble_sci_fi import SCI_FI, generate_mission_brief
from ble_theory import (
    GATT_THEORIES as PULL_THEORY_CATALOG,
    TACTICAL_THEORIES as THEORY_CATALOG,
    security_summary,
    theory_snapshot,
)
from ble_screen_relay import recommend_relay_path, screen_relay_snapshot

PORT = 8765
DISCOVER_ON_STOP_SEC = 3.0
HOP_INGEST_INTERVAL = 5.0  # push live devices into domino hop graph while scanning
AUTO_PULL_INTERVAL = 45.0  # background GATT exfil attempt for strongest unpulled device
PERSISTENT_SCAN = True  # never halt radio for device-count caps or post-scan phases
ZERO_RESULT_HINT = (
    "No advertisers yet — sweep is still running. Check Bluetooth ON, Windows Location ON, "
    "and BLE devices nearby. Hop chains update every few seconds as companions report in."
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
    sync_flag: threading.Event = field(default_factory=threading.Event)
    scan_shutdown: threading.Event = field(default_factory=threading.Event)
    started_at: float | None = None
    last_hop_ingest_at: float | None = None
    hop_ingest_count: int = 0
    last_hop_depth_logged: int = 0

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            hop_graph = HOP_GRAPH.snapshot()
            depth_map = {
                normalize_mac(n["address"]): n.get("hopDepth")
                for n in hop_graph.get("nodes", [])
                if n.get("address")
            }
            device_list = []
            for d in self.devices.values():
                mac = normalize_mac(d.get("macAddress") or d.get("id", ""))
                d["hopDepth"] = depth_map.get(mac)
                device_list.append(d)
            device_list.sort(
                key=lambda d: d.get("rssi") if d.get("rssi") is not None else -999,
                reverse=True,
            )
            TACTICAL.on_scan_tick(len(device_list), device_list, hop_graph)
            tactical = TACTICAL.snapshot(self.phase, hop_graph, device_list)
            snap = {
                "phase": self.phase,
                "missionLabel": mission_label(self.phase),
                "running": self.phase in ("running", "resolving", "pulling"),
                "persistent": PERSISTENT_SCAN,
                "hopIngestInterval": HOP_INGEST_INTERVAL,
                "lastHopIngestAt": self.last_hop_ingest_at,
                "hopIngestCount": self.hop_ingest_count,
                "error": self.error,
                "devices": device_list,
                "count": len(device_list),
                "scannerLocation": SCANNER_LOCATION.snapshot(),
                "pairedDevices": [
                    {"mac": format_mac(k), "name": v}
                    for k, v in sorted(self.paired_names.items(), key=lambda x: x[1])
                ],
                "startedAt": self.started_at,
                "zeroResultHint": ZERO_RESULT_HINT if self.phase == "running" and not device_list else None,
                "hopGraph": hop_graph,
                "tactical": tactical,
            }
            TACTICAL.record_replay(snap)
            return snap

    def begin(self) -> None:
        with self.lock:
            if self.phase == "running":
                return
            self.phase = "running"
            self.signals = {}
            self.devices = {}
            self.pulled_data = {}
            self.paired_names = load_all_paired_names()
            self.error = None
            self.sync_flag.clear()
            self.started_at = time.time()
            self.last_hop_ingest_at = None
            self.hop_ingest_count = 0
        TACTICAL.reset_mission()
        TACTICAL.on_phase_change("running")

    def ingest_hop_live(self) -> int:
        """Feed current device snapshot into domino hop graph without stopping sweep."""
        with self.lock:
            device_list = list(self.devices.values())
            self.last_hop_ingest_at = time.time()
        if not device_list:
            return 0
        loc = SCANNER_LOCATION.snapshot()
        HOP_GRAPH.ingest_pc_scan(
            device_list,
            latitude=loc.get("latitude"),
            longitude=loc.get("longitude"),
            accuracy_meters=loc.get("accuracyMeters"),
        )
        with self.lock:
            self.hop_ingest_count += 1
        max_depth = HOP_GRAPH.snapshot().get("maxHopDepth", 0)
        with self.lock:
            if max_depth > self.last_hop_depth_logged:
                self.last_hop_depth_logged = max_depth
                TACTICAL.log(
                    "hop",
                    f"DOMINO CHAIN · depth {max_depth} · {len(device_list)} contacts on root scanner",
                    {"count": len(device_list), "maxHopDepth": max_depth},
                )
        return len(device_list)

    def begin_resolve(self) -> None:
        with self.lock:
            self.phase = "resolving"
        TACTICAL.on_phase_change("resolving")

    def begin_pull(self) -> None:
        with self.lock:
            self.phase = "pulling"
        TACTICAL.on_phase_change("pulling")

    def finish(self) -> None:
        """Only used on radio failure — persistent sweep does not call this on a timer."""
        device_list: list[dict[str, Any]] = []
        with self.lock:
            self.phase = "failed" if self.error else "completed"
            if self.phase == "completed":
                device_list = list(self.devices.values())
        TACTICAL.on_phase_change(self.phase)
        if device_list:
            loc = SCANNER_LOCATION.snapshot()
            HOP_GRAPH.ingest_pc_scan(
                device_list,
                latitude=loc.get("latitude"),
                longitude=loc.get("longitude"),
                accuracy_meters=loc.get("accuracyMeters"),
            )

    def fail(self, message: str) -> None:
        with self.lock:
            self.error = message
            self.phase = "failed"

    def request_sync(self) -> None:
        """Soft sync — refresh names / hop graph without stopping the radio."""
        self.sync_flag.set()

    def merge_advertisement(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
        source: str,
    ) -> None:
        hop_graph = HOP_GRAPH.snapshot()
        depth_map = {
            normalize_mac(n["address"]): n.get("hopDepth")
            for n in hop_graph.get("nodes", [])
            if n.get("address")
        }
        with self.lock:
            key = format_mac(device.address)
            existing = self.signals.get(key)
            old_name = self.devices.get(key, {}).get("displayName") if key in self.devices else None
            if existing is None:
                existing = DeviceSignals(address=device.address)
                self.signals[key] = existing
            existing.merge(device, advertisement_data, source)
            pulled = self.pulled_data.get(key)
            hop_depth = depth_map.get(normalize_mac(key))
            record = build_device_record(
                existing, self.paired_names, SCANNER_LOCATION, pulled, hop_depth, hop_graph
            )
            record["lastSeen"] = int(time.time() * 1000)
            self.devices[key] = record
            if old_name and old_name != record.get("displayName"):
                TACTICAL.on_name_resolved(key, old_name, record["displayName"], record.get("nameSource", ""))

    def apply_resolved_records(self) -> None:
        hop_graph = HOP_GRAPH.snapshot()
        depth_map = {
            normalize_mac(n["address"]): n.get("hopDepth")
            for n in hop_graph.get("nodes", [])
            if n.get("address")
        }
        with self.lock:
            for key, signals in self.signals.items():
                pulled = self.pulled_data.get(key)
                hop_depth = depth_map.get(normalize_mac(key))
                record = build_device_record(
                    signals, self.paired_names, SCANNER_LOCATION, pulled, hop_depth, hop_graph
                )
                record["lastSeen"] = int(time.time() * 1000)
                self.devices[key] = record

    def set_pulled_data(self, address: str, payload: dict[str, Any]) -> None:
        key = format_mac(address)
        hop_graph = HOP_GRAPH.snapshot()
        depth_map = {
            normalize_mac(n["address"]): n.get("hopDepth")
            for n in hop_graph.get("nodes", [])
            if n.get("address")
        }
        with self.lock:
            self.pulled_data[key] = payload
            signals = self.signals.get(key)
            if signals:
                data = payload.get("data") or {}
                if data.get("osDeviceName"):
                    signals.os_name = str(data["osDeviceName"])
                    signals.gatt_name = signals.os_name
                remember_paired_aliases(self.paired_names, key, payload)
                hop_depth = depth_map.get(normalize_mac(key))
                record = build_device_record(
                    signals, self.paired_names, SCANNER_LOCATION, payload, hop_depth, hop_graph
                )
                record["lastSeen"] = int(time.time() * 1000)
                self.devices[key] = record
                TACTICAL.log("exfil", f"INTEL PULLED · {record.get('displayName', key)}", {"mac": key})

    def has_device(self, address: str) -> bool:
        key = format_mac(address)
        with self.lock:
            return key in self.signals or key in self.devices

    def request_stop(self) -> None:
        """Legacy alias — persistent mode treats stop as hop sync, not radio off."""
        self.request_sync()


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
    scenario = TACTICAL.current_scenario()
    auto_pull_max = int(scenario.get("autoPullMax", AUTO_PULL_MAX))
    gatt_on_stop = bool(scenario.get("gattOnStop", True))

    STATE.begin_resolve()
    with STATE.lock:
        signals_copy = dict(STATE.signals)
        paired = dict(STATE.paired_names)

    if STATE.sync_flag.is_set():
        with STATE.lock:
            STATE.signals = signals_copy
        STATE.apply_resolved_records()
        return

    if not gatt_on_stop or auto_pull_max <= 0:
        with STATE.lock:
            STATE.signals = signals_copy
        STATE.apply_resolved_records()
        TACTICAL.log("observe", "Silent observe — no GATT exfiltration")
        return

    ranked = sorted(
        signals_copy.values(),
        key=lambda s: s.rssi if s.rssi is not None else -999,
        reverse=True,
    )
    unnamed = [
        s for s in ranked
        if resolve_name(s, paired).name_source in ("inferred", "address")
    ]
    targets = unnamed[:auto_pull_max] if unnamed else ranked[:auto_pull_max]

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


async def run_persistent_scan() -> None:
    """Sweep forever; domino hop graph ingests live device list on an interval."""
    STATE.begin()
    scanner = BleakScanner(detection_callback=detection_callback, scanning_mode="active")
    last_hop = 0.0
    last_auto_pull = 0.0

    def background_pull_batch(max_devices: int = 2) -> None:
        snap = STATE.snapshot()
        ranked = sorted(
            snap.get("devices", []),
            key=lambda d: d.get("rssi") if d.get("rssi") is not None else -999,
            reverse=True,
        )
        targets = [d for d in ranked if d.get("pullStatus") in ("pending", "failed")][:max_devices]
        if not targets and ranked:
            targets = ranked[:1]
        for d in targets:
            addr = d.get("id") or d.get("macAddress")
            if not addr:
                continue
            try:
                result = pull_device_data_sync(addr)
                STATE.set_pulled_data(addr, result)
                TACTICAL.log(
                    "exfil",
                    f"GATT ATLAS · {d.get('displayName', addr)} · tier {result.get('exfilTier')}",
                    {"mac": addr, "tier": result.get("exfilTier")},
                )
            except Exception as exc:
                TACTICAL.log("exfil", f"Pull failed · {addr}: {exc}", {"mac": addr})

    try:
        await scanner.start()
        TACTICAL.log("hop", "CONTINUOUS SWEEP — domino hop ingest active")

        while not STATE.scan_shutdown.is_set():
            now = time.time()
            if now - last_hop >= HOP_INGEST_INTERVAL:
                STATE.ingest_hop_live()
                last_hop = now

            if now - last_auto_pull >= AUTO_PULL_INTERVAL:
                last_auto_pull = now
                threading.Thread(target=background_pull_batch, kwargs={"max_devices": 1}, daemon=True).start()

            if STATE.sync_flag.is_set():
                STATE.sync_flag.clear()
                STATE.apply_resolved_records()
                STATE.ingest_hop_live()
                threading.Thread(target=background_pull_batch, kwargs={"max_devices": 3}, daemon=True).start()
                TACTICAL.log("hop", "Hop sync + GATT exfil queued — sweep continues")

            await asyncio.sleep(0.25)
    except BleakBluetoothNotAvailableError as exc:
        STATE.fail(reason_message(exc.reason))
    except Exception as exc:
        STATE.fail(str(exc))
    finally:
        try:
            await scanner.stop()
        except Exception:
            pass
        if STATE.phase == "running":
            STATE.fail("Scanner stopped unexpectedly")


async def run_scan() -> None:
    """Backward-compatible entry — persistent mode ignores one-shot stop phases."""
    if PERSISTENT_SCAN:
        await run_persistent_scan()
        return

    STATE.begin()
    scanner = BleakScanner(detection_callback=detection_callback, scanning_mode="active")

    try:
        await scanner.start()
        while not STATE.scan_shutdown.is_set() and not STATE.sync_flag.is_set():
            await asyncio.sleep(0.2)
        await scanner.stop()

        await merge_discover_results(timeout=DISCOVER_ON_STOP_SEC)
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


def run_scan_in_thread() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_scan())
    finally:
        loop.close()


_SCAN_THREAD: threading.Thread | None = None
_SCAN_THREAD_LOCK = threading.Lock()


def ensure_scan_thread() -> bool:
    """Start the persistent BLE sweep thread once (idempotent)."""
    global _SCAN_THREAD
    with _SCAN_THREAD_LOCK:
        if _SCAN_THREAD is not None and _SCAN_THREAD.is_alive():
            return False
        snap = STATE.snapshot()
        if snap["phase"] == "running":
            return False
        _SCAN_THREAD = threading.Thread(target=run_scan_in_thread, daemon=True, name="ble-persistent-scan")
        _SCAN_THREAD.start()
        return True


_HTML_PATH = Path(__file__).with_name("tactical_hud.html")
HTML = _HTML_PATH.read_text(encoding="utf-8") if _HTML_PATH.exists() else "<h1>tactical_hud.html missing</h1>"


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

        if path == "/api/tactical":
            snap = STATE.snapshot()
            self._send_json(200, snap.get("tactical", {}))
            return

        if path == "/api/chrono":
            snap = STATE.snapshot()
            self._send_json(200, {"events": snap.get("tactical", {}).get("chrono", [])})
            return

        if path == "/api/theories":
            snap = theory_snapshot()
            devices = STATE.snapshot().get("devices", [])
            snap["securitySummary"] = security_summary(devices)
            self._send_json(200, snap)
            return

        if path == "/api/screen/relay":
            qs = parse_qs(urlparse(self.path).query)
            address = (qs.get("address") or [""])[0]
            device = None
            if address:
                snap = STATE.snapshot()
                device = next(
                    (d for d in snap["devices"] if format_mac(d.get("id", "")) == format_mac(address)),
                    None,
                )
            self._send_json(200, screen_relay_snapshot(device))
            return

        if path == "/api/brief":
            snap = STATE.snapshot()
            brief = generate_mission_brief(snap)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            body = brief.encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/replay":
            snap = STATE.snapshot()
            frames = (snap.get("tactical") or {}).get("sciFi", {}).get("replayFrames", [])
            self._send_json(200, {"frames": frames})
            return

        if path == "/api/scenario":
            self._send_json(200, {
                "active": TACTICAL.scenario_id,
                "scenarios": [{"id": k, **{kk: vv for kk, vv in v.items() if kk != "autoPullMax"}} for k, v in SCENARIOS.items()],
            })
            return

        if path == "/api/dossier":
            qs = parse_qs(urlparse(self.path).query)
            address = (qs.get("address") or [""])[0]
            if not address:
                self._send_json(400, {"error": "address query param required"})
                return
            snap = STATE.snapshot()
            device = next(
                (d for d in snap["devices"] if format_mac(d.get("id", "")) == format_mac(address)),
                None,
            )
            if not device:
                self._send_json(404, {"error": "Device not found"})
                return
            self._send_json(200, TACTICAL.build_dossier(device, snap["hopGraph"]))
            return

        if path == "/api/extract":
            qs = parse_qs(urlparse(self.path).query)
            fmt = (qs.get("format") or ["json"])[0]
            password = (qs.get("password") or [""])[0]
            snap = STATE.snapshot()
            package = TACTICAL.build_extraction_package(snap, snap["hopGraph"])
            if fmt == "cipher" and password:
                body = TACTICAL.build_cipher_exfil(package, password)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="houseofasher_cipher.zip"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if fmt == "zip":
                body = TACTICAL.build_extraction_zip(package)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="houseofasher_intel.zip"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._send_json(200, package)
            return

        if path == "/api/events/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            sub = TACTICAL.subscribe_sse()
            try:
                hello = json.dumps({"type": "link", "message": "WAR ROOM LINK ESTABLISHED"})
                self.wfile.write(f"data: {hello}\n\n".encode())
                self.wfile.flush()
                while True:
                    if len(sub) > 0:
                        msg = sub.popleft()
                        self.wfile.write(f"data: {msg}\n\n".encode())
                        self.wfile.flush()
                    else:
                        time.sleep(0.5)
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                TACTICAL.unsubscribe_sse(sub)
            return

        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/hop/report":
            payload = self._read_json()
            try:
                HOP_GRAPH.register_scanner_report(payload)
                node_id = str(payload.get("nodeId") or "")
                if payload.get("listeningPost") and node_id:
                    SCI_FI.register_listening_post(node_id)
                    TACTICAL.log("deaddrop", f"LISTENING POST online · {payload.get('nodeLabel', node_id)}", {"nodeId": node_id})
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
            STATE.request_sync()
            self._send_json(200, {"ok": True, "persistent": PERSISTENT_SCAN, "message": "Hop sync queued — sweep continues"})
            return

        if path == "/api/scenario":
            payload = self._read_json()
            scenario = payload.get("scenario", "standard")
            try:
                active = TACTICAL.set_scenario(str(scenario))
                self._send_json(200, {"ok": True, "scenario": active})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            return

        if path == "/api/watchlist":
            payload = self._read_json()
            address = payload.get("address")
            if not address:
                self._send_json(400, {"error": "address required"})
                return
            action = payload.get("action", "add")
            nmac = normalize_mac(str(address))
            if action == "toggle":
                if nmac in TACTICAL.watchlist:
                    TACTICAL.remove_watchlist(address)
                else:
                    TACTICAL.add_watchlist(address)
            elif action == "remove":
                TACTICAL.remove_watchlist(address)
            else:
                TACTICAL.add_watchlist(address)
            self._send_json(200, {"ok": True, "watchlist": list(TACTICAL.watchlist)})
            return

        if path == "/api/scan":
            snap = STATE.snapshot()
            if snap["phase"] in ("running", "resolving", "pulling"):
                self._send_json(200, {
                    "ok": True,
                    "continuous": True,
                    "persistent": PERSISTENT_SCAN,
                    "alreadyRunning": True,
                })
                return

            ready = asyncio.run(check_bluetooth_ready())
            if not ready["ready"]:
                self._send_json(503, {"error": ready["message"], "reason": ready.get("reason")})
                return

            ensure_scan_thread()
            self._send_json(200, {"ok": True, "continuous": True, "persistent": PERSISTENT_SCAN})
            return

        self.send_error(404)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"#houseofasher tactical BLE HUD: http://127.0.0.1:{PORT}/")
    print("CONTINUOUS SWEEP — domino hop ingest every {:.0f}s (no device-count stop).".format(HOP_INGEST_INTERVAL))

    ready = asyncio.run(check_bluetooth_ready())
    if ready["ready"]:
        if ensure_scan_thread():
            print("Auto-started persistent BLE sweep.")
    else:
        print(f"Bluetooth not ready yet: {ready['message']}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping…")
        STATE.scan_shutdown.set()


if __name__ == "__main__":
    main()
