"""Cooperative BLE hop graph — domino-style multi-scanner topology."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

from ble_device_naming import format_mac, normalize_mac

NodeKind = Literal["scanner", "device"]
ROOT_NODE_ID = "pc-root"


@dataclass
class ScannerNode:
    node_id: str
    label: str
    self_address: str | None = None
    last_seen: float = 0.0
    is_root: bool = False


@dataclass
class HopEdge:
    from_id: str
    to_id: str
    rssi: int | None
    hop: int  # 1 = direct observation
    seen_at: float
    via_scanner: str


@dataclass
class HopGraphState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    scanners: dict[str, ScannerNode] = field(default_factory=dict)
    # scanner_id -> list of observations {address, name, rssi, seen_at}
    observations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    device_names: dict[str, str] = field(default_factory=dict)  # mac -> name

    def ensure_root(self) -> None:
        with self.lock:
            if ROOT_NODE_ID not in self.scanners:
                self.scanners[ROOT_NODE_ID] = ScannerNode(
                    node_id=ROOT_NODE_ID,
                    label="This PC",
                    is_root=True,
                    last_seen=time.time(),
                )

    def register_scanner_report(self, payload: dict[str, Any]) -> None:
        node_id = str(payload.get("nodeId") or "").strip()
        if not node_id:
            raise ValueError("nodeId is required")

        label = str(payload.get("nodeLabel") or node_id).strip()
        self_addr = payload.get("selfAddress")
        if self_addr:
            self_addr = format_mac(str(self_addr))

        obs = payload.get("observations") or []
        now = time.time()

        with self.lock:
            existing = self.scanners.get(node_id)
            self.scanners[node_id] = ScannerNode(
                node_id=node_id,
                label=label,
                self_address=self_addr or (existing.self_address if existing else None),
                last_seen=now,
                is_root=node_id == ROOT_NODE_ID or (existing.is_root if existing else False),
            )

            normalized: list[dict[str, Any]] = []
            for item in obs:
                addr = format_mac(str(item.get("address", "")))
                if not addr or addr.count(":") != 5:
                    continue
                name = item.get("name") or item.get("displayName")
                if name:
                    self.device_names[normalize_mac(addr)] = str(name)
                normalized.append(
                    {
                        "address": addr,
                        "name": name,
                        "rssi": item.get("rssi"),
                        "seen_at": float(item.get("seenAt", now * 1000)) / 1000.0
                        if item.get("seenAt")
                        else now,
                    }
                )
            self.observations[node_id] = normalized

    def ingest_pc_scan(self, devices: list[dict[str, Any]]) -> None:
        """Treat latest PC scan as a hop report from the root scanner."""
        observations = []
        for d in devices:
            addr = d.get("macAddress") or d.get("id")
            if not addr:
                continue
            observations.append(
                {
                    "address": format_mac(str(addr)),
                    "name": d.get("displayName") or d.get("name"),
                    "rssi": d.get("rssi"),
                    "seenAt": d.get("lastSeen"),
                }
            )
        self.register_scanner_report(
            {
                "nodeId": ROOT_NODE_ID,
                "nodeLabel": "This PC",
                "observations": observations,
            }
        )

    def _mac_to_node_id(self, mac: str) -> str:
        return f"dev:{normalize_mac(mac)}"

    def _scanner_for_mac(self, mac: str) -> str | None:
        nmac = normalize_mac(mac)
        for sid, scanner in self.scanners.items():
            if scanner.self_address and normalize_mac(scanner.self_address) == nmac:
                return sid
        return None

    def build_graph(self) -> dict[str, Any]:
        with self.lock:
            scanners = dict(self.scanners)
            observations = {k: list(v) for k, v in self.observations.items()}
            device_names = dict(self.device_names)

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[HopEdge] = []

        for sid, scanner in scanners.items():
            nodes[sid] = {
                "id": sid,
                "kind": "scanner",
                "label": scanner.label,
                "isRoot": scanner.is_root,
                "selfAddress": scanner.self_address,
                "lastSeen": scanner.last_seen,
            }

        # Direct edges: scanner -> device
        for sid, obs_list in observations.items():
            for obs in obs_list:
                addr = obs["address"]
                dev_id = self._mac_to_node_id(addr)
                name = obs.get("name") or device_names.get(normalize_mac(addr)) or addr
                if dev_id not in nodes:
                    nodes[dev_id] = {
                        "id": dev_id,
                        "kind": "device",
                        "label": name,
                        "address": addr,
                        "isRoot": False,
                        "lastSeen": obs.get("seen_at"),
                    }
                edges.append(
                    HopEdge(
                        from_id=sid,
                        to_id=dev_id,
                        rssi=obs.get("rssi"),
                        hop=1,
                        seen_at=float(obs.get("seen_at", time.time())),
                        via_scanner=sid,
                    )
                )

        # Bridge edges: heard device MAC == another scanner's identity → domino link
        bridge_edges: list[HopEdge] = []
        for sid, scanner in scanners.items():
            if not scanner.self_address:
                continue
            dev_id = self._mac_to_node_id(scanner.self_address)
            if dev_id in nodes:
                nodes[dev_id]["linkedScanner"] = sid
                nodes[dev_id]["kind"] = "bridge"
            bridge_edges.append(
                HopEdge(
                    from_id=dev_id,
                    to_id=sid,
                    rssi=None,
                    hop=0,
                    seen_at=scanner.last_seen,
                    via_scanner=sid,
                )
            )

        # BFS from root across observations + bridges
        paths: dict[str, list[str]] = {ROOT_NODE_ID: [ROOT_NODE_ID]}
        hop_depth: dict[str, int] = {ROOT_NODE_ID: 0}
        queue: deque[str] = deque([ROOT_NODE_ID])

        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            adjacency.setdefault(edge.from_id, []).append(edge.to_id)
        for edge in bridge_edges:
            if edge.from_id in nodes:
                adjacency.setdefault(edge.from_id, []).append(edge.to_id)

        while queue:
            current = queue.popleft()
            for target in adjacency.get(current, []):
                if target in hop_depth:
                    continue
                hop_depth[target] = hop_depth[current] + 1
                paths[target] = paths[current] + [target]
                queue.append(target)

        all_edges = edges + [e for e in bridge_edges if e.from_id in nodes]

        # Annotate devices with hop depth from root
        for nid, node in nodes.items():
            node["hopDepth"] = hop_depth.get(nid)
            node["pathFromRoot"] = paths.get(nid, [])

        chains = []
        for nid, depth in sorted(hop_depth.items(), key=lambda x: x[1]):
            if depth > 0 and nid.startswith("dev:"):
                chains.append(
                    {
                        "target": nodes.get(nid, {}).get("label", nid),
                        "targetId": nid,
                        "hopDepth": depth,
                        "path": [nodes.get(p, {}).get("label", p) for p in paths.get(nid, [])],
                    }
                )

        return {
            "rootId": ROOT_NODE_ID,
            "scannerCount": len(scanners),
            "nodeCount": len(nodes),
            "edgeCount": len(all_edges),
            "maxHopDepth": max(hop_depth.values()) if hop_depth else 0,
            "nodes": list(nodes.values()),
            "edges": [
                {
                    "from": e.from_id,
                    "to": e.to_id,
                    "rssi": e.rssi,
                    "hop": e.hop,
                    "viaScanner": e.via_scanner,
                    "seenAt": e.seen_at,
                }
                for e in all_edges
            ],
            "chains": chains,
            "note": (
                "Cooperative hop map: each scanner reports what it hears. "
                "Domino chains form when a heard device is also a registered hop scanner. "
                "Passive strangers cannot relay — only your registered nodes extend range."
            ),
        }

    def snapshot(self) -> dict[str, Any]:
        graph = self.build_graph()
        with self.lock:
            scanners = [
                {
                    "nodeId": s.node_id,
                    "label": s.label,
                    "selfAddress": s.self_address,
                    "isRoot": s.is_root,
                    "lastSeen": s.last_seen,
                    "observationCount": len(self.observations.get(s.node_id, [])),
                }
                for s in self.scanners.values()
            ]
        graph["scanners"] = sorted(scanners, key=lambda x: (not x["isRoot"], x["label"]))
        return graph


HOP_GRAPH = HopGraphState()
HOP_GRAPH.ensure_root()
