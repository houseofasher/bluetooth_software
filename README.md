<div align="center">

# Bluetooth Scanning

**#houseofasher tactical BLE discovery — sci-fi HUD, domino hop chains, and honest device naming.**

[![Node.js 18+](https://img.shields.io/badge/node-18%2B-22c55e?style=for-the-badge&logo=nodedotjs&logoColor=white)](package.json)
[![TypeScript](https://img.shields.io/badge/stack-TypeScript-3178c6?style=for-the-badge&logo=typescript&logoColor=white)](package.json)
[![BLE](https://img.shields.io/badge/BLE-%40stoprocent%2Fnoble-8b5cf6?style=for-the-badge&logo=bluetooth&logoColor=white)](package.json)
[![Brand](https://img.shields.io/badge/%23houseofasher-tactical-ff3355?style=for-the-badge)](#tactical-operations-houseofasher)
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge)](#license)

[Quick Start](#quick-start) · [Tactical HUD](#tactical-operations-houseofasher) · [Hop map](#hop-map-domino-discovery) · [API](#api) · [Troubleshooting](#troubleshooting)

**Repos:** [shep95/bluetooth-scanning](https://github.com/shep95/bluetooth-scanning) · [houseofasher/bluetooth_software](https://github.com/houseofasher/bluetooth_software)

</div>

---

## Overview

**Bluetooth Scanning** is a consent-based, local-first BLE scanner for Windows. It discovers nearby Low Energy devices via **Node.js + @stoprocent/noble** (WinRT bindings), resolves human-readable names from multiple sources, and serves a live dashboard at `http://127.0.0.1:8765`.

| | |
|---|---|
| **Stack** | **100% TypeScript** — Node server, noble BLE, esbuild HUD bundles |
| **Scan model** | Continuous sweep — radio never stops; **SYNC HOPS** refreshes hop graph + GATT batch |
| **HUD** | Mission phases, chrono blackbox, Leaflet map, 3D hop battlefield, intel panels, sonar audio |
| **Naming** | Broadcast → paired registry → GATT → inference → MAC suffix |
| **Intel** | Passive adv archaeology + deep GATT pull + per-device theory chains |
| **Theories** | **111** narrative → flaw → fix → code chains (incl. PoseSense WiFi CSI + security) |
| **Privacy** | Runs on localhost; consent-based; `silent_observe` disables GATT connect |

---

## Architecture

```mermaid
flowchart TB
    subgraph UI["Browser UI :8765"]
        BTN[Start / Stop]
        LIST[Device list + name badges]
    end

    subgraph Server["src/server (Node)"]
        HTTP[HTTP API + static HUD]
        STATE[ScanState]
        SCAN[@stoprocent/noble]
        NAME[src/ble/device-naming]
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
- **Node.js 18+**
- Bluetooth **ON**
- Windows **Location** enabled (required for BLE scan on many builds)

### Install & run

```bash
git clone https://github.com/houseofasher/bluetooth_software.git
# or: git clone https://github.com/shep95/bluetooth-scanning.git
cd bluetooth-scanning  # or bluetooth_software
npm install
npm run build
npm start
```

Open **http://127.0.0.1:8765** — sweep **auto-starts** and runs forever (no device-count stop). Domino hop graph refreshes every 5s.

For multi-hop chains, run a companion in a loop:

```bash
# Phone / second PC as hop bridge
npm run hop -- --loop --node-id pixel-hop --label "Pixel 9" \
  --self-address C0:1C:6A:A4:93:C6 --server http://YOUR_PC_IP:8765

# Fixed listening post (dead drop)
npm run hop -- --loop --listening-post --node-id post-1 --label "Listening Post A" \
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
npm run hop -- --loop --node-id pixel-hop --label "Pixel 9" \
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
| **security** | 20 | `src/server`, `src/ble/theory.ts` | Local bind, hop report auth, XOR cipher limits, serial exposure |
| **screen_relay** | 20 | `ble_screen_relay.py` | scrcpy, AirPlay, WebRTC, HDMI, companion frame relay |
| **wifi_pose** | 10 | `ble_wifi_pose.py` | PoseSense — CMU WiFi CSI body pose + BLE identity fusion |
| **architecture** | 10 | `ble_hop_graph.py`, `ble_hop_merge.py` | Domino graph, hop merge to root mapper |

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

### PoseSense · WiFi body pose — Wayne / Dr. Emily

**Live implementation:** [`posesense/`](posesense/) — **100% TypeScript**. Browser camera + Node BLE fusion + WiFi CSI. Dashboard: **http://127.0.0.1:8766**

```bash
npm install && npm run build && npm start
```

Allow camera in the browser when prompted (fixes Windows OpenCV black-screen issues).

| Component | Stack |
|-----------|--------|
| Camera + pose | Browser MediaPipe (`posesense-app.ts`) |
| BLE | Node `@stoprocent/noble` |
| Fusion + WiFi CSI | `src/posesense/*.ts` |
| Live sync | WebSocket `/ws` on port 8766 |

**Narrative:** Carnegie Mellon University research showed **WiFi CSI** can reconstruct **full body pose** as someone moves in a room. Wayne's PoseSense idea: fuse that with BLE so you see **movement and identity** — who is where.

| Theory | Flaw | Fix in this repo |
|:---|:---|:---|
| PoseSense vision | BLE has no skeleton | WiFi CSI node + BLE fingerprint fusion |
| CMU WiFi pose | Commodity WiFi hides CSI | Cooperative ESP32 / research NIC → `--wifi esp32` |
| Through-wall | Camera is line-of-sight only | WiFi CSI ghost overlay when wall mode is on |
| Identity + pose | WiFi pose is anonymous | Click-to-bind BLE device to camera presence |
| Dr. Emily demo | Needs lab + consent | Ethical gate — cooperative subject only |

`GET /api/wifi/pose` — theory catalog. **Live PoseSense:** WebSocket on **8766** (`src/server/posesense-server.ts`).

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
`POST /api/screen/session` — create relay session + QR URL.  
`POST /api/screen/frame` — ingest JPEG from `/relay` sender page.  
`GET /api/screen/frame/latest?session=` — live feed for HUD monitor.

**Phone on Wi‑Fi:** restart server with LAN bind:
```powershell
$env:BLE_BIND_ALL="1"
npm start
```
Then HUD → **SCREEN RELAY** on a contact → scan QR → **START SHARE** on phone.

HUD: **SCREEN RELAY** button → QR + live viewer on your monitor.

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
| `GET` | `/api/wifi/pose` | PoseSense catalog + CMU WiFi CSI fusion spec |
| `POST` | `/api/wifi/pose` | CSI pose keyframe ingest (spec accept) |
| `GET` | `/api/theories` | Full 111-chain catalog + live `securitySummary` |
| `GET` | `/api/location` | Scanner GPS snapshot |
| `POST` | `/api/location` | Set scanner coords (browser geolocation) |
| `POST` | `/api/pull` | Manual GATT pull `{ "address": "..." }` |
| `GET` | `/relay` | Consent-based screen share sender (getDisplayMedia) |
| `POST` | `/api/screen/session` | Create relay session `{ "deviceAddress", "label" }` |
| `POST` | `/api/screen/frame` | Ingest JPEG frame `{ "sessionId", "frameJpeg" }` |
| `GET` | `/api/screen/frame/latest?session=` | Latest JPEG for HUD live viewer |
| `GET` | `/api/screen/sessions` | Active relay sessions |
| `GET` | `/api/screen/relay?address=` | Screen relay theories + consent-based mirror path |
| `GET` | `/api/events/stream` | SSE war room event stream |
| `POST` | `/api/scenario` | Set mission preset `{ "scenario": "perimeter" }` |
| `POST` | `/api/watchlist` | Target lock `{ "address": "...", "action": "toggle" }` |
| `POST` | `/api/stop` | SYNC HOPS — hop refresh + GATT batch (sweep continues) |

---

### TypeScript client (all API calls)

The HUD and screen relay pages load bundled JS from `dist/` — all `fetch()` calls go through `bluetooth-client.ts`.

```bash
npm run build    # dist/tactical-hud.js + dist/screen-relay.js
npm run typecheck
```

```typescript
import { BluetoothClient } from "./bluetooth-client";

const client = new BluetoothClient();

// Health & sweep
await client.checkHealth();
await client.triggerScan();
const snap = await client.getDevices();
await client.stopScan();

// Tactical & intel
await client.getTactical();
await client.getTheories();
await client.getDossier("AA:BB:CC:DD:EE:FF");
await client.pullDeviceData("AA:BB:CC:DD:EE:FF");
await client.setScenario("perimeter");
await client.toggleWatchlist("AA:BB:CC:DD:EE:FF");

// Location & hop
await client.setScannerLocation(40.44, -79.94, 12);
await client.getHopGraph();
await client.reportHop({ scannerId: "pixel-hop", devices: [] });

// Screen relay & PoseSense
await client.createScreenSession({ deviceAddress: "…", label: "Pixel 9" });
client.latestScreenFrameUrl(sessionId);
await client.postScreenFrame({ sessionId, frameJpeg: "…", width: 1080, height: 1920, ts: Date.now() });
await client.getScreenRelay("AA:BB:CC:DD:EE:FF");
await client.getWifiPose();

// Streams & exports
client.openWarRoomStream((e) => console.log(e.message));
window.location.href = client.extractionUrl("zip");
window.open(client.briefUrl(), "_blank");

// Programmatic polling helper
const scan = await client.startScan({
  onUpdate: (s) => console.log(s.missionLabel, s.tactical?.ticker, s.count),
});
await scan.stop();
```

---

## Hop map (domino discovery)

**Theory:** Each scanner hears nearby devices and **reports everything back to the root mapper** (your PC). Device 1 sees Device 2, Device 2 (if it's a cooperative hop node) POSTs that data home — domino chains extend the map.

**Reality:** Only **cooperative scanners** running `hop_reporter.py` relay data. Passive BLE peripherals (headphones, strangers' phones) do **not** run software — they appear as leaf nodes only when a hop scanner hears them.

```mermaid
flowchart LR
    subgraph Root["Root mapper (This PC)"]
        PC[BLE sweep + merge]
        API["/api/hop/report ingest"]
    end

    subgraph HopNode["Cooperative hop scanner (Pixel)"]
        PIX[hop_reporter.py --loop]
    end

    PC -->|hop 1 · direct radio| PIX
    PC -->|hop 1 · direct radio| A[Device A]

    PIX -->|POST all observations| API
    PIX -->|hop 1 · Pixel's radio| C[Device C]
    PIX -->|hop 1 · Pixel's radio| D[Device D]

    API --> PC
    PC -.->|merged hop 2| C
    PC -.->|merged hop 2| D
```

### Data flows back to root

| Scanner | What it reports | How |
|:---|:---|:---|
| **This PC** | Every BLE contact its radio hears | Auto every 5s via `ingest_hop_live()` |
| **Pixel / hop node** | **Every** device **it** hears | `POST /api/hop/report` with full `observations[]` |
| **Listening post** | Same — all contacts at fixed location | `hop_reporter.py --listening-post --loop` |

Root mapper **merges** all reports into one contact list (`hopRelay` in `/api/devices`). Devices only heard by a hop node show `nameSource: hop_relay` and `reportedByScanner` in the HUD.

### Run the hop chain

1. Start the server on your PC (root mapper). Sweep auto-runs.
2. On a phone or second PC on the **same network**, run a hop reporter — it brings back **all** devices it maps:

```bash
# Phone must reach PC — use LAN IP; set BLE_BIND_ALL=1 on server if needed
npm run hop -- --loop --node-id pixel-hop --label "Pixel 9" \
  --self-address C0:1C:6A:A4:93:C6 \
  --server http://192.168.1.10:8765
```

3. Open the HUD — **Signal contacts** includes hop-relayed devices. **Hop map** shows depth-2 chains like `This PC → Pixel 9 → Device C`.

| Flaw (raw theory) | Fix (this build) |
|---|---|
| Hop node hears devices root cannot | `hop_reporter` POSTs full observation list to root |
| Data scattered per scanner | `ble_hop_merge.merge_hop_relay_devices()` unifies `/api/devices` |
| Unlimited passive hops through strangers | Only registered `hop/report` nodes relay |
| Infinite distance | Each hop is still ~10–30 m radio; more hops = more of **your** scanners |

---

## Project layout

```
bluetooth-scanning/
├── src/
│   ├── server/           # HTTP API, scan loop (npm start)
│   ├── ble/              # Naming, GATT, hop graph, enrichment, theory
│   ├── engine/           # Tactical, sci-fi, screen-relay, wifi-pose
│   ├── cli/              # hop-reporter.ts (npm run hop)
│   └── data/             # theory-arrays.json (111 chains)
├── tactical_hud.html     # HUD shell → dist/tactical-hud.js
├── screen_relay.html     # Screen share sender
├── bluetooth-client.ts   # Browser API client
├── tactical-hud.ts       # HUD logic
├── screen-relay.ts       # Relay sender logic
├── package.json
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
| `GET` | `/api/theories` | 111 theory chains + security summary |

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
      111 theory chains
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

Tactical BLE discovery for Windows — honest naming, real radio physics, 111 narrative→flaw→fix→code chains, sci-fi presentation.

</div>
