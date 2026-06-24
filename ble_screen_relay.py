"""Screen relay theories — narrative → flaw → fix → code.

BLE and GATT cannot mirror another device's display. Phones and laptops deliberately
block remote framebuffer access. This module documents honest, consent-based paths
to get pixels onto your monitor — and why covert capture is not a viable theory.
"""

from __future__ import annotations

from typing import Any, Literal

Platform = Literal["android", "ios", "windows", "macos", "linux", "unknown"]

SCREEN_RELAY_THEORIES: list[dict[str, str]] = [
    {
        "id": "ble_not_framebuffer",
        "category": "screen_relay",
        "narrative": "Pull live screen over BLE GATT",
        "flaw": "BLE ~1 Mbps and GATT max ~512 B/transaction — no framebuffer characteristic exists",
        "flawType": "technical",
        "fix": "Use Wi‑Fi/USB video channel; BLE only for presence discovery in this repo",
        "code": "ble_gatt_pull.pull_device_data",
        "module": "ble_screen_relay.py",
        "feasibility": "impossible",
    },
    {
        "id": "gatt_screen_blocked",
        "category": "screen_relay",
        "narrative": "Read screen buffer after GATT connect",
        "flaw": "iOS/Android never expose display memory to unknown centrals — exfilTier LOCKED",
        "flawType": "security",
        "fix": "Treat LOCKED tier as signal to switch relay strategy, not push harder on GATT",
        "code": "ble_gatt_pull._exfil_tier",
        "module": "ble_screen_relay.py",
        "feasibility": "blocked",
    },
    {
        "id": "covert_mirror",
        "category": "screen_relay",
        "narrative": "Secretly view stranger's screen from scan alone",
        "flaw": "OS sandbox + encryption; unauthorized access is illegal",
        "flawType": "legal",
        "fix": "Not supported — operator must own device or have explicit consent",
        "code": "ble_screen_relay.consent_gate",
        "module": "ble_screen_relay.py",
        "feasibility": "forbidden",
    },
    {
        "id": "scrcpy_usb",
        "category": "screen_relay",
        "narrative": "Mirror Android to PC monitor via USB",
        "flaw": "Requires USB debugging ON and RSA fingerprint approve on phone",
        "flawType": "operational",
        "fix": "scrcpy over adb — user taps Allow on device once",
        "code": "external:scrcpy + adb",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "android",
    },
    {
        "id": "scrcpy_wifi",
        "category": "screen_relay",
        "narrative": "Wireless Android mirror on same LAN",
        "flaw": "Still needs adb tcpip + prior USB trust or Android 11+ wireless pairing",
        "flawType": "operational",
        "fix": "adb pair / adb connect then scrcpy --tcpip",
        "code": "external:scrcpy",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "android",
    },
    {
        "id": "airplay_receiver",
        "category": "screen_relay",
        "narrative": "Mirror iPhone/iPad screen to Windows monitor",
        "flaw": "Apple blocks third-party silent capture; user must start Screen Mirroring",
        "flawType": "security",
        "fix": "AirPlay receiver on PC (LonelyScreen, UxPlay, or built-in where available)",
        "code": "external:AirPlay",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "ios",
    },
    {
        "id": "quicktime_ios",
        "category": "screen_relay",
        "narrative": "Wired iOS screen on Mac — extend to second monitor",
        "flaw": "Needs Lightning/USB-C cable and Mac QuickTime Movie Recording",
        "flawType": "operational",
        "fix": "QuickTime → New Movie Recording → select iPhone; macOS display extend",
        "code": "external:QuickTime",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "ios",
    },
    {
        "id": "miracast_win",
        "category": "screen_relay",
        "narrative": "Cast laptop/phone to Windows display",
        "flaw": "Source must support Miracast; not all corporate laptops allow it",
        "flawType": "technical",
        "fix": "Win+K → Connect to wireless display on source device",
        "code": "external:Miracast",
        "module": "ble_screen_relay.py",
        "feasibility": "medium",
        "platform": "windows",
    },
    {
        "id": "windows_project",
        "category": "screen_relay",
        "narrative": "Project Windows laptop to your monitor",
        "flaw": "Both machines must be on same network or cable",
        "flawType": "operational",
        "fix": "Settings → System → Projecting to this PC → allow from source laptop",
        "code": "external:Windows.Projection",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "windows",
    },
    {
        "id": "chromecast_tab",
        "category": "screen_relay",
        "narrative": "Show mobile browser tab on monitor",
        "flaw": "Casts tab only, not full system UI without user gesture",
        "flawType": "technical",
        "fix": "Chrome Cast → select tab; or Android Cast screen with unlock + confirm",
        "code": "external:GoogleCast",
        "module": "ble_screen_relay.py",
        "feasibility": "medium",
        "platform": "android",
    },
    {
        "id": "webrtc_display",
        "category": "screen_relay",
        "narrative": "Browser picks window — show on HUD monitor",
        "flaw": "User must click Share and choose window each session",
        "flawType": "ethical",
        "fix": "getDisplayMedia() in companion page → POST frames to /api/screen/frame",
        "code": "ble_screen_relay.webrtc_relay_spec",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "any",
    },
    {
        "id": "hdmi_capture",
        "category": "screen_relay",
        "narrative": "Physical wire — pixels cannot be blocked by OS policy",
        "flaw": "Needs cable + capture card; not wireless",
        "flawType": "operational",
        "fix": "HDMI out → USB capture dongle → OBS or second monitor clone",
        "code": "external:HDMI_capture",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "any",
    },
    {
        "id": "rdp_consent",
        "category": "screen_relay",
        "narrative": "Remote desktop laptop screen on your monitor",
        "flaw": "Needs credentials, network path, and session permission",
        "flawType": "security",
        "fix": "Windows RDP / RustDesk / AnyDesk with user accepting session",
        "code": "external:RDP",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "windows",
    },
    {
        "id": "ios_replaykit",
        "category": "screen_relay",
        "narrative": "In-app iOS screen broadcast to custom receiver",
        "flaw": "Requires App Store app or MDM profile; user starts broadcast from Control Center",
        "flawType": "security",
        "fix": "ReplayKit broadcast extension → WebRTC or HLS to local relay server",
        "code": "ble_screen_relay.replaykit_spec",
        "module": "ble_screen_relay.py",
        "feasibility": "medium",
        "platform": "ios",
    },
    {
        "id": "companion_frame_relay",
        "category": "screen_relay",
        "narrative": "Domino hop for screen — like hop_reporter but JPEG frames",
        "flaw": "Source device must run your companion app and tap Share",
        "flawType": "ethical",
        "fix": "POST /api/screen/frame from cooperative phone (future); BLE finds device, Wi‑Fi carries video",
        "code": "ble_screen_relay.companion_relay_spec",
        "module": "ble_screen_relay.py",
        "feasibility": "planned",
        "platform": "any",
    },
    {
        "id": "ble_to_wifi_handoff",
        "category": "screen_relay",
        "narrative": "BLE discovers phone, Wi‑Fi carries mirror stream",
        "flaw": "BLE cannot carry video; only pairs identity to IP/session",
        "flawType": "technical",
        "fix": "Match scanned MAC/name → show QR with WebRTC URL on HUD for phone to open",
        "code": "ble_screen_relay.recommend_relay_path",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
        "platform": "any",
    },
    {
        "id": "qr_session_pair",
        "category": "screen_relay",
        "narrative": "Phone scans QR on monitor to start consent relay",
        "flaw": "Extra step — not automatic from passive scan",
        "flawType": "operational",
        "fix": "HUD displays session QR → phone opens https://127.0.0.1:8765/relay → Share screen",
        "code": "ble_screen_relay.qr_handoff_spec",
        "module": "ble_screen_relay.py",
        "feasibility": "planned",
        "platform": "any",
    },
    {
        "id": "obs_ndi",
        "category": "screen_relay",
        "narrative": "Low-latency LAN video on monitor",
        "flaw": "Sender must install OBS/NDI tools",
        "flawType": "operational",
        "fix": "OBS Virtual Camera or NDI Scan Converter on source laptop",
        "code": "external:NDI",
        "module": "ble_screen_relay.py",
        "feasibility": "medium",
        "platform": "windows",
    },
    {
        "id": "continuity_camera",
        "category": "screen_relay",
        "narrative": "Apple ecosystem second screen",
        "flaw": "Requires same Apple ID / Continuity — not arbitrary devices",
        "flawType": "security",
        "fix": "Sidecar (iPad) or Continuity Camera — paired Apple devices only",
        "code": "external:Apple.Continuity",
        "module": "ble_screen_relay.py",
        "feasibility": "medium",
        "platform": "ios",
    },
    {
        "id": "locked_phone_path",
        "category": "screen_relay",
        "narrative": "When GATT LOCKED — still see their screen",
        "flaw": "LOCKED means OS denied connect — no BLE workaround exists",
        "flawType": "technical",
        "fix": "Pair in Windows Bluetooth OR use AirPlay/scrcpy with user approval on device",
        "code": "ble_screen_relay.recommend_relay_path",
        "module": "ble_screen_relay.py",
        "feasibility": "high",
    },
]

THEORY_BY_ID = {t["id"]: t for t in SCREEN_RELAY_THEORIES}

PLATFORM_HINTS: dict[str, list[str]] = {
    "android": ["scrcpy_usb", "scrcpy_wifi", "chromecast_tab", "webrtc_display", "companion_frame_relay"],
    "ios": ["airplay_receiver", "quicktime_ios", "ios_replaykit", "webrtc_display", "continuity_camera"],
    "windows": ["windows_project", "miracast_win", "rdp_consent", "obs_ndi", "webrtc_display"],
    "macos": ["airplay_receiver", "quicktime_ios", "webrtc_display", "obs_ndi"],
    "unknown": ["webrtc_display", "hdmi_capture", "qr_session_pair", "ble_to_wifi_handoff"],
}


def consent_gate(operator_owns_device: bool, explicit_consent: bool) -> dict[str, Any]:
    """Hard gate — screen relay theories require consent."""
    allowed = operator_owns_device or explicit_consent
    return {
        "allowed": allowed,
        "message": (
            "Screen relay permitted — use consent-based path below."
            if allowed
            else "BLOCKED — pair device you own or obtain explicit consent before mirroring."
        ),
    }


def guess_platform(record: dict[str, Any]) -> Platform:
    name = (record.get("displayName") or record.get("name") or "").lower()
    passive = record.get("passiveIntel") or {}
    hints = " ".join(passive.get("ecosystemHints") or []).lower()
    appearance = str((record.get("pulledData") or {}).get("data", {}).get("appearance", "")).lower()

    if "iphone" in name or "ipad" in name or "apple" in hints or "phone" in appearance:
        return "ios"
    if "pixel" in name or "galaxy" in name or "android" in name or "google" in hints or "fast pair" in hints:
        return "android"
    if "surface" in name or "windows" in name or "swift pair" in hints:
        return "windows"
    if "macbook" in name or "imac" in name:
        return "macos"
    return "unknown"


def recommend_relay_path(record: dict[str, Any] | None = None) -> dict[str, Any]:
    """Best-effort relay recommendation when GATT cannot show screen content."""
    tier = (record or {}).get("exfilTier", "PASSIVE_ONLY")
    platform = guess_platform(record or {})
    paths = list(PLATFORM_HINTS.get(platform, PLATFORM_HINTS["unknown"]))

    if tier == "LOCKED":
        paths = ["locked_phone_path", "ble_to_wifi_handoff"] + paths

    # Always prepend impossibility theories for education
    education = ["ble_not_framebuffer", "gatt_screen_blocked", "covert_mirror"]
    ranked_ids: list[str] = []
    for tid in education + paths:
        if tid not in ranked_ids:
            ranked_ids.append(tid)

    theories = [THEORY_BY_ID[tid] for tid in ranked_ids if tid in THEORY_BY_ID]
    top = next((t for t in theories if t.get("feasibility") in ("high", "planned")), theories[-1] if theories else None)

    return {
        "narrative": "See another device's screen on your monitor",
        "bleCanDo": "Discover device presence, name, RSSI — not pixels",
        "gattExfilTier": tier,
        "guessedPlatform": platform,
        "recommendedTheoryId": top.get("id") if top else None,
        "recommendedFix": top.get("fix") if top else None,
        "recommendedCode": top.get("code") if top else None,
        "operatorSteps": _operator_steps(platform, tier),
        "theories": theories,
        "consent": consent_gate(operator_owns_device=True, explicit_consent=False),
    }


def _operator_steps(platform: Platform, exfil_tier: str) -> list[str]:
    steps = [
        "BLE scan finds the device in tactical HUD (presence only).",
        "GATT pull cannot read screen — expect exfilTier LOCKED on phones.",
    ]
    if platform == "android":
        steps.extend([
            "Enable USB debugging on the phone → approve RSA fingerprint.",
            "Install scrcpy → run: scrcpy -s <device_serial> (shows on PC monitor).",
            "Or: same Wi‑Fi → adb pair → scrcpy --tcpip.",
        ])
    elif platform == "ios":
        steps.extend([
            "On iPhone: Control Center → Screen Mirroring → pick AirPlay receiver on PC.",
            "Or: cable to Mac QuickTime, extend display to your monitor.",
            "Or: install cooperative app with ReplayKit (user starts broadcast).",
        ])
    elif platform == "windows":
        steps.extend([
            "On source laptop: Win+K or Connect → project to this PC.",
            "Or: RDP / RustDesk with user accepting the session.",
        ])
    else:
        steps.extend([
            "Open HUD relay page (planned) → browser Share screen (getDisplayMedia).",
            "Or: HDMI capture card from physical video out.",
            "Or: scan QR on monitor to start WebRTC session from phone.",
        ])
    if exfil_tier == "LOCKED":
        steps.insert(2, "LOCKED: pair device in Windows Bluetooth first — still won't mirror; use paths above.")
    return steps


def webrtc_relay_spec() -> dict[str, Any]:
    return {
        "endpoint": "POST /api/screen/frame",
        "browserApi": "navigator.mediaDevices.getDisplayMedia()",
        "transport": "JPEG or WebRTC to localhost HUD canvas",
        "consent": "Browser shows picker — user chooses window/screen",
        "status": "spec_only",
    }


def companion_relay_spec() -> dict[str, Any]:
    return {
        "pattern": "Like hop_reporter.py but posts base64 JPEG every N seconds",
        "endpoint": "POST /api/screen/frame",
        "payload": {"nodeId": "...", "deviceAddress": "...", "frameJpeg": "...", "ts": 0},
        "consent": "Companion app with foreground service + Share button",
        "status": "spec_only",
    }


def replaykit_spec() -> dict[str, Any]:
    return {
        "platform": "iOS",
        "api": "RPBroadcastSampleHandler",
        "consent": "User starts screen recording from Control Center",
        "status": "spec_only",
    }


def qr_handoff_spec(session_base: str = "http://127.0.0.1:8765") -> dict[str, Any]:
    return {
        "qrUrl": f"{session_base}/relay",
        "flow": "HUD shows QR → phone opens URL → getDisplayMedia → stream to monitor",
        "status": "spec_only",
    }


def screen_relay_snapshot(device: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = recommend_relay_path(device)
    return {
        "category": "screen_relay",
        "count": len(SCREEN_RELAY_THEORIES),
        "catalog": SCREEN_RELAY_THEORIES,
        "recommendation": rec,
        "specs": {
            "webrtc": webrtc_relay_spec(),
            "companion": companion_relay_spec(),
            "replaykit": replaykit_spec(),
            "qrHandoff": qr_handoff_spec(),
        },
        "honestLimit": "No theory bypasses OS consent for arbitrary devices. BLE finds them; Wi‑Fi/USB/HDMI shows them.",
    }
