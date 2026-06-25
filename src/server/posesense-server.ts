/** PoseSense live server — WebSocket fusion hub (TypeScript, port 8766). */

import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer, type WebSocket } from "ws";

import { normalizeMac } from "../ble/device-naming.js";
import { lookupPairedName } from "../ble/paired-windows.js";
import { STATE } from "../server/scan-state.js";
import { ensureScanLoop } from "../server/scanner.js";
import { classifyDevice } from "../posesense/ble-classifier.js";
import { FusionEngine } from "../posesense/fusion.js";
import { resolveNarrative } from "../posesense/narrative.js";
import { HAND_CONNECTIONS, POSE_EDGE_GROUPS } from "../posesense/skeleton.js";
import type { PersonDetection } from "../posesense/types.js";
import { WiFiCsiEngine } from "../posesense/wifi-csi-engine.js";
import { WiFiCsiSimulator } from "../posesense/wifi-csi-simulator.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../..");
const UI_DIR = join(ROOT, "posesense");
const DIST = join(ROOT, "dist");

export const POSESENSE_PORT = Number(process.env.POSESENSE_PORT ?? 8766);

const fusion = new FusionEngine();
const wifiEngine = new WiFiCsiEngine();
const wifiSim = new WiFiCsiSimulator((f) => wifiEngine.ingest(f), true);

let wallMode = true;
let latestPersons: PersonDetection[] = [];
let cameraMeta = { status: "starting", status_message: "Allow camera in browser", width: 1280, height: 720, brightness: 0 };

const clients = new Set<WebSocket>();

function readStatic(name: string, res: ServerResponse, contentType: string): boolean {
  const path = join(UI_DIR, name);
  if (!existsSync(path)) return false;
  const body = readFileSync(path);
  res.writeHead(200, { "Content-Type": contentType, "Content-Length": body.length, "Cache-Control": "no-cache" });
  res.end(body);
  return true;
}

function syncBleFromScanState(): void {
  const now = Date.now() / 1000;
  for (const d of STATE.devices.values()) {
    const address = normalizeMac(String(d.macAddress ?? d.id ?? ""));
    if (!address) continue;
    const name = String(d.name ?? d.displayName ?? "Unknown");
    const rssi = Number(d.rssi ?? -100);
    const mfg = (d.manufacturerData as Record<string, string>) ?? {};
    const paired = lookupPairedName(address, STATE.pairedNames);
    const meta = classifyDevice(name, mfg, address, paired ?? null);
    fusion.ingestBle(address, String(meta.display_name ?? name), rssi, now, meta);
  }
}

function throughWallTargets(wifi: Record<string, unknown>): Array<Record<string, unknown>> {
  if (!wifi.through_wall || Number(wifi.through_wall_confidence) < 0.3) return [];
  return [{
    id: "wifi-1", source: "wifi_csi", activity: wifi.activity, zone: wifi.zone,
    x: wifi.zone_x, y: 0.55, confidence: wifi.through_wall_confidence,
    label: `Body reflection (${wifi.activity})`,
  }];
}

function buildPayload(): Record<string, unknown> {
  syncBleFromScanState();
  const targets = fusion.update(latestPersons);
  const wifiState = wifiEngine.analyze(latestPersons.length, wallMode) as Record<string, unknown>;
  const unbound = fusion.unboundDevices(latestPersons);
  const hasMetrics = targets.some((t) => t.metrics.measurements_ready);
  const phoneNearby = unbound.some((d) => d.is_phone);

  const narrative = resolveNarrative({
    person_count: latestPersons.length,
    device_count: fusion.devices.size,
    binding_count: fusion.bindings.size,
    phone_nearby: phoneNearby,
    has_metrics: hasMetrics,
    wifi_occupied: Boolean(wifiState.occupied),
    through_wall: Boolean(wifiState.through_wall),
  });

  return {
    mode: "ble",
    timestamp: Date.now() / 1000,
    wall_mode: wallMode,
    narrative,
    wifi: { source: "sim", ...wifiState, through_wall_targets: throughWallTargets(wifiState) },
    camera: cameraMeta,
    targets,
    pose_edge_groups: POSE_EDGE_GROUPS,
    hand_edges: HAND_CONNECTIONS,
    unbound_devices: unbound,
    bind_suggestions: fusion.bindSuggestions(latestPersons),
    bindings: fusion.boundSummary(),
    person_count: latestPersons.length,
    device_count: fusion.devices.size,
    disclaimer:
      "Camera runs in your browser (getUserMedia). Bluetooth from Node noble scan. " +
      "WiFi CSI simulates body reflections through walls. All TypeScript — no Python.",
    ble_scan: {
      paired_devices: Object.keys(STATE.pairedNames).length,
      tips: ["Unlock phone for BLE name", "Hold phone up to auto-link", "Headphones in Radio Signatures"],
    },
  };
}

function broadcast(): void {
  const payload = JSON.stringify(buildPayload());
  for (const ws of clients) {
    if (ws.readyState === ws.OPEN) ws.send(payload);
  }
}

function handleCommand(msg: Record<string, unknown>): void {
  const action = msg.action;
  if (action === "bind") fusion.bindManual(Number(msg.person_id), String(msg.address));
  if (action === "unbind") fusion.unbind(Number(msg.person_id));
  if (action === "set_wall_mode") {
    wallMode = Boolean(msg.enabled ?? true);
    wifiSim.wallMode = wallMode;
  }
  if (action === "pose_frame") {
    latestPersons = (msg.persons as PersonDetection[]) ?? [];
    if (msg.camera && typeof msg.camera === "object") {
      cameraMeta = { ...cameraMeta, ...(msg.camera as typeof cameraMeta) };
    }
  }
}

export function createPoseSenseServer() {
  const server = createServer((req, res) => {
    const url = req.url ?? "/";
    if (req.method === "GET" && (url === "/" || url === "/posesense" || url === "/index.html")) {
      if (readStatic("index.html", res, "text/html; charset=utf-8")) return;
    }
    if (req.method === "GET" && url === "/theme-2027.css") {
      if (readStatic("theme-2027.css", res, "text/css; charset=utf-8")) return;
    }
    if (req.method === "GET" && (url === "/posesense.js" || url.startsWith("/posesense.js?"))) {
      try {
        const body = readFileSync(join(DIST, "posesense.js"));
        res.writeHead(200, {
          "Content-Type": "application/javascript; charset=utf-8",
          "Content-Length": body.length,
          "Cache-Control": "no-cache, no-store, must-revalidate",
        });
        res.end(body);
        return;
      } catch { /* fallthrough */ }
    }
    res.writeHead(404);
    res.end("Not found");
  });

  const wss = new WebSocketServer({ server, path: "/ws" });
  wss.on("connection", (ws) => {
    clients.add(ws);
    ws.send(JSON.stringify(buildPayload()));
    ws.on("message", (raw) => {
      try {
        const msg = JSON.parse(String(raw)) as Record<string, unknown>;
        handleCommand(msg);
      } catch { /* ignore */ }
    });
    ws.on("close", () => clients.delete(ws));
  });

  return server;
}

export async function startPoseSenseHub(): Promise<void> {
  ensureScanLoop();
  wifiSim.start();
  const server = createPoseSenseServer();
  await new Promise<void>((resolve) => server.listen(POSESENSE_PORT, "127.0.0.1", () => resolve()));
  setInterval(broadcast, 50);
  console.log(`PoseSense (TypeScript): http://127.0.0.1:${POSESENSE_PORT}/`);
}

export function stopPoseSenseHub(): void {
  wifiSim.stop();
}
