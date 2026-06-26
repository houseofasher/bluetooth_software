"""PoseSense — live camera + BLE + WiFi CSI fusion server."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from posesense.ble_collector import BleCollector
from posesense.camera_tracker import CameraTracker
from posesense.fusion import FusionEngine
from posesense.narrative import resolve_narrative
from posesense.simulator import MotionSimulator
from posesense.skeleton import HAND_CONNECTIONS, POSE_EDGE_GROUPS
from posesense.wifi_csi_engine import WiFiCsiEngine, CsiFrame
from posesense.wifi_csi_simulator import WiFiCsiSimulator
from posesense.wifi_esp32_receiver import Esp32CsiReceiver
from posesense.wifi_rssi_scanner import WiFiRssiScanner

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="PoseSense Live")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

fusion = FusionEngine()
camera = CameraTracker()
wifi_engine = WiFiCsiEngine()
clients: set[WebSocket] = set()
_command_queue: asyncio.Queue[dict] = asyncio.Queue()

wall_mode = True
wifi_source_name = "sim"
_wifi_source = None


def on_ble_device(address: str, name: str, rssi: float, ts: float, meta: dict) -> None:
    fusion.ingest_ble(address, name, rssi, ts, meta)


def on_sim_rssi(address: str, name: str, rssi: float, ts: float) -> None:
    fusion.ingest_ble(address, name, rssi, ts, {
        "brand": "SimBeacon",
        "model": name,
        "display_name": name,
        "device_type": "beacon",
        "is_phone": False,
        "likely_body_zone": "Fixed position",
        "icon": "📡",
        "confidence": 1.0,
    })


def on_wifi_csi(frame: CsiFrame) -> None:
    wifi_engine.ingest(frame)


async def process_commands() -> None:
    global wall_mode
    while True:
        cmd = await _command_queue.get()
        action = cmd.get("action")
        if action == "bind":
            fusion.bind_manual(int(cmd["person_id"]), cmd["address"])
        elif action == "unbind":
            fusion.unbind(int(cmd["person_id"]))
        elif action == "set_wall_mode":
            wall_mode = bool(cmd.get("enabled", True))
            if _wifi_source is not None and hasattr(_wifi_source, "wall_mode"):
                _wifi_source.wall_mode = wall_mode


def _wifi_through_wall_targets(state) -> list[dict]:
    """Ghost presence detected by WiFi only (no camera line-of-sight)."""
    if not state.through_wall or state.through_wall_confidence < 0.3:
        return []
    return [{
        "id": "wifi-1",
        "source": "wifi_csi",
        "activity": state.activity,
        "zone": state.zone,
        "x": state.zone_x,
        "y": 0.55,
        "motion_energy": state.motion_energy,
        "confidence": state.through_wall_confidence,
        "label": f"Body reflection ({state.activity})",
    }]


async def broadcast_loop(ble_mode: str) -> None:
    while True:
        frame = camera.get_latest()
        persons = frame.persons if frame else []
        targets = fusion.update(persons)
        camera_count = len(targets)

        wifi_state = wifi_engine.analyze(
            camera_person_count=camera_count,
            wall_mode=wall_mode,
        )

        has_metrics = any(t.metrics.get("measurements_ready") for t in targets) if targets else False
        has_hands = any(t.left_hand or t.right_hand for t in targets) if targets else False
        unbound = fusion.unbound_devices(persons)
        phone_nearby = any(d.get("is_phone") for d in unbound)

        narrative = resolve_narrative(
            person_count=camera_count,
            device_count=len(fusion.devices),
            binding_count=len(fusion.bindings),
            phone_nearby=phone_nearby,
            has_metrics=has_metrics,
            has_hands=has_hands,
            wifi_occupied=wifi_state.occupied,
            through_wall=wifi_state.through_wall,
        )

        payload = {
            "mode": ble_mode,
            "timestamp": time.time(),
            "wall_mode": wall_mode,
            "narrative": narrative,
            "wifi": {
                "source": wifi_source_name,
                "occupied": wifi_state.occupied,
                "motion_energy": wifi_state.motion_energy,
                "activity": wifi_state.activity,
                "through_wall": wifi_state.through_wall,
                "through_wall_confidence": wifi_state.through_wall_confidence,
                "zone": wifi_state.zone,
                "zone_x": wifi_state.zone_x,
                "person_count_est": wifi_state.person_count_est,
                "message": wifi_state.message,
                "subcarrier_motion": wifi_state.subcarrier_motion,
                "spectrogram": wifi_engine.spectrogram[-20:],
                "home_detected": wifi_state.home_detected,
                "automation": wifi_state.automation,
                "through_wall_targets": _wifi_through_wall_targets(wifi_state),
            },
            "camera": {
                "jpeg": frame.jpeg_base64 if frame else None,
                "width": frame.width if frame else 1280,
                "height": frame.height if frame else 720,
            },
            "targets": [
                {
                    "person_id": t.person_id,
                    "ble_address": t.ble_address,
                    "device": t.device,
                    "devices": t.devices,
                    "placement": t.placement,
                    "ble_name": t.ble_name,
                    "ble_device_type": t.ble_device_type,
                    "ble_is_phone": t.ble_is_phone,
                    "in_frame": t.in_frame,
                    "pose": t.pose,
                    "face": t.face,
                    "left_hand": t.left_hand,
                    "right_hand": t.right_hand,
                    "bbox": t.bbox,
                    "motion_energy": round(t.motion_energy, 3),
                    "rssi": t.rssi,
                    "bind_method": t.bind_method,
                    "metrics": t.metrics,
                }
                for t in targets
            ],
            "pose_edge_groups": [
                {"name": n, "edges": e, "color": c} for n, e, c in POSE_EDGE_GROUPS
            ],
            "hand_edges": HAND_CONNECTIONS,
            "bluetooth_radio_targets": fusion.radio_targets(persons),
            "unbound_devices": unbound,
            "bindings": fusion.bound_summary(),
            "person_count": camera_count,
            "device_count": len(fusion.devices),
            "disclaimer": (
                "Camera = line-of-sight pose. Bluetooth = device identity from radio advertisements. "
                "Bluetooth on a normal laptop does not expose bounce/CSI imaging, so Bluetooth device "
                "positions are radio proxies, not optical object recognition. "
                "WiFi CSI = body reflections from router signal perturbations — can detect motion through "
                "walls when camera cannot see. Smart-home triggers simulate lights/climate on WiFi presence."
            ),
        }

        dead: set[WebSocket] = set()
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        clients.difference_update(dead)
        await asyncio.sleep(0.05)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                if isinstance(msg, dict) and "action" in msg:
                    await _command_queue.put(msg)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        clients.discard(ws)


async def main(
    ble_mode: str,
    name_filter: str | None,
    camera_index: int,
    wifi_mode: str,
) -> None:
    global wifi_source_name, _wifi_source

    camera.camera_index = camera_index
    camera.start()

    if ble_mode == "sim":
        ble_source = MotionSimulator(on_sim_rssi)
    else:
        ble_source = BleCollector(on_ble_device, name_filter=name_filter)

    wifi_source_name = wifi_mode
    if wifi_mode == "sim":
        wifi_source = WiFiCsiSimulator(on_wifi_csi, wall_mode=True)
    elif wifi_mode == "esp32":
        wifi_source = Esp32CsiReceiver(on_wifi_csi)
    else:
        wifi_source = WiFiRssiScanner(on_wifi_csi)

    _wifi_source = wifi_source

    ble_task = asyncio.create_task(ble_source.run())
    wifi_task = asyncio.create_task(wifi_source.run())
    broadcast_task = asyncio.create_task(broadcast_loop(ble_mode))
    command_task = asyncio.create_task(process_commands())

    config = uvicorn.Config(app, host="127.0.0.1", port=8766, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        ble_source.stop()
        wifi_source.stop()
        camera.stop()
        ble_task.cancel()
        wifi_task.cancel()
        broadcast_task.cancel()
        command_task.cancel()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PoseSense live tracker")
    parser.add_argument("--mode", choices=["sim", "ble"], default="ble")
    parser.add_argument("--filter", default=None)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument(
        "--wifi",
        choices=["sim", "rssi", "esp32"],
        default="sim",
        help="WiFi sensing: sim=through-wall CSI demo, rssi=Windows scan, esp32=hardware UDP:9000",
    )
    args = parser.parse_args()
    asyncio.run(main(args.mode, args.filter, args.camera, args.wifi))
