"""Windows paired Bluetooth device discovery.

BLE advertisements are not enough for phones/headphones: many only advertise
while pairing or on the Bluetooth settings screen. This module reads the local
Windows Bluetooth device registry so PoseSense can still offer paired devices
for manual camera-to-device binding.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field


MAC_RE = re.compile(r"(?:DEV_|BLUETOOTHDEVICE_|&)([0-9A-F]{12})(?:\\|_|$)", re.I)
SYSTEM_NAMES = (
    "Bluetooth LE Generic Attribute Service",
    "Microsoft Bluetooth",
    "Intel(R) Wireless Bluetooth",
    "Bluetooth Device (RFCOMM Protocol TDI)",
    "Object Push Service",
    "Sim Access Service",
    "Phonebook Access",
    "Personal Area Network",
)
AUDIO_SERVICE_WORDS = ("avrcp", "a2dp", "audio", "headset", "hands-free", "headphone")
PHONE_SERVICE_WORDS = ("phonebook", "sim access", "object push", "personal area network")
PHONE_NAME_WORDS = ("iphone", "pixel", "galaxy", "phone", "oneplus", "redmi")


@dataclass
class PairedBluetoothDevice:
    address: str
    name: str
    status: str = "Unknown"
    service_names: set[str] = field(default_factory=set)


def _extract_address(instance_id: str) -> str | None:
    match = MAC_RE.search(instance_id or "")
    if not match:
        return None
    raw = match.group(1).upper()
    return ":".join(raw[i : i + 2] for i in range(0, len(raw), 2))


def _is_system_name(name: str) -> bool:
    return any(token.lower() in name.lower() for token in SYSTEM_NAMES)


def _run_pnp_query() -> list[dict]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Get-PnpDevice -Class Bluetooth | "
            "Select-Object FriendlyName,Status,InstanceId | "
            "ConvertTo-Json -Compress"
        ),
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=6, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else [parsed]


def paired_bluetooth_devices() -> list[PairedBluetoothDevice]:
    """Return deduplicated paired Bluetooth devices on Windows."""
    if sys.platform != "win32":
        return []

    grouped: dict[str, PairedBluetoothDevice] = {}
    for row in _run_pnp_query():
        name = str(row.get("FriendlyName") or "").strip()
        instance_id = str(row.get("InstanceId") or "")
        status = str(row.get("Status") or "Unknown")
        address = _extract_address(instance_id)
        if not name or not address:
            continue

        device = grouped.setdefault(address, PairedBluetoothDevice(address=address, name=name, status=status))
        device.service_names.add(name)
        if not _is_system_name(name) and not any(word in name.lower() for word in AUDIO_SERVICE_WORDS):
            device.name = name
            device.status = status

    return [d for d in grouped.values() if d.name and not _is_system_name(d.name)]


def paired_device_meta(device: PairedBluetoothDevice) -> dict:
    """Hints that improve classification from paired Windows services."""
    services = " ".join(device.service_names).lower()
    name = device.name.lower()
    has_audio_service = any(word in services for word in AUDIO_SERVICE_WORDS)
    has_phone_service = any(word in services for word in PHONE_SERVICE_WORDS)
    looks_like_phone = any(word in name for word in PHONE_NAME_WORDS)
    meta = {
        "source": "windows_paired",
        "is_paired": True,
        "is_live_signal": False,
        "scan_note": "Paired in Windows; no live BLE advertisement/RSSI right now.",
    }
    if has_audio_service:
        meta.update({
            "device_type": "audio",
            "is_phone": False,
            "likely_body_zone": "Ears / neck",
            "icon": "🎧",
            "confidence": 0.78,
        })
    if has_phone_service and (looks_like_phone or not has_audio_service):
        meta.update({
            "device_type": "phone",
            "is_phone": True,
            "likely_body_zone": "Hand or pocket",
            "icon": "📱",
            "confidence": 0.84,
        })
    return meta
