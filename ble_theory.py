"""#houseofasher unified theory corpus — narrative → flaw → fix → code.

Every feature in this repo is documented as a theory chain:
  narrative  — what the operator wants to believe / accomplish
  flaw       — why reality or security blocks the fantasy
  flawType   — technical | security | privacy | legal | operational | ethical
  fix        — honest mitigation or compensating control in this codebase
  code       — where the fix lives (module.symbol)
  module     — source file
"""

from __future__ import annotations

from typing import Any, Literal

from ble_screen_relay import SCREEN_RELAY_THEORIES, recommend_relay_path

FlawType = Literal["technical", "security", "privacy", "legal", "operational", "ethical"]
Category = Literal["tactical", "passive", "gatt", "security", "privacy", "architecture", "operational", "screen_relay"]

# Tactical sci-fi theories (ble_sci_fi.py)
TACTICAL_THEORIES: list[dict[str, str]] = [
    {"id": "clone", "category": "tactical", "narrative": "Spot cloned emitters across random MACs", "flaw": "MAC randomization is intentional privacy", "flawType": "privacy", "fix": "Fingerprint + co-appearance clustering", "code": "ble_sci_fi.detect_clone_clusters", "module": "ble_sci_fi.py"},
    {"id": "spoof", "category": "tactical", "narrative": "Detect name impersonation", "flaw": "Generic BLE names collide; adv names are unauthenticated", "flawType": "security", "fix": "Watchlist name vs fingerprint mismatch alert", "code": "ble_sci_fi.detect_spoof", "module": "ble_sci_fi.py"},
    {"id": "resurrection", "category": "tactical", "narrative": "Track devices that die and return", "flaw": "Idle devices stop advertising", "flawType": "technical", "fix": "SIGNAL LOST / RESURRECTED chrono events", "code": "ble_sci_fi.SciFiEngine.tick_lost_devices", "module": "ble_sci_fi.py"},
    {"id": "dialect", "category": "tactical", "narrative": "Classify advertisement accent", "flaw": "No single standard payload", "flawType": "technical", "fix": "UUID + manufacturer rule labels", "code": "ble_sci_fi.classify_beacon_dialect", "module": "ble_sci_fi.py"},
    {"id": "pursuit", "category": "tactical", "narrative": "Predict target heading", "flaw": "RSSI is noisy indoors", "flawType": "technical", "fix": "Velocity vector with confidence band", "code": "ble_sci_fi.vector_pursuit", "module": "ble_sci_fi.py"},
    {"id": "geofence", "category": "tactical", "narrative": "Digital perimeter breach", "flaw": "No target GPS — only scanner position known", "flawType": "technical", "fix": "Scanner-zone + RSSI containment", "code": "ble_sci_fi.containment_geofence", "module": "ble_sci_fi.py"},
    {"id": "shadow", "category": "tactical", "narrative": "Follow target through hop relay", "flaw": "Need cooperative nodes; strangers won't relay", "flawType": "operational", "fix": "Fingerprint path across hop scanners", "code": "ble_sci_fi.shadow_track", "module": "ble_sci_fi.py"},
    {"id": "echo", "category": "tactical", "narrative": "Sonar-like ranging", "flaw": "BLE is not sonar", "flawType": "technical", "fix": "Multi-node RSSI delta trend", "code": "ble_sci_fi.echo_ranging", "module": "ble_sci_fi.py"},
    {"id": "quorum", "category": "tactical", "narrative": "Three scanners confirm contact", "flaw": "One radio can lie; quorum can still be fooled", "flawType": "security", "fix": "N-node mesh quorum promotion", "code": "ble_sci_fi.mesh_quorum", "module": "ble_sci_fi.py"},
    {"id": "custody", "category": "tactical", "narrative": "Scanner handoff chain", "flaw": "No GPS on targets", "flawType": "technical", "fix": "Last-heard-by scanner custody log", "code": "ble_sci_fi.SciFiEngine.update_custody", "module": "ble_sci_fi.py"},
    {"id": "deaddrop", "category": "tactical", "narrative": "Fixed listening posts", "flaw": "Need deployed hardware", "flawType": "operational", "fix": "hop_reporter --listening-post flag", "code": "hop_reporter.post_report", "module": "hop_reporter.py"},
    {"id": "replay", "category": "tactical", "narrative": "Rewind the battlefield", "flaw": "Live view is fleeting", "flawType": "technical", "fix": "Time-series replay buffer", "code": "ble_sci_fi.SciFiEngine.record_replay_frame", "module": "ble_sci_fi.py"},
    {"id": "protocol", "category": "tactical", "narrative": "Passive protocol fingerprint", "flaw": "Limited without connect", "flawType": "technical", "fix": "Deep adv UUID/manufacturer parse", "code": "ble_sci_fi.passive_protocol_profile", "module": "ble_sci_fi.py"},
    {"id": "cohort", "category": "tactical", "narrative": "Devices that travel together", "flaw": "Co-location ≠ relationship", "flawType": "ethical", "fix": "Co-occurrence cluster matrix", "code": "ble_sci_fi.build_cooccurrence_clusters", "module": "ble_sci_fi.py"},
    {"id": "battery", "category": "tactical", "narrative": "Battery drain oracle", "flaw": "Most devices hide battery", "flawType": "technical", "fix": "GATT battery or adv cadence inference", "code": "ble_sci_fi.battery_oracle", "module": "ble_sci_fi.py"},
    {"id": "cipher", "category": "tactical", "narrative": "Encrypted exfil channel", "flaw": "Plain ZIP leaks MACs; XOR cipher is not real crypto", "flawType": "security", "fix": "Password-scrambled export blob (lab-only)", "code": "ble_sci_fi.build_cipher_zip", "module": "ble_sci_fi.py"},
    {"id": "tomography", "category": "tactical", "narrative": "Through-wall heat grid", "flaw": "Not real X-ray", "flawType": "technical", "fix": "Multi-scanner RSSI zone map", "code": "ble_sci_fi.tomography_grid", "module": "ble_sci_fi.py"},
    {"id": "mind", "category": "tactical", "narrative": "Read device capabilities", "flaw": "Can't read thoughts; GATT may expose PII", "flawType": "privacy", "fix": "GATT + UUID capability map", "code": "ble_sci_fi.device_mind_reading", "module": "ble_sci_fi.py"},
    {"id": "worm", "category": "tactical", "narrative": "Domino infection spread", "flaw": "Only your nodes relay", "flawType": "operational", "fix": "Hop depth timeline visualization", "code": "ble_sci_fi.SciFiEngine.record_worm", "module": "ble_sci_fi.py"},
    {"id": "anomaly", "category": "tactical", "narrative": "Temporal hop inconsistency", "flaw": "Graph can reorder under race conditions", "flawType": "security", "fix": "Impossible depth jump flag", "code": "ble_sci_fi.detect_temporal_anomaly", "module": "ble_sci_fi.py"},
    {"id": "brief", "category": "tactical", "narrative": "Auto mission after-action report", "flaw": "Raw JSON is unreadable", "flawType": "operational", "fix": "Template intel brief generator", "code": "ble_sci_fi.generate_mission_brief", "module": "ble_sci_fi.py"},
    {"id": "fingerprint", "category": "tactical", "narrative": "Stable emitter signature", "flaw": "Fingerprint changes if adv payload changes", "flawType": "privacy", "fix": "Hash manufacturer + UUIDs + name pattern", "code": "ble_tactical.signal_fingerprint", "module": "ble_tactical.py"},
    {"id": "ghost_trail", "category": "tactical", "narrative": "Movement ghost trail", "flaw": "RSSI jitter looks like motion", "flawType": "technical", "fix": "Rolling RSSI trail with trend label", "code": "ble_tactical.movement_trend", "module": "ble_tactical.py"},
    {"id": "threat_tier", "category": "tactical", "narrative": "Automated threat scoring", "flaw": "Heuristics misclassify paired allies", "flawType": "ethical", "fix": "Tier from name source + watchlist + hop depth", "code": "ble_tactical.threat_tier", "module": "ble_tactical.py"},
    {"id": "interference", "category": "tactical", "narrative": "Electronic jamming detector", "flaw": "Can't detect real jammers cheaply", "flawType": "technical", "fix": "Contact-count volatility heuristic", "code": "ble_tactical.TacticalEngine.interference_level", "module": "ble_tactical.py"},
    {"id": "domino_breach", "category": "tactical", "narrative": "Deep hop breach chains", "flaw": "Depth ≠ compromise", "flawType": "ethical", "fix": "Path labels from cooperative graph only", "code": "ble_tactical.domino_breach_chains", "module": "ble_tactical.py"},
    {"id": "watchlist", "category": "tactical", "narrative": "Target lock watchlist", "flaw": "MAC rotates; lock may follow wrong emitter", "flawType": "privacy", "fix": "Operator-curated address list + alerts", "code": "ble_tactical.TacticalEngine.add_watchlist", "module": "ble_tactical.py"},
    {"id": "scenario", "category": "tactical", "narrative": "Mission scenario presets", "flaw": "Aggressive pull may alarm users", "flawType": "ethical", "fix": "silent_observe disables GATT connect", "code": "ble_tactical.SCENARIOS", "module": "ble_tactical.py"},
    {"id": "dossier", "category": "tactical", "narrative": "Per-device intel card", "flaw": "Aggregates sensitive fields in one view", "flawType": "privacy", "fix": "Structured dossier with honest disclaimers", "code": "ble_tactical.TacticalEngine.build_dossier", "module": "ble_tactical.py"},
    {"id": "exfil_zip", "category": "tactical", "narrative": "Mission exfil package", "flaw": "ZIP contains MACs, names, trails", "flawType": "security", "fix": "Local download only; optional cipher wrapper", "code": "ble_tactical.TacticalEngine.build_extraction_zip", "module": "ble_tactical.py"},
]

PASSIVE_THEORIES: list[dict[str, str]] = [
    {"id": "adv_archaeology", "category": "passive", "narrative": "Passive advertisement archaeology", "flaw": "Payloads are vendor-opaque without connect", "flawType": "technical", "fix": "Parse known Apple/Microsoft/Eddystone/iBeacon layouts", "code": "ble_adv_intel.build_passive_intel", "module": "ble_adv_intel.py"},
    {"id": "ibeacon", "category": "passive", "narrative": "iBeacon zone fingerprint", "flaw": "UUID/major/minor are public in cleartext adv", "flawType": "privacy", "fix": "Decode Apple 0x004C iBeacon frame", "code": "ble_adv_intel.parse_ibeacon", "module": "ble_adv_intel.py"},
    {"id": "eddystone", "category": "passive", "narrative": "Eddystone URL/UID/TLM", "flaw": "URL beacons can deanonymize venues", "flawType": "privacy", "fix": "Parse Eddystone service data frames", "code": "ble_adv_intel.parse_eddystone", "module": "ble_adv_intel.py"},
    {"id": "apple_continuity", "category": "passive", "narrative": "Apple continuity hints", "flaw": "Manufacturer bytes leak ecosystem presence", "flawType": "privacy", "fix": "Apple mfg opcode heuristics", "code": "ble_adv_intel.parse_apple_mfg", "module": "ble_adv_intel.py"},
    {"id": "swift_pair", "category": "passive", "narrative": "Microsoft Swift Pair surface", "flaw": "Pairing UX can be abused for confusion attacks", "flawType": "security", "fix": "Flag 0x0006 Microsoft mfg payloads", "code": "ble_adv_intel.parse_microsoft_mfg", "module": "ble_adv_intel.py"},
    {"id": "fast_pair", "category": "passive", "narrative": "Google Fast Pair surface", "flaw": "Fast Pair adv can identify device class", "flawType": "security", "fix": "Flag Google 0x00E0 / 0x018E mfg", "code": "ble_adv_intel.parse_google_fast_pair", "module": "ble_adv_intel.py"},
    {"id": "connectable_guess", "category": "passive", "narrative": "Connectable emitter guess", "flaw": "Connectable flag not always present", "flawType": "technical", "fix": "Infer from name + service UUID presence", "code": "ble_adv_intel.build_passive_intel", "module": "ble_adv_intel.py"},
    {"id": "naming_broadcast", "category": "passive", "narrative": "Resolve device callsign", "flaw": "Many devices hide name until bonded", "flawType": "privacy", "fix": "Broadcast → paired → GATT cascade", "code": "ble_device_naming.resolve_name", "module": "ble_device_naming.py"},
    {"id": "paired_registry", "category": "passive", "narrative": "Windows paired name lookup", "flaw": "Reads OS pairing DB — sensitive on shared PCs", "flawType": "privacy", "fix": "load_all_paired_names + lookup_paired_name", "code": "ble_paired_windows.load_all_paired_names", "module": "ble_paired_windows.py"},
]

GATT_THEORIES: list[dict[str, str]] = [
    {"id": "callsign", "category": "gatt", "narrative": "Device callsign", "flaw": "Often missing in adv", "flawType": "technical", "fix": "GATT 0x2A00 + OS name", "code": "ble_gatt_pull.READABLE_CHARS", "module": "ble_gatt_pull.py"},
    {"id": "appearance", "category": "gatt", "narrative": "Device class icon", "flaw": "Optional char", "flawType": "technical", "fix": "Read 0x2A01 appearance", "code": "ble_gatt_pull._decode_value", "module": "ble_gatt_pull.py"},
    {"id": "battery", "category": "gatt", "narrative": "Power cell status", "flaw": "Gated on phones; exposes usage patterns", "flawType": "privacy", "fix": "Battery 0x2A19 + notify sample", "code": "ble_gatt_pull._try_notify_sample", "module": "ble_gatt_pull.py"},
    {"id": "dossier_gatt", "category": "gatt", "narrative": "Asset dossier", "flaw": "Needs connect; serial is PII", "flawType": "privacy", "fix": "Device Information 0x180A", "code": "ble_gatt_pull.READABLE_CHARS", "module": "ble_gatt_pull.py"},
    {"id": "pnp", "category": "gatt", "narrative": "Exact product SKU", "flaw": "Rare on phones", "flawType": "technical", "fix": "PnP ID 0x2A50", "code": "ble_gatt_pull._decode_value", "module": "ble_gatt_pull.py"},
    {"id": "biometric", "category": "gatt", "narrative": "Live vitals", "flaw": "Wearable + bond; health data is sensitive", "flawType": "legal", "fix": "HR 0x2A37 read/notify", "code": "ble_gatt_pull.pull_device_data", "module": "ble_gatt_pull.py"},
    {"id": "fitness", "category": "gatt", "narrative": "Motion telemetry", "flaw": "Service-specific; may need authorization", "flawType": "privacy", "fix": "CSC/RSC/weight chars", "code": "ble_gatt_pull.READABLE_CHARS", "module": "ble_gatt_pull.py"},
    {"id": "medical", "category": "gatt", "narrative": "Med telemetry", "flaw": "Heavily gated; HIPAA-like sensitivity", "flawType": "legal", "fix": "Glucose/BP chars if exposed", "code": "ble_gatt_pull.READABLE_CHARS", "module": "ble_gatt_pull.py"},
    {"id": "atlas", "category": "gatt", "narrative": "Full GATT map", "flaw": "Slow on Windows; maps attack surface", "flawType": "security", "fix": "Enumerate all services/chars", "code": "ble_gatt_pull._build_gatt_atlas", "module": "ble_gatt_pull.py"},
    {"id": "hid", "category": "gatt", "narrative": "Input device profile", "flaw": "HID map reveals input capabilities", "flawType": "security", "fix": "HID service in atlas", "code": "ble_gatt_pull._build_gatt_atlas", "module": "ble_gatt_pull.py"},
    {"id": "stream", "category": "gatt", "narrative": "Live notify stream", "flaw": "Needs sustained connect", "flawType": "technical", "fix": "Sample notify on HR/battery", "code": "ble_gatt_pull._try_notify_sample", "module": "ble_gatt_pull.py"},
    {"id": "identity", "category": "gatt", "narrative": "True MAC after bond", "flaw": "Random MAC while scanning protects privacy", "flawType": "privacy", "fix": "resolvedAddress after connect", "code": "ble_gatt_pull.pull_device_data", "module": "ble_gatt_pull.py"},
    {"id": "exfil_tier", "category": "gatt", "narrative": "Classify exfil success", "flaw": "OPEN tier still may be mostly empty", "flawType": "operational", "fix": "OPEN/PARTIAL/LOCKED/UNKNOWN tiers", "code": "ble_gatt_pull._exfil_tier", "module": "ble_gatt_pull.py"},
    {"id": "auto_pull", "category": "gatt", "narrative": "Background GATT exfil", "flaw": "Connects without per-device consent", "flawType": "ethical", "fix": "Respect silent_observe; interval + SYNC batch", "code": "ble-scan-server.run_persistent_scan", "module": "ble-scan-server.py"},
]

SECURITY_THEORIES: list[dict[str, str]] = [
    {"id": "local_bind", "category": "security", "narrative": "Local-only command post", "flaw": "Binding 0.0.0.0 would expose BLE intel LAN-wide", "flawType": "security", "fix": "HTTP server on 127.0.0.1 only", "code": "ble-scan-server.main", "module": "ble-scan-server.py", "severity": "high"},
    {"id": "hop_report_unauth", "category": "security", "narrative": "Cooperative hop ingest", "flaw": "/api/hop/report accepts unsigned posts from LAN", "flawType": "security", "fix": "Trust cooperative nodes only — no auth token yet", "code": "ble-scan-server.Handler.do_POST", "module": "ble-scan-server.py", "severity": "medium"},
    {"id": "fake_listening_post", "category": "security", "narrative": "Listening post registration", "flaw": "Any reporter can claim --listening-post", "flawType": "security", "fix": "Operator deploys known nodeIds; graph is advisory", "code": "ble_sci_fi.SciFiEngine.register_listening_post", "module": "ble_sci_fi.py", "severity": "medium"},
    {"id": "cipher_xor_weak", "category": "security", "narrative": "Password exfil scramble", "flaw": "XOR+SHA256 key is not authenticated encryption", "flawType": "security", "fix": "Lab/demo only — use real secrets management in prod", "code": "ble_sci_fi.encrypt_package", "module": "ble_sci_fi.py", "severity": "high"},
    {"id": "cleartext_http", "category": "security", "narrative": "Local HUD API", "flaw": "No TLS on localhost — other local processes can sniff", "flawType": "security", "fix": "Loopback bind + single-user PC assumption", "code": "ble-scan-server.ThreadingHTTPServer", "module": "ble-scan-server.py", "severity": "low"},
    {"id": "sse_disclosure", "category": "security", "narrative": "War room SSE stream", "flaw": "Any local browser tab can subscribe to chrono", "flawType": "security", "fix": "Local-only /api/events/stream", "code": "ble-scan-server.Handler.do_GET", "module": "ble-scan-server.py", "severity": "low"},
    {"id": "gatt_unauth_read", "category": "security", "narrative": "GATT characteristic read", "flaw": "Many peripherals expose DIS without pairing", "flawType": "security", "fix": "Document exfilTier; phones usually block", "code": "ble_gatt_pull.pull_device_data", "module": "ble_gatt_pull.py", "severity": "medium"},
    {"id": "serial_exposure", "category": "security", "narrative": "Serial number harvest", "flaw": "0x2A25 serial enables device tracking", "flawType": "privacy", "fix": "Surface in intelSummary with disclaimer", "code": "ble_gatt_pull.READABLE_CHARS", "module": "ble_gatt_pull.py", "severity": "medium"},
    {"id": "adv_tracking", "category": "security", "narrative": "Passive adv tracking", "flaw": "Scanning profiles nearby people without consent", "flawType": "legal", "fix": "Consent-based tool; silent_observe for passive-only", "code": "ble_tactical.SCENARIOS.silent_observe", "module": "ble_tactical.py", "severity": "high"},
    {"id": "mac_rotation", "category": "security", "narrative": "Defeat MAC randomization", "flaw": "Fingerprinting undermines BLE privacy design", "flawType": "ethical", "fix": "Use only on owned/authorized assets", "code": "ble_tactical.signal_fingerprint", "module": "ble_tactical.py", "severity": "medium"},
    {"id": "rssi_tracking", "category": "security", "narrative": "RSSI proximity tracking", "flaw": "Distance estimate enables presence profiling", "flawType": "privacy", "fix": "Honest distanceNote + no target GPS claim", "code": "ble_distance.distance_payload", "module": "ble_distance.py", "severity": "medium"},
    {"id": "colocation_inference", "category": "security", "narrative": "Infer device home address", "flaw": "Co-location ≠ device's address", "flawType": "ethical", "fix": "contextNote explains scanner-only GPS", "code": "ble_location.location_context_for_device", "module": "ble_location.py", "severity": "medium"},
    {"id": "nominatim_leak", "category": "security", "narrative": "Reverse geocode scanner", "flaw": "Sends scanner GPS to OSM Nominatim", "flawType": "privacy", "fix": "User-agent + optional skip if offline", "code": "ble_location.reverse_geocode", "module": "ble_location.py", "severity": "low"},
    {"id": "paired_db_read", "category": "security", "narrative": "Windows pairing DB", "flaw": "Exposes names of user's paired devices", "flawType": "privacy", "fix": "Local enrichment only; never uploaded by default", "code": "ble_paired_windows.load_all_paired_names", "module": "ble_paired_windows.py", "severity": "medium"},
    {"id": "persistent_scan", "category": "security", "narrative": "Never-ending sweep", "flaw": "Continuous surveillance of radio environment", "flawType": "ethical", "fix": "Operator starts sweep; documented consent model", "code": "ble-scan-server.run_persistent_scan", "module": "ble-scan-server.py", "severity": "medium"},
    {"id": "spoof_name_attack", "category": "security", "narrative": "Advertised name spoofing", "flaw": "Adv names are not cryptographically bound", "flawType": "security", "fix": "spoofAlerts + fingerprint mismatch", "code": "ble_sci_fi.detect_spoof", "module": "ble_sci_fi.py", "severity": "medium"},
    {"id": "quorum_poison", "category": "security", "narrative": "Poison hop quorum", "flaw": "Fake hop node can inflate scannerCount", "flawType": "security", "fix": "Cooperative graph only; anomaly flags", "code": "ble_sci_fi.mesh_quorum", "module": "ble_sci_fi.py", "severity": "medium"},
    {"id": "mitm_gatt", "category": "security", "narrative": "GATT MITM on connect", "flaw": "BLE pairing absent — connect is opportunistic", "flawType": "security", "fix": "No pairing UI; read-only standard chars", "code": "ble_gatt_pull.pull_device_data", "module": "ble_gatt_pull.py", "severity": "medium"},
    {"id": "health_data", "category": "security", "narrative": "Health characteristic read", "flaw": "HR/glucose may violate medical privacy", "flawType": "legal", "fix": "Only read if exposed; show in tier LOCKED otherwise", "code": "ble_gatt_pull.READABLE_CHARS", "module": "ble_gatt_pull.py", "severity": "high"},
    {"id": "exfil_download", "category": "security", "narrative": "Browser exfil download", "flaw": "ZIP saved to disk contains full mission", "flawType": "security", "fix": "Operator-triggered /api/extract only", "code": "ble-scan-server.Handler.do_GET", "module": "ble-scan-server.py", "severity": "medium"},
]

ARCHITECTURE_THEORIES: list[dict[str, str]] = [
    {"id": "hop_graph", "category": "architecture", "narrative": "Domino hop topology", "flaw": "Graph is eventual-consistency under parallel reports", "flawType": "technical", "fix": "Thread-locked HopGraphState + live ingest", "code": "ble_hop_graph.HOP_GRAPH.ingest_pc_scan", "module": "ble_hop_graph.py"},
    {"id": "hop_reporter", "category": "architecture", "narrative": "Companion scanner relay", "flaw": "Reporter must reach server URL", "flawType": "operational", "fix": "hop_reporter --loop POST observations", "code": "hop_reporter.run_loop", "module": "hop_reporter.py"},
    {"id": "enrichment_merge", "category": "architecture", "narrative": "Unified device record", "flaw": "Stale pull data if adv changes", "flawType": "technical", "fix": "Re-merge on every adv + set_pulled_data", "code": "ble_enrichment.build_device_record", "module": "ble_enrichment.py"},
    {"id": "rssi_distance", "category": "architecture", "narrative": "Distance from RSSI", "flaw": "Path loss varies by environment", "flawType": "technical", "fix": "Log-distance model + clamp 0.1–500m", "code": "ble_distance.estimate_distance_meters", "module": "ble_distance.py"},
    {"id": "map_rings", "category": "architecture", "narrative": "Leaflet contact rings", "flaw": "Bearing on map is illustrative not GPS", "flawType": "ethical", "fix": "RSSI ring + hash bearing offset", "code": "tactical_hud.updateTacticalMap", "module": "tactical_hud.html"},
    {"id": "triangulation", "category": "architecture", "narrative": "Multi-scanner fusion", "flaw": "Not true trilateration without 3+ RSSI curves", "flawType": "technical", "fix": "Hop observation fusion along graph", "code": "ble_tactical.estimate_triangulation", "module": "ble_tactical.py"},
    {"id": "continuous_sweep", "category": "architecture", "narrative": "Perpetual scan loop", "flaw": "Radio never rests — battery/heat on adapter", "flawType": "operational", "fix": "PERSISTENT_SCAN + hop ingest interval", "code": "ble-scan-server.run_persistent_scan", "module": "ble-scan-server.py"},
    {"id": "sync_hops", "category": "architecture", "narrative": "Soft hop sync", "flaw": "Stop button doesn't stop radio", "flawType": "operational", "fix": "sync_flag triggers resolve + pull batch", "code": "ble-scan-server.ScanState.request_sync", "module": "ble-scan-server.py"},
]

ALL_THEORIES: list[dict[str, str]] = (
    TACTICAL_THEORIES
    + PASSIVE_THEORIES
    + GATT_THEORIES
    + SECURITY_THEORIES
    + ARCHITECTURE_THEORIES
    + SCREEN_RELAY_THEORIES
)

THEORY_BY_ID: dict[str, dict[str, str]] = {t["id"]: t for t in ALL_THEORIES}

# Back-compat exports for existing imports
THEORY_CATALOG = TACTICAL_THEORIES
PULL_THEORY_CATALOG = GATT_THEORIES
PASSIVE_THEORY_CATALOG = PASSIVE_THEORIES


def theories_by_category(category: str) -> list[dict[str, str]]:
    return [t for t in ALL_THEORIES if t.get("category") == category]


def theories_by_flaw_type(flaw_type: str) -> list[dict[str, str]]:
    return [t for t in ALL_THEORIES if t.get("flawType") == flaw_type]


def theories_for_module(module: str) -> list[dict[str, str]]:
    return [t for t in ALL_THEORIES if t.get("module", "").startswith(module)]


def theory_chain(theory: dict[str, str]) -> str:
    return (
        f"{theory.get('narrative')} → FLAW ({theory.get('flawType', '?')}): {theory.get('flaw')} "
        f"→ FIX: {theory.get('fix')} → CODE: {theory.get('code')}"
    )


def theory_snapshot() -> dict[str, Any]:
    flaw_types = sorted({t.get("flawType", "technical") for t in ALL_THEORIES})
    categories = sorted({t.get("category", "tactical") for t in ALL_THEORIES})
    return {
        "brand": "houseofasher",
        "pattern": "narrative → flaw → fix → code",
        "total": len(ALL_THEORIES),
        "categories": categories,
        "flawTypes": flaw_types,
        "tactical": TACTICAL_THEORIES,
        "passive": PASSIVE_THEORIES,
        "gatt": GATT_THEORIES,
        "security": SECURITY_THEORIES,
        "architecture": ARCHITECTURE_THEORIES,
        "screenRelay": SCREEN_RELAY_THEORIES,
        "all": ALL_THEORIES,
        "screenRelayNote": "BLE finds devices; Wi‑Fi/USB/HDMI/AirPlay/scrcpy show screens — always with user consent.",
        "note": "Sci-fi labels map to honest BLE limits. Security flaws include privacy, legal, and ethical classes.",
    }


def _has_beacon(passive: dict[str, Any] | None) -> bool:
    return bool(passive and passive.get("beacons"))


def _pulled_data(record: dict[str, Any]) -> dict[str, Any]:
    return (record.get("pulledData") or {}).get("data") or {}


def theories_for_device(record: dict[str, Any]) -> list[dict[str, str]]:
    """Attach applicable theory chains to a device record."""
    ids: list[str] = ["adv_tracking", "rssi_tracking", "mac_rotation"]
    passive = record.get("passiveIntel") or {}
    data = _pulled_data(record)
    tier = record.get("exfilTier", "PASSIVE_ONLY")

    if _has_beacon(passive):
        for b in passive.get("beacons") or []:
            bt = b.get("type", "")
            if "ibeacon" in bt.lower():
                ids.append("ibeacon")
            if "eddystone" in bt.lower():
                ids.append("eddystone")
    for hint in passive.get("ecosystemHints") or []:
        h = hint.lower()
        if "apple" in h:
            ids.append("apple_continuity")
        if "microsoft" in h or "swift" in h:
            ids.append("swift_pair")
        if "google" in h or "fast pair" in h:
            ids.append("fast_pair")

    if record.get("nameSource") == "paired":
        ids.append("paired_registry")
    if record.get("nameSource") == "broadcast":
        ids.append("naming_broadcast")

    if tier == "LOCKED":
        ids.extend(["gatt_unauth_read", "mitm_gatt", "gatt_screen_blocked", "locked_phone_path", "ble_to_wifi_handoff"])
    elif tier in ("OPEN", "PARTIAL"):
        ids.extend(["atlas", "dossier_gatt"])
    if tier == "PASSIVE_ONLY":
        ids.append("adv_archaeology")

    if data.get("serialNumber"):
        ids.append("serial_exposure")
    if data.get("heartRateBpm") is not None:
        ids.extend(["biometric", "health_data"])
    if data.get("glucoseMeasurement"):
        ids.append("medical")
    if data.get("resolvedAddress"):
        ids.append("identity")
    if data.get("batteryLevel") is not None:
        ids.append("battery")

    if record.get("onWatchlist"):
        ids.extend(["watchlist", "spoof"])
    if record.get("threatTier") == "breach":
        ids.append("domino_breach")
    if record.get("fingerprint"):
        ids.append("fingerprint")

    sci = record.get("sciFi") or {}
    if sci.get("spoof"):
        ids.append("spoof_name_attack")
    if (sci.get("quorum") or {}).get("quorumMet"):
        ids.append("quorum")
    if (sci.get("geofence") or {}).get("breach"):
        ids.append("geofence")

    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for tid in ids:
        if tid in seen:
            continue
        t = THEORY_BY_ID.get(tid)
        if t:
            seen.add(tid)
            out.append({**t, "chain": theory_chain(t)})
    return out


def security_summary(devices: list[dict[str, Any]]) -> dict[str, Any]:
    locked = sum(1 for d in devices if d.get("exfilTier") == "LOCKED")
    serials = sum(1 for d in devices if _pulled_data(d).get("serialNumber"))
    health = sum(1 for d in devices if _pulled_data(d).get("heartRateBpm") is not None)
    beacons = sum(len((d.get("passiveIntel") or {}).get("beacons") or []) for d in devices)
    high = [t for t in SECURITY_THEORIES if t.get("severity") == "high"]
    return {
        "devicesTracked": len(devices),
        "gattLocked": locked,
        "serialsExposed": serials,
        "healthReads": health,
        "beaconsDecoded": beacons,
        "highSeverityTheories": len(high),
        "operatorNote": "Use only on networks and devices you are authorized to assess.",
    }


def append_theory_brief(lines: list[str], devices: list[dict[str, Any]]) -> None:
    sec = security_summary(devices)
    lines.extend([
        "",
        "## Security & ethics posture",
        f"- Devices in sweep: {sec['devicesTracked']}",
        f"- GATT locked (blocked connect): {sec['gattLocked']}",
        f"- Serial numbers read: {sec['serialsExposed']}",
        f"- Health characteristic reads: {sec['healthReads']}",
        f"- Beacons decoded (passive): {sec['beaconsDecoded']}",
        f"- High-severity theory controls documented: {sec['highSeverityTheories']}",
        f"- {sec['operatorNote']}",
        "",
        "## Theory corpus",
        f"- Total narrative→flaw→fix→code chains: {len(ALL_THEORIES)}",
        f"- Categories: {', '.join(theory_snapshot()['categories'])}",
        f"- Flaw types: {', '.join(theory_snapshot()['flawTypes'])}",
    ])
