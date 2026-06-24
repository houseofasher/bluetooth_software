"""Resolve BLE device display names from multiple sources."""

from __future__ import annotations

import asyncio
import re
import winreg
from dataclasses import dataclass, field
from typing import Any, Literal

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

NameSource = Literal["broadcast", "paired", "gatt", "inferred", "address"]

DEVICE_NAME_UUID = "00002a00-0000-1000-8000-00805f9b34fb"
GATT_MAX_ENRICH = 5
GATT_TIMEOUT_SEC = 4.0

COMPANY_NAMES: dict[int, str] = {
    0x004C: "Apple",
    0x0006: "Microsoft",
    0x000F: "Broadcom",
    0x0075: "Samsung",
    0x00E0: "Google",
    0x0087: "Garmin",
    0x0157: "Anker",
    0x0318: "Sonos",
    0x0499: "Nintendo",
    0x05AC: "Apple",
    0x0A5C: "Bose",
    0x0D8C: "Jabra",
    0x1915: "Nordic Semiconductor",
    0x2204: "Tile",
    0x2412: "Sony",
    0x3432: "Fitbit",
    0x4154: "Tile",
}

SERVICE_LABELS: dict[str, str] = {
    "1800": "Generic Access",
    "1801": "Generic Attribute",
    "180A": "Device Information",
    "180D": "Heart Rate",
    "180F": "Battery",
    "1812": "HID",
    "181C": "User Data",
    "FE2C": "Google Fast Pair",
    "FE95": "Xiaomi",
    "FE9F": "Google",
    "FDAA": "Sonos",
}


def normalize_mac(address: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", address).upper()


def format_mac(address: str) -> str:
    mac = normalize_mac(address)
    if len(mac) != 12:
        return address
    return ":".join(mac[i : i + 2] for i in range(0, 12, 2))


def short_mac_suffix(address: str) -> str:
    mac = format_mac(address)
    parts = mac.split(":")
    return ":".join(parts[-3:]) if len(parts) >= 3 else mac


def service_uuid_key(uuid: str) -> str:
    u = uuid.lower().replace("-", "")
    if len(u) == 4:
        return u.upper()
    if len(u) == 32 and u.endswith("00001000800000805f9b34fb"):
        return u[4:8].upper()
    return u[-4:].upper() if len(u) >= 4 else u.upper()


def _decode_registry_string(value: bytes | str) -> str | None:
    if isinstance(value, str):
        text = value
    else:
        text = value.decode("utf-8", errors="ignore")
    text = text.replace("\x00", "").strip()
    return text or None


def load_windows_paired_names() -> dict[str, str]:
    names: dict[str, str] = {}
    base = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as parent:
            count = winreg.QueryInfoKey(parent)[0]
            for i in range(count):
                key_name = winreg.EnumKey(parent, i)
                try:
                    with winreg.OpenKey(parent, key_name) as device_key:
                        for value_name in ("LEName", "Name"):
                            try:
                                raw, _ = winreg.QueryValueEx(device_key, value_name)
                                decoded = _decode_registry_string(raw)
                                if decoded:
                                    names[normalize_mac(key_name)] = decoded
                                    break
                            except OSError:
                                continue
                except OSError:
                    continue
    except OSError:
        pass
    return names


@dataclass
class DeviceSignals:
    address: str
    broadcast_name: str | None = None
    rssi: int | None = None
    uuids: list[str] = field(default_factory=list)
    manufacturer_data: dict[int, bytes] = field(default_factory=dict)
    service_data_keys: list[str] = field(default_factory=list)
    tx_power: int | None = None
    gatt_name: str | None = None
    scan_source: str = "live"

    def merge(
        self,
        device: BLEDevice,
        adv: AdvertisementData,
        source: str,
    ) -> None:
        self.scan_source = source
        candidate = (adv.local_name or device.name or "").strip()
        if candidate and not _looks_like_mac(candidate):
            self.broadcast_name = candidate
        if adv.rssi is not None:
            self.rssi = adv.rssi
        self.uuids = sorted(set(self.uuids + [str(u) for u in adv.service_uuids]))
        self.manufacturer_data.update(adv.manufacturer_data)
        self.service_data_keys = sorted(
            set(self.service_data_keys + [str(k) for k in adv.service_data])
        )
        if adv.tx_power is not None:
            self.tx_power = adv.tx_power


def _looks_like_mac(value: str) -> bool:
    return bool(re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", value))


@dataclass
class ResolvedName:
    display_name: str
    name_source: NameSource
    broadcast_name: str | None
    manufacturer: str | None
    inferred_detail: str | None


def manufacturer_label(manufacturer_data: dict[int, bytes]) -> str | None:
    for company_id in sorted(manufacturer_data):
        label = COMPANY_NAMES.get(company_id)
        if label:
            return label
    return None


def service_labels(uuids: list[str], limit: int = 2) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for uuid in uuids:
        key = service_uuid_key(uuid)
        label = SERVICE_LABELS.get(key)
        if label and label not in seen:
            seen.add(label)
            labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def infer_label(signals: DeviceSignals) -> str | None:
    parts: list[str] = []
    mfg = manufacturer_label(signals.manufacturer_data)
    if mfg:
        parts.append(mfg)
    svc = service_labels(signals.uuids)
    if svc:
        parts.append(" + ".join(svc))
    if signals.service_data_keys and not svc:
        parts.append("Service data")
    if not parts and signals.uuids:
        parts.append(f"{len(signals.uuids)} service(s)")
    return " · ".join(parts) if parts else None


def resolve_name(
    signals: DeviceSignals,
    paired_names: dict[str, str],
) -> ResolvedName:
    broadcast = signals.broadcast_name
    if broadcast:
        return ResolvedName(
            display_name=broadcast,
            name_source="broadcast",
            broadcast_name=broadcast,
            manufacturer=manufacturer_label(signals.manufacturer_data),
            inferred_detail=None,
        )

    mac = normalize_mac(signals.address)
    paired = paired_names.get(mac)
    if paired:
        return ResolvedName(
            display_name=paired,
            name_source="paired",
            broadcast_name=None,
            manufacturer=manufacturer_label(signals.manufacturer_data),
            inferred_detail=None,
        )

    if signals.gatt_name:
        return ResolvedName(
            display_name=signals.gatt_name,
            name_source="gatt",
            broadcast_name=None,
            manufacturer=manufacturer_label(signals.manufacturer_data),
            inferred_detail=None,
        )

    inferred = infer_label(signals)
    if inferred:
        return ResolvedName(
            display_name=inferred,
            name_source="inferred",
            broadcast_name=None,
            manufacturer=manufacturer_label(signals.manufacturer_data),
            inferred_detail=inferred,
        )

    suffix = short_mac_suffix(signals.address)
    return ResolvedName(
        display_name=f"BLE device · {suffix}",
        name_source="address",
        broadcast_name=None,
        manufacturer=manufacturer_label(signals.manufacturer_data),
        inferred_detail=None,
    )


def signals_to_record(signals: DeviceSignals, paired_names: dict[str, str]) -> dict[str, Any]:
    resolved = resolve_name(signals, paired_names)
    return {
        "id": format_mac(signals.address),
        "displayName": resolved.display_name,
        "name": resolved.display_name,
        "nameSource": resolved.name_source,
        "broadcastName": resolved.broadcast_name,
        "manufacturer": resolved.manufacturer,
        "inferredDetail": resolved.inferred_detail,
        "rssi": signals.rssi,
        "uuids": signals.uuids,
        "source": signals.scan_source,
        "lastSeen": 0,
    }


async def read_gatt_device_name(address: str) -> str | None:
    try:
        async with BleakClient(address, timeout=GATT_TIMEOUT_SEC) as client:
            data = await client.read_gatt_char(DEVICE_NAME_UUID)
            text = data.decode("utf-8", errors="ignore").replace("\x00", "").strip()
            return text or None
    except Exception:
        return None


async def enrich_with_gatt_names(
    signals_map: dict[str, DeviceSignals],
    paired_names: dict[str, str],
) -> None:
    candidates: list[DeviceSignals] = []
    for signals in signals_map.values():
        resolved = resolve_name(signals, paired_names)
        if resolved.name_source in ("inferred", "address"):
            candidates.append(signals)

    candidates.sort(key=lambda s: s.rssi if s.rssi is not None else -999, reverse=True)
    targets = candidates[:GATT_MAX_ENRICH]
    if not targets:
        return

    results = await asyncio.gather(
        *(read_gatt_device_name(s.address) for s in targets),
        return_exceptions=True,
    )
    for signals, result in zip(targets, results):
        if isinstance(result, str) and result:
            signals.gatt_name = result
