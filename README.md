<div align="center">

# Bluetooth Scanning

**#houseofasher tactical BLE discovery — sci-fi HUD, domino hop chains, and honest device naming.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3b82f6?style=for-the-badge&logo=python&logoColor=white)](requirements.txt)
[![Platform](https://img.shields.io/badge/platform-Windows-0078d4?style=for-the-badge&logo=windows&logoColor=white)](#)
[![BLE](https://img.shields.io/badge/stack-bleak%20%2B%20WinRT-8b5cf6?style=for-the-badge&logo=bluetooth&logoColor=white)](#)
[![Brand](https://img.shields.io/badge/%23houseofasher-tactical-ff3355?style=for-the-badge)](#tactical-operations-houseofasher)
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge)](#license)

[Quick Start](#quick-start) · [Tactical HUD](#tactical-operations-houseofasher) · [Hop map](#hop-map-domino-discovery) · [API](#api) · [Troubleshooting](#troubleshooting)

**Repos:** [shep95/bluetooth-scanning](https://github.com/shep95/bluetooth-scanning) · [houseofasher/bluetooth_software](https://github.com/houseofasher/bluetooth_software)

</div>

---

## Overview

**Bluetooth Scanning** is a consent-based, local-first BLE scanner for Windows. It discovers nearby Low Energy devices through the OS Bluetooth stack (via [bleak](https://github.com/hbldh/bleak)), resolves human-readable names from multiple sources, and serves a live dashboard at `http://127.0.0.1:8765`.

| | |
|---|---|
| **Scan model** | Continuous sweep — radio never stops; **SYNC HOPS** refreshes hop graph + GATT batch |
| **HUD** | Mission phases, chrono blackbox, Leaflet map, 3D hop battlefield, intel panels, sonar audio |
| **Naming** | Broadcast → paired registry → GATT → inference → MAC suffix |
| **Intel** | Passive adv archaeology + deep GATT pull + per-device theory chains |
| **Theories** | **101** narrative → flaw → fix → code chains (incl. screen relay + security) |
| **Stack** | Python · bleak · WinRT · Leaflet · Three.js HUD · optional TypeScript client |
| **Privacy** | Runs on localhost; consent-based; `silent_observe` disables GATT connect |

---

## Architecture

```mermaid
flowchart TB
    subgraph UI["Browser UI :8765"]
        BTN[Start / Stop]
        LIST[Device list + name badges]
    end

    subgraph Server["ble-scan-server.py"]
        HTTP[Threading HTTP server]
        STATE[ScanState + lock]
        SCAN[BleakScanner active mode]
        NAME[ble_device_naming]
    end

    subgraph OS["Windows"]
        BT[Bluetooth radio]
        REG[(Paired device registry)]
        GATT[GATT Device Name 0x2A00]
    end

    BTN -->|POST /api/scan| HTTP
    HTTP -->|poll GET /api/devices| LIST
    HTTP --> STATE
    STATE --> SCAN
    SCAN --> BT
    STATE --> NAME
    NAME --> REG
    NAME --> GATT
    SCAN -->|advertisements| STATE
```

---

## Scan workflow

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Web UI
    participant API as HTTP API
    participant S as BleakScanner
    participant N as Name resolver

    U->>UI: Open localhost:8765
    UI->>API: GET /api/health
    API-->>UI: Bluetooth ready / off

    UI->>API: POST /api/scan (auto on boot)
    API->>S: Active scan (continuous)
    loop Forever until server stops
        S-->>API: Advertisement packets
        API->>API: Hop ingest every 5s
        API->>API: Background GATT pull every 45s
        UI->>API: Poll /api/devices
        API-->>UI: Live devices + passiveIntel + theories
    end
    U->>UI: SYNC HOPS
    UI->>API: POST /api/stop
    API->>API: Name merge + GATT pull batch (sweep continues)
    UI->>API: Poll /api/devices
    API-->>UI: Updated hop graph + exfil tiers
```

---

## Naming pipeline

Many BLE devices never broadcast a name. This project resolves **display names** in strict priority order:

```mermaid
flowchart LR
    A[Advertisement] --> B{broadcast name?}
    B -->|yes| Z[displayName]
    B -->|no| C{Windows paired?}
    C -->|yes| Z
    C -->|no| D{GATT 0x2A00?}
    D -->|yes| Z
    D -->|no| E{Manufacturer + services?}
    E -->|yes| Z[inferred label]
    E -->|no| F[BLE device · MAC suffix]
    F --> Z
```

| Priority | Source | Example | Badge |
|:---:|:---|:---|:---|
| 1 | **broadcast** | `Galaxy Buds` | `advertised` |
| 2 | **paired** | `Pixel 9` (Windows registry) | `paired` |
| 3 | **gatt** | Read from Device Name characteristic | `GATT name` |
| 4 | **inferred** | `Apple · Battery + HID` | `inferred` |
| 5 | **address** | `BLE device · A4:93:C6` | `address only` |

---

## Quick start

### Prerequisites

- **Windows 10/11** with Bluetooth adapter
- **Python 3.10+**
- Bluetooth **ON**
- Windows **Location** enabled (required for BLE scan on many builds)

### Install & run

```bash
git clone https://github.com/houseofasher/bluetooth_software.git
# or: git clone https://github.com/shep95/bluetooth-scanning.git
cd bluetooth-scanning  # or bluetooth_software
pip install -r requirements.txt
python ble-scan-server.py
```

Open **http://127.0.0.1:8765** — sweep **auto-starts** and runs forever (no device-count stop). Domino hop graph refreshes every 5s.

For multi-hop chains, run a companion in a loop:

```bash
# Phone / second PC as hop bridge
python hop_reporter.py --loop --node-id pixel-hop --label "Pixel 9" \
  --self-address C0:1C:6A:A4:93:C6 --server http://YOUR_PC_IP:8765

# Fixed listening post (dead drop)
python hop_reporter.py --loop --listening-post --node-id post-1 --label "Listening Post A" \
  --server http://YOUR_PC_IP:8765
```

### Tactical map (Leaflet)

Open the HUD → allow **Share scanner GPS** (auto-requested on load). The map shows:

| Map element | Meaning |
|-------------|---------|
| Green pin | Your PC scanner (real GPS) |
| Cyan dashed circle | 15 m co-location perimeter |
| Cyan pins + lines | Hop nodes with `--latitude` / `--longitude` |
| Colored rings + dots | BLE contacts at RSSI distance — bearing illustrative only |

```bash
python hop_reporter.py --loop --node-id pixel-hop --label "Pixel 9" \
  --latitude 40.7128 --longitude -74.0060 --server http://YOUR_PC_IP:8765
```

---

## Tactical operations (#houseofasher)

Sci-fi action layer on top of real BLE physics. Every feature maps to honest radio behavior — no fake X-ray or stranger relay.

```mermaid
flowchart TB
    subgraph HUD["Tactical HUD"]
        SWEEP[SWEEP phase]
        TICKER[Live ticker + chrono blackbox]
        BATTLE[3D hop battlefield]
        ALERT[Proximity alerts + sonar]
    end

    subgraph Intel["Intelligence"]
        DOSSIER[Device dossiers]
        FP[Signal fingerprints]
        TRAIL[Ghost trails / movement]
        TRI[Multi-scanner triangulation]
    end

    subgraph Mission["Mission control"]
        PRESET[Scenario presets]
        WATCH[Target lock watchlist]
        EXFIL[ZIP exfil package]
        SSE[War room SSE stream]
    end

    SWEEP --> Intel
    Intel --> Mission
```

### Narrative → flaw → fix → code

Every feature is documented as a **theory chain** in `ble_theory.py`:

```
narrative → flaw (technical | security | privacy | legal | ethical | operational) → fix → code
```

| Category | Count | Module | Examples |
|:---|:---:|:---|:---|
| **tactical** | 30 | `ble_sci_fi.py`, `ble_tactical.py` | Clone clusters, spoof alerts, ghost trails, cipher exfil |
| **passive** | 9 | `ble_adv_intel.py`, `ble_device_naming.py` | iBeacon, Eddystone, Apple continuity, Swift Pair |
| **gatt** | 14 | `ble_gatt_pull.py` | Battery, DIS dossier, HR notify, full GATT atlas |
| **security** | 20 | `ble-scan-server.py`, `ble_theory.py` | Local bind, hop report auth, XOR cipher limits, serial exposure |
| **screen_relay** | 20 | `ble_screen_relay.py` | scrcpy, AirPlay, WebRTC, HDMI, companion frame relay |

**Live catalog:** `GET /api/theories` — filterable in the HUD by flaw type (security, privacy, legal, etc.)

Each device record includes `theories[]` — applicable chains for that contact (beacons, exfil tier, watchlist, health reads, etc.).

### Security & ethics posture

| Theory | Flaw | Fix in code |
|:---|:---|:---|
| Passive adv tracking | Scanning profiles nearby people without consent | Consent-based tool; `silent_observe` scenario |
| MAC randomization defeat | Fingerprinting undermines BLE privacy design | Use only on owned/authorized assets |
| GATT unauth read | Peripherals may expose DIS without pairing | `exfilTier`: OPEN / PARTIAL / LOCKED |
| Serial number harvest | 0x2A25 enables device tracking | Surfaced in intel with disclaimer |
| Cipher exfil | XOR+SHA256 is not real encryption | Lab/demo only — `/api/extract?format=cipher` |
| Hop report unauth | `/api/hop/report` accepts unsigned LAN posts | Cooperative nodes only — no auth token yet |
| Local command post | Binding 0.0.0.0 would expose intel LAN-wide | HTTP server on `127.0.0.1` only |
| Co-location inference | Co-location ≠ device's home address | `contextNote` — scanner GPS only |

Mission brief (`GET /api/brief`) includes a **Security & ethics** section with live counts (GATT locked, serials read, health reads).

### Screen relay theories (`ble_screen_relay.py`) — 20 chains

**BLE cannot show another device's screen.** GATT `LOCKED` means the OS blocked connect — not pixels. To see a phone/laptop on your monitor you need a **consent-based video path**:

| Theory | Flaw | Fix (what actually works) |
|:---|:---|:---|
| BLE framebuffer | ~1 Mbps, no screen GATT char | BLE finds device; Wi‑Fi/USB carries video |
| GATT screen blocked | iOS/Android never expose display to strangers | Switch to AirPlay / scrcpy / WebRTC |
| Covert mirror | Illegal without consent | **Not supported** — own device or explicit approval |
| **scrcpy (Android)** | USB debugging + RSA approve | `scrcpy` after user taps Allow |
| **AirPlay (iOS)** | User must start Screen Mirroring | UxPlay / LonelyScreen receiver on PC |
| **WebRTC share** | User picks window in browser | `getDisplayMedia()` → planned `/api/screen/frame` |
| **HDMI capture** | Needs cable | Capture dongle → OBS / second monitor |
| **Windows project** | Same network | Win+K → project to this PC |
| **Companion relay** | Like hop_reporter for JPEG frames | User runs app + taps Share (planned) |
| **QR handoff** | Not automatic from scan | Phone scans QR on HUD → starts relay session |

`GET /api/screen/relay?address=` — platform guess + recommended path + operator steps.  
HUD: **SCREEN RELAY** button on `GATT LOCKED` contacts.

### Core tactical theories

| Theory | Flaw | Fix in code |
|:---|:---|:---|
| Emitter cloning | Random MACs | `cloneClusters` via fingerprint history |
| Spoof / mimic | Generic names | `spoofAlerts` when watchlist name ≠ signature |
| Resurrection | Idle devices vanish | `SIGNAL LOST` / `RESURRECTED` chrono |
| Beacon dialect | No standard payload | `dialect` tags from UUID rules |
| Vector pursuit | RSSI noise | `pursuit.bearing` + confidence |
| Containment geofence | No target GPS | RSSI perimeter breach on scanner zone |
| Shadow tracking | Needs hop nodes | `shadowPath` across domino graph |
| Echo ranging | BLE ≠ sonar | Multi-node RSSI delta trend |
| Mesh quorum | One radio lies | `CONFIRMED` when ≥2 scanners agree |
| Scanner custody | No target GPS | `custodyChains` handoff log |
| Dead drop posts | Need hardware | `hop_reporter.py --listening-post --loop` |
| Mission replay | Live view fleeting | `replayFrames` buffer + HUD scrubber |
| Protocol fingerprint | Limited passive data | `protocol` profile from adv bytes |
| Co-occurrence cohorts | Co-location ≠ bond | `cohortClusters` matrix |
| Battery oracle | Battery often hidden | GATT level or adv cadence inference |
| Cipher exfil | Plain ZIP leaks | `/api/extract?format=cipher&password=` |
| Tomography grid | Not X-ray | Multi-scanner RSSI heat map |
| Device mind reading | Can't read thoughts | `mind.capabilities` from GATT/UUIDs |
| Worm spread | Strangers won't relay | `wormTimeline` hop depth over time |
| Temporal anomaly | Graph reorders | Impossible hop depth jump flag |
| Mission brief | JSON unreadable | `GET /api/brief` auto after-action report |
| Threat board | Too many contacts | Rotating priority board in HUD |
| Voice commander | — | Web Speech: "sync hops", "status", "brief" |
| Red/blue team | — | Ally=blue, unknown=red, target=purple |
| Quantum decoherence | — | UI glitch when interference = critical |

### Passive intel (`ble_adv_intel.py`)

Decoded from advertisements **without GATT connect**:

| Signal | Parser | Security note |
|:---|:---|:---|
| iBeacon | `parse_ibeacon` | UUID/major/minor in cleartext adv |
| Eddystone UID/URL/TLM | `parse_eddystone` | URL beacons can deanonymize venues |
| Apple continuity | `parse_apple_mfg` | Manufacturer bytes leak ecosystem presence |
| Microsoft Swift Pair | `parse_microsoft_mfg` | Pairing UX confusion surface |
| Google Fast Pair | `parse_google_fast_pair` | Device class identification |

Shown per device in HUD **INTEL PANEL** as `passiveIntel`.

### GATT exfil (`ble_gatt_pull.py`)

| Exfil tier | Meaning |
|:---|:---|
| `PASSIVE_ONLY` | No connect attempted yet |
| `OPEN` | Readable standard characteristics |
| `PARTIAL` | Some chars + atlas mapped |
| `LOCKED` | Connect blocked (typical for unpaired phones) |

Readable characteristics include: device name, appearance, battery, DIS (manufacturer/model/serial/firmware), PnP ID, heart rate (read/notify sample), CSC/RSC/weight/glucose, and full **GATT atlas** (all services/chars).

Background pull: every 45s + on **SYNC HOPS**. Manual: **PULL GATT** per device or `POST /api/pull`.

### Extended sci-fi theories (`ble_sci_fi.py`)

| Phase | HUD label | Meaning |
|:---|:---|:---|
| `idle` | STANDBY | Ready |
| `running` | SWEEP | Continuous scan (never auto-stops) |
| `resolving` | DECRYPT | Name merge after SYNC HOPS |
| `pulling` | EXFIL | GATT intelligence pull (background) |
| `completed` | MISSION COMPLETE | Results final |
| `failed` | SIGNAL LOST | Radio error |

### Scenario presets

| ID | Use case |
|:---|:---|
| `standard` | Balanced sweep + GATT exfil |
| `perimeter` | Aggressive proximity alerts, light pull |
| `asset_recovery` | Watchlist alerts, deep pull |
| `silent_observe` | No GATT connect, passive only |
| `deep_pull` | Maximum GATT exfil on SYNC HOPS |

### Tactical API

| Method | Path | Description |
|:---:|:---|:---|
| `GET` | `/api/tactical` | Mission state, alerts, relay scores, domino breaches |
| `GET` | `/api/chrono` | Chrono blackbox events |
| `GET` | `/api/dossier?address=` | Full intel card + applicable theories |
| `GET` | `/api/extract?format=zip` | Download mission exfil package |
| `GET` | `/api/extract?format=cipher&password=` | Password-scrambled exfil ZIP (lab-only XOR) |
| `GET` | `/api/brief` | Plain-text mission after-action brief + security posture |
| `GET` | `/api/replay` | Time-dilated replay frame buffer |
| `GET` | `/api/theories` | Full 101-chain catalog + live `securitySummary` |
| `GET` | `/api/location` | Scanner GPS snapshot |
| `POST` | `/api/location` | Set scanner coords (browser geolocation) |
| `POST` | `/api/pull` | Manual GATT pull `{ "address": "..." }` |
| `GET` | `/api/screen/relay?address=` | Screen relay theories + consent-based mirror path |
| `GET` | `/api/events/stream` | SSE war room event stream |
| `POST` | `/api/scenario` | Set mission preset `{ "scenario": "perimeter" }` |
| `POST` | `/api/watchlist` | Target lock `{ "address": "...", "action": "toggle" }` |
| `POST` | `/api/stop` | SYNC HOPS — hop refresh + GATT batch (sweep continues) |

---

### TypeScript client (optional)

```typescript
import { BluetoothClient } from "./bluetooth-client";

const client = new BluetoothClient();
await client.setScenario("perimeter");

const scan = await client.startScan({
  onUpdate: (s) => console.log(s.missionLabel, s.tactical?.ticker, s.count),
});

await scan.stop();
window.location.href = client.extractionUrl("zip");
```

---

## Hop map (domino discovery)

**Theory:** Device 1 sees Device 2, Device 2 sees Device 3 — a domino chain that extends discovery beyond one radio.

**Reality:** Only **cooperative scanners** you register can hop. Strangers' phones do not relay.

```mermaid
flowchart LR
    PC[This PC scanner] -->|hop 1| B[Device B]
    B -->|bridge| PIX[Pixel hop scanner]
    PIX -->|hop 1| C[Device C]
    PIX -->|hop 1| D[Device D]
    PC -.->|hop 2 via bridge| C
    PC -.->|hop 2 via bridge| D
```

### Run the hop chain

1. Start the server and **Start scan** on your PC (root scanner).
2. On another machine or phone hotspot network, run a **hop reporter**:

```bash
# Example: Pixel as hop node 2 (use your PC's LAN IP if remote)
python hop_reporter.py --node-id pixel-hop --label "Pixel 9" \
  --self-address C0:1C:6A:A4:93:C6 \
  --server http://192.168.1.10:8765
```

3. Open the dashboard **Hop map** section — chains show `This PC → Pixel 9 → …`.

| Flaw (raw theory) | Fix (this build) |
|---|---|
| Unlimited passive hops through strangers | Only registered `hop/report` nodes |
| Infinite distance | Each hop is still ~10–30 m radio; more hops = more of your scanners |
| One scanner sees all | Server merges graphs from PC + companions |

---

## Project layout

```
bluetooth-scanning/
├── ble-scan-server.py      # HTTP server + persistent scan + auto GATT pull
├── tactical_hud.html       # #houseofasher tactical HUD (Leaflet map + intel panels)
├── ble_screen_relay.py     # Screen mirror theories (scrcpy, AirPlay, WebRTC, HDMI…)
├── ble_theory.py           # Unified 101-chain narrative→flaw→fix→code corpus
├── ble_tactical.py         # Chrono, fingerprints, trails, scenarios, exfil
├── ble_sci_fi.py           # Extended theory engine (clone, spoof, quorum, replay…)
├── ble_adv_intel.py        # Passive adv archaeology (iBeacon, Eddystone, mfg hints)
├── ble_gatt_pull.py        # Deep GATT exfil + service atlas + exfil tiers
├── ble_hop_graph.py        # Cooperative domino hop graph + relay scores
├── ble_location.py         # Scanner GPS + Nominatim reverse geocode
├── ble_distance.py         # RSSI → distance estimate + proximity zones
├── ble_enrichment.py       # Merge naming, distance, passive, GATT, theories
├── ble_device_naming.py    # Multi-source name resolution
├── ble_paired_windows.py   # Windows paired device registry lookup
├── hop_reporter.py         # Companion scanner CLI (hop node / listening post)
├── bluetooth-client.ts     # TypeScript API client
├── requirements.txt
└── README.md
```

---

## API

| Method | Path | Description |
|:---:|:---|:---|
| `GET` | `/` | Tactical HUD |
| `GET` | `/api/health` | Preflight Bluetooth radio check |
| `GET` | `/api/devices` | Full snapshot: devices, hopGraph, tactical, scannerLocation |
| `POST` | `/api/scan` | Ensure persistent sweep running (503 if Bluetooth off) |
| `POST` | `/api/stop` | SYNC HOPS — refresh names/hop graph/GATT batch; sweep continues |
| `POST` | `/api/pull` | Manual GATT pull `{ "address": "AA:BB:CC:DD:EE:FF" }` |
| `GET` | `/api/hop/graph` | Domino hop graph (nodes, edges, chains) |
| `POST` | `/api/hop/report` | Companion scanner submits observations |
| `GET` | `/api/theories` | 101 theory chains + security summary |

### Device object (selected fields)

```json
{
  "id": "C0:1C:6A:A4:93:C6",
  "displayName": "Pixel 9",
  "nameSource": "paired",
  "rssi": -62,
  "distanceLabel": "12 ft",
  "proximityZone": "near",
  "exfilTier": "LOCKED",
  "pullStatus": "failed",
  "threatTier": "known",
  "fingerprint": "SIG-A1B2C3D4E5F6",
  "passiveIntel": {
    "beacons": [],
    "ecosystemHints": ["Google Fast Pair"],
    "manufacturerRecords": [{ "companyName": "Google", "hex": "e000..." }]
  },
  "pulledData": { "ok": false, "exfilTier": "LOCKED", "errors": ["..."] },
  "gattAtlas": [],
  "intelSummary": [],
  "theories": [
    {
      "id": "adv_tracking",
      "flawType": "legal",
      "narrative": "Passive adv tracking",
      "flaw": "Scanning profiles nearby people without consent",
      "fix": "Consent-based tool; silent_observe for passive-only",
      "code": "ble_tactical.SCENARIOS.silent_observe",
      "chain": "Passive adv tracking → FLAW (legal): ... → FIX: ... → CODE: ..."
    }
  ],
  "sciFi": { "dialect": { "dialect": "WEARABLE" }, "quorum": { "status": "PENDING" } }
}
```

### Scan phases

| Phase | Meaning |
|:---|:---|
| `idle` | Ready for new scan |
| `running` | Collecting advertisements (continuous) |
| `resolving` | Name merge after SYNC HOPS |
| `pulling` | Background GATT pull in progress |
| `completed` | Results final |
| `failed` | Bluetooth or scan error |

---

## Troubleshooting

<details>
<summary><strong>Health check says Bluetooth is OFF</strong></summary>

Settings → **Bluetooth & devices** → turn Bluetooth **On**, then refresh the page.
</details>

<details>
<summary><strong>Scan completes with 0 devices</strong></summary>

1. Confirm health banner is green  
2. Enable **Location** in Windows Settings → Privacy  
3. Ensure a BLE device is nearby and advertising (phone, watch, headphones)  
4. Stay within ~10 m of the device
</details>

<details>
<summary><strong>Devices show inferred names instead of real names</strong></summary>

That device is not broadcasting its name and is not paired with this PC. Pair it in Windows Bluetooth settings, or rely on GATT resolution (automatic for the strongest unresolved devices).
</details>

<details>
<summary><strong>Port 8765 already in use</strong></summary>

```bash
# Windows PowerShell
Get-NetTCPConnection -LocalPort 8765 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```
</details>

---

## Design principles

```mermaid
mindmap
  root((Bluetooth Scanning))
    Consent
      Operator starts sweep
      silent_observe mode
      Authorized assets only
    Accuracy
      Multi packet merge
      Paired registry lookup
      GATT + passive enrichment
    Clarity
      nameSource badges
      exfilTier labels
      101 theory chains
    Security
      localhost bind
      flawType catalog
      ethics in brief
    Local
      127.0.0.1 only
      No cloud telemetry
      Optional Nominatim geocode
```

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**#houseofasher** · [shep95/bluetooth-scanning](https://github.com/shep95/bluetooth-scanning) · [houseofasher/bluetooth_software](https://github.com/houseofasher/bluetooth_software)

Tactical BLE discovery for Windows — honest naming, real radio physics, 101 narrative→flaw→fix→code chains, sci-fi presentation.

</div>
