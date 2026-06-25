"""Resolve BLE addresses to paired device names on Windows."""

from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache

REG_BASE = r"HKLM\SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"


def _normalize_mac(raw: str) -> str:
    hex_only = re.sub(r"[^0-9A-Fa-f]", "", raw)
    if len(hex_only) != 12:
        return raw.upper()
    return ":".join(hex_only[i : i + 2] for i in range(0, 12, 2)).upper()


def _decode_reg_value(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if re.fullmatch(r"[0-9A-Fa-f]+", raw):
        bytes_out = bytes.fromhex(raw)
    elif raw.lower().startswith("hex"):
        hex_part = raw.split(":", 1)[-1].strip()
        bytes_out = bytes(int(b, 16) for b in hex_part.split() if b)
    else:
        return raw.strip('"').strip()
    if not bytes_out:
        return ""
    for encoding in ("utf-16-le", "utf-8", "ascii"):
        try:
            text = bytes_out.decode(encoding).strip("\x00 ").strip()
            if text and not all(c == "\x00" for c in text):
                return text
        except UnicodeDecodeError:
            continue
    return ""


def _load_winrt_paired() -> dict[str, str]:
    """WinRT paired LE device names (Windows 10+)."""
    script = """
[Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Bluetooth.BluetoothLEDevice,Windows.Devices,ContentType=WindowsRuntime] | Out-Null
$selector = [Windows.Devices.Bluetooth.BluetoothLEDevice]::GetDeviceSelectorFromPairingState($true)
$infos = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync($selector).GetAwaiter().GetResult()
$out = @()
foreach ($info in $infos) {
  try {
    $ble = [Windows.Devices.Bluetooth.BluetoothLEDevice]::FromIdAsync($info.Id).GetAwaiter().GetResult()
    if ($ble -and $ble.Name) {
      $addr = "{0:X2}:{1:X2}:{2:X2}:{3:X2}:{4:X2}:{5:X2}" -f
        [byte](($ble.BluetoothAddress -shr 40) -band 0xFF),
        [byte](($ble.BluetoothAddress -shr 32) -band 0xFF),
        [byte](($ble.BluetoothAddress -shr 24) -band 0xFF),
        [byte](($ble.BluetoothAddress -shr 16) -band 0xFF),
        [byte](($ble.BluetoothAddress -shr 8) -band 0xFF),
        [byte]($ble.BluetoothAddress -band 0xFF)
      $out += [pscustomobject]@{ address = $addr; name = $ble.Name }
    }
  } catch {}
}
$out | ConvertTo-Json -Compress
""".strip()
    names: dict[str, str] = {}
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return names
        data = json.loads(proc.stdout.strip())
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            addr = _normalize_mac(str(row.get("address", "")))
            name = str(row.get("name", "")).strip()
            if addr and name:
                names[addr] = name
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return names


@lru_cache(maxsize=1)
def load_paired_names() -> dict[str, str]:
    """MAC (AA:BB:...) -> friendly name from Windows Bluetooth registry + WinRT."""
    names: dict[str, str] = {}
    names.update(_load_winrt_paired())
    try:
        proc = subprocess.run(
            ["reg", "query", REG_BASE],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return names

        keys = re.findall(r"Devices\\([0-9A-Fa-f]{12})", proc.stdout, re.I)
        for key in keys:
            mac = _normalize_mac(key)
            for value_name in ("Name", "LEName"):
                try:
                    val_proc = subprocess.run(
                        ["reg", "query", f"{REG_BASE}\\{key}", "/v", value_name],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    match = re.search(
                        rf"{value_name}\s+(REG_[A-Z_]+)\s+(.+)",
                        val_proc.stdout,
                        re.I,
                    )
                    if match:
                        decoded = _decode_reg_value(match.group(2))
                        if decoded and len(decoded) > 1:
                            names[mac] = decoded
                            break
                except OSError:
                    continue
    except OSError:
        pass
    return names


def resolve_paired_name(address: str) -> str | None:
    return load_paired_names().get(_normalize_mac(address))
