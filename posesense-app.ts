/**
 * PoseSense browser app — getUserMedia camera + MediaPipe pose → WebSocket fusion.
 */

import {
  FilesetResolver,
  PoseLandmarker,
} from "@mediapipe/tasks-vision";

import {
  listCameras,
  openCameraDevice,
  pickWorkingCamera,
} from "./camera-utils.js";

const canvas = document.getElementById("stageCanvas") as HTMLCanvasElement;
const ctx = canvas.getContext("2d", { alpha: true })!;
const video = document.getElementById("webcam") as HTMLVideoElement;
const bindBar = document.getElementById("bindBar")!;
const cameraStatus = document.getElementById("cameraStatus")!;
const cameraSelect = document.getElementById("cameraSelect") as HTMLSelectElement | null;
const cameraHint = document.getElementById("cameraHint")!;

const scratch = document.createElement("canvas");

let ws: WebSocket | null = null;
let latestData: Record<string, unknown> | null = null;
let latestTargets: Array<Record<string, unknown>> = [];
let edgeGroups: Array<{ name: string; edges: number[][]; color: string }> = [];
let selectedPersonId: number | null = null;
let wallModeEnabled = true;
let localPersons: Array<Record<string, unknown>> = [];
let currentStream: MediaStream | null = null;
let activeDeviceId = "";
let activeLabel = "";

const SKEL: Record<string, string> = {
  torso: "#818cf8", left_arm: "#34d399", right_arm: "#fbbf24",
  left_leg: "#c084fc", right_leg: "#f472b6", head_neck: "#22d3ee",
  linked: "#4ade80",
};

function send(msg: Record<string, unknown>) {
  if (ws?.readyState === 1) ws.send(JSON.stringify(msg));
}

function el(id: string) { return document.getElementById(id)!; }

function stageSize() {
  const rect = canvas.parentElement!.getBoundingClientRect();
  return { w: Math.max(1, rect.width), h: Math.max(1, rect.height) };
}

function resizeCanvas() {
  const { w, h } = stageSize();
  const dpr = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();

function lm(p: { x: number; y: number; visibility?: number; presence?: number }, name?: string) {
  return { x: p.x, y: p.y, confidence: p.visibility ?? p.presence ?? 0.8, name };
}

function bboxFromPose(pts: Array<{ x: number; y: number; confidence?: number }>) {
  const vis = pts.filter((p) => (p.confidence ?? 0) > 0.2);
  if (!vis.length) return { x: 0.4, y: 0.2, w: 0.2, h: 0.6 };
  const xs = vis.map((p) => p.x), ys = vis.map((p) => p.y);
  const pad = 0.05;
  const x = Math.max(0, Math.min(...xs) - pad);
  const y = Math.max(0, Math.min(...ys) - pad);
  return { x, y, w: Math.min(1, Math.max(...xs) + pad) - x, h: Math.min(1, Math.max(...ys) + pad) - y };
}

function setCameraHint(text: string) {
  cameraHint.textContent = text;
}

function drawSkeleton(targets: Array<Record<string, unknown>>) {
  const { w, h } = stageSize();
  ctx.clearRect(0, 0, w, h);

  for (const tgt of targets) {
    const pose = (tgt.pose as Array<{ x: number; y: number; confidence?: number }>) ?? [];
    for (const g of edgeGroups) {
      ctx.strokeStyle = SKEL[g.name] ?? g.color;
      ctx.lineWidth = 2.5;
      ctx.shadowColor = ctx.strokeStyle;
      ctx.shadowBlur = 6;
      for (const [a, b] of g.edges) {
        const p1 = pose[a], p2 = pose[b];
        if (!p1 || !p2 || (p1.confidence ?? 0) < 0.2 || (p2.confidence ?? 0) < 0.2) continue;
        const x1 = (1 - p1.x) * w, y1 = p1.y * h;
        const x2 = (1 - p2.x) * w, y2 = p2.y * h;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    }
    ctx.shadowBlur = 0;

    const b = tgt.bbox as { x: number; y: number; w: number; h: number };
    ctx.strokeStyle = tgt.ble_address ? SKEL.linked : "#22d3ee";
    ctx.lineWidth = 2;
    ctx.strokeRect((1 - b.x - b.w) * w, b.y * h, b.w * w, b.h * h);
  }
}

function renderUI() {
  const data = latestData;
  if (!data) return;

  const narrative = data.narrative as Record<string, unknown>;
  el("narrativeTitle").innerHTML = `<span>${narrative.icon ?? "◈"}</span> ${narrative.title ?? ""}`;
  (el("narrativeStory") as HTMLElement).textContent = String(narrative.story ?? "");
  (el("narrativeGuidance") as HTMLElement).textContent = String(narrative.guidance ?? "");
  (el("trustBody") as HTMLElement).textContent = String(data.disclaimer ?? "");

  el("personCount").textContent = String(data.person_count ?? 0);
  el("deviceCount").textContent = String(data.device_count ?? 0);
  el("boundCount").textContent = String((data.bindings as unknown[])?.length ?? 0);
  el("countBadge").textContent = `${data.person_count} · ${data.device_count} signals`;

  const wifi = data.wifi as Record<string, unknown>;
  if (wifi) {
    (el("wifiMsg") as HTMLElement).textContent = String(wifi.message ?? "");
    el("wifiMotion").textContent = String(wifi.motion_energy ?? 0);
    el("wifiZone").textContent = String(wifi.zone ?? "—");
  }

  const suggestions = (data.bind_suggestions as Array<Record<string, unknown>>) ?? [];
  const targets = (data.targets as Array<Record<string, unknown>>) ?? [];
  if (suggestions.length && targets.length && !targets[0]?.ble_address) {
    const top = suggestions[0];
    bindBar.className = "bind-prompt active";
    bindBar.innerHTML = `Likely: <strong>${top.display_name}</strong> (${top.rssi} dBm) — tap a signal below or wait for auto-link.`;
  }

  const deviceList = el("deviceList");
  deviceList.innerHTML = "";
  for (const d of (data.unbound_devices as Array<Record<string, unknown>>) ?? []) {
    const li = document.createElement("li");
    li.className = (d.suggested ? "suggested " : "") + (d.is_phone ? "phone " : "");
    li.innerHTML = `<strong>${d.icon} ${d.display_name}</strong><span class="rssi">${d.rssi} dBm</span>
      <div class="sub">${d.brand ?? "?"} · ${d.device_type}</div>`;
    li.onclick = () => {
      const pid = selectedPersonId ?? targets[0]?.person_id;
      if (pid != null) send({ action: "bind", person_id: pid, address: d.address });
    };
    deviceList.appendChild(li);
  }
}

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => {
    el("pulseDot").classList.add("on");
    el("modeBadge").textContent = "Live · TS";
  };
  ws.onclose = () => setTimeout(connect, 2000);
  ws.onmessage = (ev) => {
    latestData = JSON.parse(ev.data);
    latestTargets = (latestData?.targets as Array<Record<string, unknown>>) ?? [];
    edgeGroups = (latestData?.pose_edge_groups as typeof edgeGroups) ?? [];
    renderUI();
  };
}

async function fillCameraSelect(selectedId: string) {
  if (!cameraSelect) return;
  const devices = await listCameras();
  cameraSelect.innerHTML = devices
    .map((d, i) => {
      const label = d.label || `Camera ${i + 1}`;
      return `<option value="${d.deviceId}" ${d.deviceId === selectedId ? "selected" : ""}>${label}</option>`;
    })
    .join("");
  cameraSelect.disabled = devices.length <= 1;
}

async function attachCamera(deviceId: string, label: string) {
  currentStream?.getTracks().forEach((t) => t.stop());
  currentStream = await openCameraDevice(deviceId, video);
  activeDeviceId = deviceId;
  activeLabel = label;
  cameraStatus.className = "camera-status ok";
  setCameraHint(`${label} · ${video.videoWidth || "?"}×${video.videoHeight || "?"}`);
  if (cameraSelect) cameraSelect.value = deviceId;
}

async function loadMediaPipe() {
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm",
  );
  const model = (path: string) => ({
    baseOptions: { modelAssetPath: path, delegate: "CPU" as const },
    runningMode: "VIDEO" as const,
  });

  const poseLm = await PoseLandmarker.createFromOptions(vision, {
    ...model("https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"),
    numPoses: 2,
  });

  let ts = 0;
  return () => {
    if (video.readyState < 2) return;
    ts += 33;
    const poseRes = poseLm.detectForVideo(video, ts);
    localPersons = (poseRes.landmarks ?? []).map((plm, i) => {
      const pose = plm.map((p, idx) => lm(p, String(idx)));
      return {
        person_id: i + 1,
        pose,
        face: [],
        left_hand: [],
        right_hand: [],
        bbox: bboxFromPose(pose),
        motion_energy: 0.2,
        metrics: {
          height_cm: null, weight_kg_est: null, face_width_cm: null, face_height_cm: null,
          visibility_score: 0.5, measurements_ready: false,
          visibility_message: "Stand fully in view for biometrics",
        },
      };
    });

    send({
      action: "pose_frame",
      persons: localPersons,
      camera: {
        status: "live",
        status_message: activeLabel,
        width: video.videoWidth,
        height: video.videoHeight,
        brightness: 128,
        device_label: activeLabel,
        device_id: activeDeviceId,
      },
    });
  };
}

async function startCamera() {
  cameraStatus.className = "camera-status show";
  cameraStatus.textContent = "Finding camera…";

  const picked = await pickWorkingCamera(video, scratch);
  currentStream = picked.stream;
  activeDeviceId = picked.deviceId;
  activeLabel = picked.label;

  await fillCameraSelect(activeDeviceId);
  cameraStatus.className = "camera-status ok";
  setCameraHint(`${picked.label} · ${video.videoWidth}×${video.videoHeight}`);

  if (picked.luma < 8) {
    cameraStatus.className = "camera-status show";
    cameraStatus.textContent =
      "Feed still dark — use the Camera dropdown and pick USB FHD UVC (not IR). Close Zoom/Teams if open.";
  }

  let detect: (() => void) | null = null;
  loadMediaPipe()
    .then((fn) => { detect = fn; })
    .catch(() => { /* camera works without pose */ });

  const loop = () => {
    resizeCanvas();
    if (video.readyState >= 2 && video.videoWidth > 0) {
      detect?.();
      drawSkeleton(latestTargets.length ? latestTargets : localPersons);
    }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

if (cameraSelect) {
  cameraSelect.addEventListener("change", async () => {
    const opt = cameraSelect.selectedOptions[0];
    if (!opt?.value || opt.value === activeDeviceId) return;
    try {
      await attachCamera(opt.value, opt.textContent ?? "Camera");
    } catch (e) {
      cameraStatus.className = "camera-status show";
      cameraStatus.textContent = `Switch failed: ${e instanceof Error ? e.message : String(e)}`;
    }
  });
}

el("wallModeBtn").addEventListener("click", () => {
  wallModeEnabled = !wallModeEnabled;
  send({ action: "set_wall_mode", enabled: wallModeEnabled });
  (el("wallModeBtn") as HTMLButtonElement).classList.toggle("active", wallModeEnabled);
});

connect();
startCamera().catch((e) => {
  cameraStatus.className = "camera-status show";
  cameraStatus.textContent = `Camera blocked: ${e instanceof Error ? e.message : String(e)}. Allow camera in browser settings for this site.`;
});
