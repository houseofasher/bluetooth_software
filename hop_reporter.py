#!/usr/bin/env python3
"""Companion hop scanner — reports what this machine hears to the hop graph server."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request

from bleak import BleakScanner

from ble_device_naming import format_mac


async def scan_once(duration: float) -> list[dict]:
    seen: dict[str, dict] = {}

    def callback(device, adv):
        addr = format_mac(device.address)
        name = adv.local_name or device.name
        seen[addr] = {
            "address": addr,
            "name": name,
            "rssi": adv.rssi,
            "seenAt": int(time.time() * 1000),
        }

    async with BleakScanner(detection_callback=callback, scanning_mode="active"):
        await asyncio.sleep(duration)

    return list(seen.values())


def post_report(server: str, node_id: str, label: str, self_address: str | None, observations: list[dict]) -> dict:
    payload = {
        "nodeId": node_id,
        "nodeLabel": label,
        "selfAddress": self_address,
        "observations": observations,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{server.rstrip('/')}/api/hop/report",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def main() -> int:
    parser = argparse.ArgumentParser(description="BLE hop companion reporter")
    parser.add_argument("--server", default="http://127.0.0.1:8765", help="Hop graph server URL")
    parser.add_argument("--node-id", required=True, help="Unique scanner id (e.g. pixel-hop-1)")
    parser.add_argument("--label", default=None, help="Human label for this scanner")
    parser.add_argument("--self-address", default=None, help="This device's BLE MAC (links domino chain)")
    parser.add_argument("--duration", type=float, default=12.0, help="Scan seconds")
    args = parser.parse_args()

    label = args.label or args.node_id
    print(f"Scanning {args.duration}s as hop node '{label}'...")
    observations = await scan_once(args.duration)
    print(f"Seen {len(observations)} device(s), posting to {args.server}...")

    try:
        result = post_report(args.server, args.node_id, label, args.self_address, observations)
        print(json.dumps(result, indent=2))
        return 0
    except urllib.error.URLError as exc:
        print(f"Failed to reach server: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
