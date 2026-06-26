"""UDP receiver for ESP32 WiFi CSI packets (real hardware path)."""

from __future__ import annotations

import asyncio
import json
from typing import Callable

from .wifi_csi_engine import CsiFrame

CsiCallback = Callable[[CsiFrame], None]


class Esp32CsiReceiver:
    """
    Listen for JSON CSI frames from ESP32 running WiFi CSI firmware.

    Expected UDP JSON: {"rssi": -50, "amplitudes": [...], "phases": [...]}
    Send from ESP32 to port 9000 on this machine.
    """

    def __init__(self, on_frame: CsiCallback, port: int = 9000) -> None:
        self.on_frame = on_frame
        self.port = port
        self._running = False
        self._transport = None

    async def run(self) -> None:
        self._running = True
        loop = asyncio.get_event_loop()

        class Protocol(asyncio.DatagramProtocol):
            def __init__(self, cb: CsiCallback) -> None:
                self.cb = cb

            def datagram_received(self, data: bytes, addr) -> None:
                try:
                    msg = json.loads(data.decode("utf-8"))
                    amps = msg.get("amplitudes") or msg.get("amp") or []
                    phases = msg.get("phases") or msg.get("phase") or []
                    if not phases and amps:
                        phases = [0.0] * len(amps)
                    self.cb(CsiFrame(
                        amplitudes=[float(a) for a in amps],
                        phases=[float(p) for p in phases],
                        rssi=float(msg.get("rssi", -60)),
                        timestamp=__import__("time").time(),
                        source="esp32",
                    ))
                except Exception:
                    pass

        transport, _ = await loop.create_datagram_endpoint(
            lambda: Protocol(self.on_frame),
            local_addr=("0.0.0.0", self.port),
        )
        self._transport = transport
        try:
            while self._running:
                await asyncio.sleep(0.2)
        finally:
            transport.close()

    def stop(self) -> None:
        self._running = False
        if self._transport:
            self._transport.close()
