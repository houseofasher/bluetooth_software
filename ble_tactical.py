"""Sci-fi tactical layer — chrono log, fingerprints, trails, watchlist, scenarios, extraction."""

from __future__ import annotations

import hashlib
import io
import json
import math
import threading
import time
import zipfile
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

from ble_device_naming import DeviceSignals, format_mac, normalize_mac
from ble_sci_fi import SCI_FI, generate_mission_brief, build_cipher_zip
from ble_screen_relay import recommend_relay_path

MissionPhase = Literal["idle", "running", "resolving", "pulling", "completed", "failed"]
ThreatTier = Literal["friendly", "known", "unknown", "priority", "breach"]
MovementTrend = Literal["approaching", "receding", "static", "unknown"]
InterferenceLevel = Literal["clear", "elevated", "critical"]
ScenarioId = Literal["standard", "perimeter", "asset_recovery", "silent_observe", "deep_pull"]

MISSION_PHASE_LABELS: dict[str, str] = {
    "idle": "STANDBY",
    "running": "SWEEP",
    "resolving": "DECRYPT",
    "pulling": "EXFIL",
    "completed": "MISSION COMPLETE",
    "failed": "SIGNAL LOST",
}

SCENARIOS: dict[str, dict[str, Any]] = {
    "standard": {
        "label": "Standard sweep",
        "description": "Balanced discovery, name resolve, and GATT pull on stop.",
        "autoPullMax": 10,
        "gattOnStop": True,
        "proximityAlertRssi": -65,
        "audioEnabled": True,
    },
    "perimeter": {
        "label": "Perimeter watch",
        "description": "Aggressive proximity alerts; lighter GATT exfil.",
        "autoPullMax": 3,
        "gattOnStop": False,
        "proximityAlertRssi": -55,
        "audioEnabled": True,
    },
    "asset_recovery": {
        "label": "Asset recovery",
        "description": "Watchlist-only alerts; deep pull on known targets.",
        "autoPullMax": 15,
        "gattOnStop": True,
        "proximityAlertRssi": -70,
        "watchlistOnlyAlerts": True,
        "audioEnabled": True,
    },
    "silent_observe": {
        "label": "Silent observe",
        "description": "Passive sweep only — no GATT connect, no audio.",
        "autoPullMax": 0,
        "gattOnStop": False,
        "proximityAlertRssi": -60,
        "audioEnabled": False,
    },
    "deep_pull": {
        "label": "Deep exfil",
        "description": "Maximum GATT intelligence pull after stop.",
        "autoPullMax": 20,
        "gattOnStop": True,
        "proximityAlertRssi": -65,
        "audioEnabled": True,
    },
}

TRAIL_MAX_POINTS = 60
CHRONO_MAX_EVENTS = 500
INTERFERENCE_WINDOW = 20


def mission_label(phase: str) -> str:
    return MISSION_PHASE_LABELS.get(phase, phase.upper())


def threat_tier(
    name_source: str,
    proximity_zone: str,
    on_watchlist: bool,
    hop_depth: int | None = None,
) -> ThreatTier:
    if on_watchlist:
        return "priority"
    if hop_depth is not None and hop_depth >= 3:
        return "breach"
    if name_source in ("paired", "broadcast"):
        return "friendly" if proximity_zone == "immediate" else "known"
    if name_source in ("gatt", "inferred"):
        return "known"
    if proximity_zone == "immediate":
        return "unknown"
    return "unknown"


def signal_fingerprint(signals: DeviceSignals) -> str:
    mfg_keys = ",".join(str(k) for k in sorted(signals.manufacturer_data))
    parts = [
        signals.address,
        mfg_keys,
        signals.broadcast_name or "",
        ",".join(signals.uuids or []),
        str(signals.tx_power or ""),
    ]
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
    return f"SIG-{digest.upper()}"


def movement_trend(trail: list[dict[str, Any]]) -> MovementTrend:
    if len(trail) < 4:
        return "unknown"
    recent = [p["rssi"] for p in trail[-6:] if p.get("rssi") is not None]
    if len(recent) < 3:
        return "unknown"
    delta = recent[-1] - recent[0]
    if delta >= 5:
        return "approaching"
    if delta <= -5:
        return "receding"
    return "static"


def estimate_triangulation(
    device_mac: str,
    hop_graph: dict[str, Any],
) -> dict[str, Any] | None:
    """Rough multi-scanner RSSI fusion along hop topology (not GPS)."""
    nmac = normalize_mac(device_mac)
    nodes = {n["id"]: n for n in hop_graph.get("nodes", [])}
    observations: list[dict[str, Any]] = []

    for edge in hop_graph.get("edges", []):
        if edge.get("hop") != 1:
            continue
        to_id = edge.get("to", "")
        target = nodes.get(to_id)
        if not target or target.get("kind") not in ("device", "bridge"):
            continue
        addr = target.get("address", "")
        if not addr or normalize_mac(addr) != nmac:
            continue
        rssi = edge.get("rssi")
        if rssi is None:
            continue
        from_node = nodes.get(edge.get("from", ""), {})
        observations.append(
            {
                "scanner": from_node.get("label", edge.get("from")),
                "scannerId": edge.get("from"),
                "rssi": rssi,
                "hopDepth": from_node.get("hopDepth", 0),
            }
        )

    if len(observations) < 2:
        return None

    strongest = max(observations, key=lambda o: o["rssi"])
    weakest = min(observations, key=lambda o: o["rssi"])
    spread = strongest["rssi"] - weakest["rssi"]
    avg_rssi = sum(o["rssi"] for o in observations) / len(observations)
    est_m = max(1.0, min(50.0, 10 ** ((-59 - avg_rssi) / 20.0)))

    return {
        "method": "multi-scanner-rssi",
        "scannerCount": len(observations),
        "estimatedMeters": round(est_m, 1),
        "confidence": "high" if spread > 8 else "medium" if spread > 4 else "low",
        "note": "Relative battlefield coords from cooperative scanners — not street GPS.",
        "observations": observations,
    }


def relay_scores(hop_graph: dict[str, Any]) -> list[dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    for scanner in hop_graph.get("scanners", []):
        sid = scanner.get("nodeId", "")
        scores[sid] = {
            "nodeId": sid,
            "label": scanner.get("label", sid),
            "contacts": scanner.get("observationCount", 0),
            "bridges": 0,
            "score": 0,
            "uptime": "active" if scanner.get("lastSeen") else "unknown",
        }

    bridge_count = 0
    for node in hop_graph.get("nodes", []):
        if node.get("kind") == "bridge" and node.get("linkedScanner"):
            sid = node["linkedScanner"]
            if sid in scores:
                scores[sid]["bridges"] += 1
                bridge_count += 1

    for edge in hop_graph.get("edges", []):
        via = edge.get("viaScanner")
        if via and via in scores and edge.get("hop") == 1:
            scores[via]["contacts"] = max(scores[via]["contacts"], scores[via].get("contacts", 0))

    result = []
    for s in scores.values():
        s["score"] = s["contacts"] * 10 + s["bridges"] * 25
        result.append(s)
    return sorted(result, key=lambda x: x["score"], reverse=True)


def domino_breach_chains(hop_graph: dict[str, Any]) -> list[dict[str, Any]]:
    chains = hop_graph.get("chains", [])
    if not chains:
        return []

    enriched = []
    meters_per_hop = 15.0
    for chain in chains:
        depth = chain.get("hopDepth", 0)
        enriched.append(
            {
                **chain,
                "estimatedReachMeters": round(depth * meters_per_hop, 0),
                "breachLabel": f"CHAIN LENGTH {depth} · EST. REACH {int(depth * meters_per_hop)}m",
            }
        )
    return sorted(enriched, key=lambda c: c.get("hopDepth", 0), reverse=True)


@dataclass
class ChronoEvent:
    ts: float
    event_type: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "tsMs": int(self.ts * 1000),
            "type": self.event_type,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class TacticalEngine:
    lock: threading.Lock = field(default_factory=threading.Lock)
    scenario_id: ScenarioId = "standard"
    watchlist: set[str] = field(default_factory=set)
    chrono: deque[ChronoEvent] = field(default_factory=lambda: deque(maxlen=CHRONO_MAX_EVENTS))
    trails: dict[str, deque[dict[str, Any]]] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)
    fingerprint_history: dict[str, dict[str, Any]] = field(default_factory=dict)
    seen_macs: set[str] = field(default_factory=set)
    alerts: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=100))
    packet_samples: deque[tuple[float, int]] = field(default_factory=lambda: deque(maxlen=INTERFERENCE_WINDOW))
    last_device_count: int = 0
    mission_id: str = ""
    sse_subscribers: list[deque[str]] = field(default_factory=list)

    def current_scenario(self) -> dict[str, Any]:
        base = dict(SCENARIOS[self.scenario_id])
        base["id"] = self.scenario_id
        return base

    def set_scenario(self, scenario_id: str) -> dict[str, Any]:
        if scenario_id not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_id}")
        with self.lock:
            self.scenario_id = scenario_id  # type: ignore[assignment]
            self._log("scenario", f"Mission preset: {SCENARIOS[scenario_id]['label']}", {"scenario": scenario_id})
        return self.current_scenario()

    def add_watchlist(self, address: str) -> None:
        key = normalize_mac(address)
        with self.lock:
            self.watchlist.add(key)
            self._log("watchlist", f"Target locked: {format_mac(address)}", {"mac": format_mac(address)})

    def remove_watchlist(self, address: str) -> None:
        key = normalize_mac(address)
        with self.lock:
            self.watchlist.discard(key)

    def reset_mission(self) -> None:
        with self.lock:
            self.mission_id = f"MSN-{int(time.time())}"
            self.seen_macs.clear()
            self.trails.clear()
            self.packet_samples.clear()
            self.last_device_count = 0
            self._log("mission", "MISSION START — tactical sweep initiated", {"missionId": self.mission_id})
        SCI_FI.reset()

    def _log(self, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        event = ChronoEvent(time.time(), event_type, message, details or {})
        self.chrono.append(event)
        payload = json.dumps(event.to_dict())
        dead: list[deque[str]] = []
        for sub in self.sse_subscribers:
            if len(sub) > 200:
                dead.append(sub)
                continue
            sub.append(payload)
        for sub in dead:
            if sub in self.sse_subscribers:
                self.sse_subscribers.remove(sub)

    def log(self, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        with self.lock:
            self._log(event_type, message, details)

    def subscribe_sse(self) -> deque[str]:
        sub: deque[str] = deque(maxlen=200)
        with self.lock:
            self.sse_subscribers.append(sub)
        return sub

    def unsubscribe_sse(self, sub: deque[str]) -> None:
        with self.lock:
            if sub in self.sse_subscribers:
                self.sse_subscribers.remove(sub)

    def on_device_update(
        self,
        signals: DeviceSignals,
        record: dict[str, Any],
        hop_depth: int | None = None,
        hop_graph: dict[str, Any] | None = None,
        paired_names: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        mac = format_mac(signals.address)
        nmac = normalize_mac(mac)
        fp = signal_fingerprint(signals)
        now = time.time()

        with self.lock:
            self.fingerprints[nmac] = fp
            hist = self.fingerprint_history.setdefault(
                fp,
                {"fingerprint": fp, "firstSeen": now, "lastSeen": now, "macs": []},
            )
            hist["lastSeen"] = now
            if nmac not in hist["macs"]:
                hist["macs"].append(nmac)

            trail = self.trails.setdefault(nmac, deque(maxlen=TRAIL_MAX_POINTS))
            trail.append(
                {
                    "ts": now,
                    "rssi": signals.rssi,
                    "distanceMeters": record.get("distanceMeters"),
                }
            )

            is_new = nmac not in self.seen_macs
            if is_new:
                self.seen_macs.add(nmac)
                self._log(
                    "acquire",
                    f"SIGNAL ACQUIRED · {record.get('displayName', mac)}",
                    {"mac": mac, "rssi": signals.rssi, "fingerprint": fp},
                )

            on_watchlist = nmac in self.watchlist or fp in self.watchlist
            scenario = SCENARIOS[self.scenario_id]
            rssi_threshold = scenario.get("proximityAlertRssi", -65)
            watchlist_only = scenario.get("watchlistOnlyAlerts", False)

            if signals.rssi is not None and signals.rssi >= rssi_threshold:
                should_alert = on_watchlist or not watchlist_only
                if should_alert and (is_new or on_watchlist):
                    alert = {
                        "ts": now,
                        "type": "proximity",
                        "message": f"PERIMETER BREACH · {record.get('displayName', mac)} @ {signals.rssi} dBm",
                        "mac": mac,
                        "rssi": signals.rssi,
                        "priority": on_watchlist,
                    }
                    self.alerts.append(alert)
                    self._log("alert", alert["message"], alert)

        tier = threat_tier(
            record.get("nameSource", "address"),
            record.get("proximityZone", "unknown"),
            on_watchlist,
            hop_depth,
        )
        trend = movement_trend(list(self.trails.get(nmac, [])))

        sci = SCI_FI.analyze_device(
            signals,
            {**record, "fingerprint": fp, "ghostTrail": list(self.trails.get(nmac, [])), "hopDepth": hop_depth},
            hop_graph or {},
            paired_names or {},
            dict(self.fingerprints),
            self.log,
        )

        return {
            "threatTier": tier,
            "fingerprint": fp,
            "movementTrend": trend,
            "onWatchlist": on_watchlist,
            "ghostTrail": list(self.trails.get(nmac, [])),
            "knownEmitter": self.fingerprint_history.get(fp, {}).get("firstSeen", now) < now - 60,
            "sciFi": sci,
        }

    def on_name_resolved(self, mac: str, old_name: str, new_name: str, source: str) -> None:
        if old_name != new_name:
            self.log(
                "decrypt",
                f"NAME RESOLVED · {new_name} ({source})",
                {"mac": mac, "name": new_name, "source": source},
            )

    def on_phase_change(self, phase: str) -> None:
        self.log("phase", f"PHASE → {mission_label(phase)}", {"phase": phase, "missionLabel": mission_label(phase)})

    def on_scan_tick(self, device_count: int, devices: list[dict[str, Any]] | None = None, hop_graph: dict[str, Any] | None = None) -> None:
        now = time.time()
        with self.lock:
            self.packet_samples.append((now, device_count))
            self.last_device_count = device_count
        if devices is not None:
            SCI_FI.tick_presence(devices)
            active = {normalize_mac(d.get("macAddress") or d.get("id", "")) for d in devices}
            by_mac = {normalize_mac(d.get("macAddress") or d.get("id", "")): d for d in devices}
            SCI_FI.tick_lost_devices(active, by_mac, self.log)
            if hop_graph:
                SCI_FI.update_custody(devices, hop_graph)
                SCI_FI.record_worm(hop_graph.get("maxHopDepth", 0), hop_graph.get("nodeCount", 0))

    def interference_level(self) -> dict[str, Any]:
        with self.lock:
            samples = list(self.packet_samples)
        if len(samples) < 5:
            return {"level": "clear", "label": "SPECTRUM CLEAR", "score": 0}

        counts = [s[1] for s in samples]
        volatility = max(counts) - min(counts)
        recent_drop = counts[-1] < counts[0] - 3

        if recent_drop and volatility > 5:
            level: InterferenceLevel = "critical"
            label = "SPECTRUM NOISE CRITICAL"
        elif volatility > 3:
            level = "elevated"
            label = "SPECTRUM NOISE ELEVATED"
        else:
            level = "clear"
            label = "SPECTRUM CLEAR"

        return {"level": level, "label": label, "score": volatility, "samples": len(samples)}

    def build_dossier(self, record: dict[str, Any], hop_graph: dict[str, Any]) -> dict[str, Any]:
        mac = record.get("macAddress") or record.get("id", "")
        nmac = normalize_mac(mac)
        fp = self.fingerprints.get(nmac, "")
        trail = list(self.trails.get(nmac, []))
        tri = estimate_triangulation(mac, hop_graph) if mac else None

        nodes = {n["id"]: n for n in hop_graph.get("nodes", [])}
        dev_id = f"dev:{nmac}"
        path_labels = []
        if dev_id in nodes:
            path_ids = nodes[dev_id].get("pathFromRoot", [])
            path_labels = [nodes.get(p, {}).get("label", p) for p in path_ids]

        return {
            "mac": mac,
            "displayName": record.get("displayName"),
            "threatTier": record.get("threatTier"),
            "fingerprint": fp,
            "movementTrend": record.get("movementTrend"),
            "ghostTrail": trail[-20:],
            "hopPath": path_labels,
            "hopDepth": record.get("hopDepth"),
            "triangulation": tri,
            "passiveIntel": record.get("passiveIntel"),
            "exfilTier": record.get("exfilTier"),
            "intelSummary": record.get("intelSummary"),
            "charLabels": record.get("charLabels"),
            "gattAtlas": record.get("gattAtlas"),
            "pullStatus": record.get("pullStatus"),
            "pulledIntel": record.get("pulledData"),
            "theories": record.get("theories") or [],
            "screenRelay": recommend_relay_path(record),
            "firstSeenInMission": self.fingerprint_history.get(fp, {}).get("firstSeen"),
            "dossierNote": "Tactical intel card — MAC is hardware ID, not street address.",
        }

    def snapshot(self, phase: str, hop_graph: dict[str, Any], devices: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        with self.lock:
            chrono = [e.to_dict() for e in list(self.chrono)[-100:]]
            alerts = list(self.alerts)[-20:]
            watchlist = [format_mac(m) if len(m) == 12 else m for m in self.watchlist]
            fp_count = len(self.fingerprint_history)
            fp_by_mac = dict(self.fingerprints)

        sci_snap = SCI_FI.snapshot(
            devices or [],
            hop_graph,
            self.fingerprint_history,
            fp_by_mac,
        )

        return {
            "brand": "houseofasher",
            "missionId": self.mission_id,
            "missionPhase": phase,
            "missionLabel": mission_label(phase),
            "scenario": self.current_scenario(),
            "interference": self.interference_level(),
            "chrono": chrono,
            "alerts": alerts,
            "watchlist": watchlist,
            "fingerprintCount": fp_count,
            "relayScores": relay_scores(hop_graph),
            "dominoBreaches": domino_breach_chains(hop_graph),
            "ticker": chrono[-1]["message"] if chrono else "AWAITING ORDERS",
            "sciFi": sci_snap,
        }

    def record_replay(self, full_snapshot: dict[str, Any]) -> None:
        SCI_FI.record_replay_frame(full_snapshot)

    def build_extraction_package(
        self,
        scan_snapshot: dict[str, Any],
        hop_graph: dict[str, Any],
    ) -> dict[str, Any]:
        devices = scan_snapshot.get("devices", [])
        dossiers = [self.build_dossier(d, hop_graph) for d in devices]
        return {
            "brand": "houseofasher",
            "packageType": "tactical-exfil",
            "exportedAt": time.time(),
            "missionId": self.mission_id,
            "scenario": self.current_scenario(),
            "missionLabel": mission_label(scan_snapshot.get("phase", "completed")),
            "scannerLocation": scan_snapshot.get("scannerLocation"),
            "deviceCount": scan_snapshot.get("count", 0),
            "devices": devices,
            "dossiers": dossiers,
            "hopGraph": hop_graph,
            "dominoBreaches": domino_breach_chains(hop_graph),
            "relayScores": relay_scores(hop_graph),
            "chrono": [e.to_dict() for e in self.chrono],
            "interference": self.interference_level(),
            "sciFi": SCI_FI.snapshot(devices, hop_graph, self.fingerprint_history, dict(self.fingerprints)),
            "missionBrief": generate_mission_brief({
                "count": scan_snapshot.get("count", 0),
                "tactical": {"missionId": self.mission_id, "missionLabel": mission_label(scan_snapshot.get("phase", "completed")),
                             "dominoBreaches": domino_breach_chains(hop_graph), "chrono": [e.to_dict() for e in self.chrono]},
                "hopGraph": hop_graph,
            }),
        }

    def build_extraction_zip(self, package: dict[str, Any]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mission_intel.json", json.dumps(package, indent=2, default=str))
            zf.writestr(
                "chrono_blackbox.json",
                json.dumps(package.get("chrono", []), indent=2, default=str),
            )
            zf.writestr(
                "hop_graph.json",
                json.dumps(package.get("hopGraph", {}), indent=2, default=str),
            )
            zf.writestr("mission_brief.txt", package.get("missionBrief", ""))
            readme = (
                "# houseofasher tactical exfil package\n"
                f"Mission: {package.get('missionId')}\n"
                f"Devices: {package.get('deviceCount')}\n"
            )
            zf.writestr("README.txt", readme)
        return buf.getvalue()

    def build_cipher_exfil(self, package: dict[str, Any], password: str) -> bytes:
        return build_cipher_zip(package, password)


TACTICAL = TacticalEngine()
