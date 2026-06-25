/**
 * PoseSense browser app — getUserMedia camera + MediaPipe pose → WebSocket fusion.
 */

import {
  FaceLandmarker,
  FilesetResolver,
  HandLandmarker,
  PoseLandmarker,
} from "@mediapipe/tasks-vision";

const canvas = document.getElementById("stageCanvas") as HTMLCanvasElement;
const ctx = canvas.getContext("2d", { alpha: true })!;
const video = document.getElementById("webcam") as HTMLVideoElement;
const bindBar = document.getElementById("bindBar")!;
const cameraStatus = document.getElementById("cameraStatus")!;
const cameraSelect = document.getElementById("cameraSelect") as HTMLSelectElement | null;

let ws: WebSocket | null = null;
let latestData: Record<string, unknown> | null = null;
let latestTargets: Array<Record<string, unknown>> = [];
let edgeGroups: Array<{ name: string; edges: number[][]; color: string }> = [];
let selectedPersonId: number | null = null;
let wallModeEnabled = true;
let localPersons: Array<Record<string, unknown>> = [];
let currentStream: MediaStream | null = null;
let activeDeviceId = "";
let mediaPipeReady = false;

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
  return { w: rect.width, h: rect.height };
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

/** Skeleton overlay only — video renders natively underneath. */
function drawOverlay(targets: Array<Record<string, unknown>>) {
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

async function openStream(deviceId?: string) {
  currentStream?.getTracks().forEach((t) => t.stop());
  const stream = await navigator.mediaDevices.getUserMedia({
    video: deviceId
      ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
      : { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
    audio: false,
  });
  currentStream = stream;
  video.srcObject = stream;
  video.setAttribute("playsinline", "true");
  await video.play();
  activeDeviceId = deviceId ?? stream.getVideoTracks()[0]?.getSettings().deviceId ?? "";
  cameraStatus.className = "camera-status ok";
}

async function fillCameraSelect() {
  if (!cameraSelect) return;
  const devices = (await navigator.mediaDevices.enumerateDevices())
    .filter((d) => d.kind === "videoinput" && d.deviceId);
  cameraSelect.innerHTML = devices
    .map((d, i) => {
      const label = d.label?.trim() || `Camera ${i + 1}`;
      return `<option value="${d.deviceId}" ${d.deviceId === activeDeviceId ? "selected" : ""}>${label}</option>`;
    })
    .join("");
  cameraSelect.disabled = devices.length <= 1;
}

async function loadMediaPipe() {
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm",
  );
  const opts = (path: string, delegate: "GPU" | "CPU") => ({
    baseOptions: { modelAssetPath: path, delegate },
    runningMode: "VIDEO" as const,
  });

  let delegate: "GPU" | "CPU" = "GPU";
  try {
    await PoseLandmarker.createFromOptions(vision, { ...opts(
      "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
      "GPU",
    ), numPoses: 2 });
  } catch {
    delegate = "CPU";
  }

  const poseLm = await PoseLandmarker.createFromOptions(vision, {
    ...opts("https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task", delegate),
    numPoses: 2,
  });
  const handLm = await HandLandmarker.createFromOptions(vision, {
    ...opts("https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task", delegate),
    numHands: 4,
  });
  const faceLm = await FaceLandmarker.createFromOptions(vision, {
    ...opts("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task", delegate),
    numFaces: 2,
  });

  mediaPipeReady = true;
  let ts = 0;

  const detect = () => {
    if (video.readyState < 2) return;
    ts += 33;
    const poseRes = poseLm.detectForVideo(video, ts);
    const handRes = handLm.detectForVideo(video, ts);
    const faceRes = faceLm.detectForVideo(video, ts);

    localPersons = (poseRes.landmarks ?? []).map((plm, i) => {
      const pose = plm.map((p, idx) => lm(p, String(idx)));
      return {
        person_id: i + 1,
        pose,
        face: faceRes.faceLandmarks?.[i]?.map((p) => lm(p)) ?? [],
        left_hand: handRes.landmarks?.[0]?.map((p) => lm(p)) ?? [],
        right_hand: handRes.landmarks?.[1]?.map((p) => lm(p)) ?? [],
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
        status_message: "Browser camera live",
        width: video.videoWidth,
        height: video.videoHeight,
        brightness: 128,
      },
    });
  };

  return detect;
}

async function startCamera() {
  await openStream();
  await fillCameraSelect();

  let detect: (() => void) | null = null;
  loadMediaPipe()
    .then((fn) => { detect = fn; })
    .catch((e) => {
      cameraStatus.className = "camera-status show";
      cameraStatus.textContent = `Pose tracking unavailable: ${e instanceof Error ? e.message : String(e)}. Camera feed still live.`;
    });

  const loop = () => {
    resizeCanvas();
    if (video.readyState >= 2 && video.videoWidth > 0) {
      detect?.();
      drawOverlay(latestTargets.length ? latestTargets : localPersons);
    }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

if (cameraSelect) {
  cameraSelect.addEventListener("change", async () => {
    const id = cameraSelect.value;
    if (!id || id === activeDeviceId) return;
    try {
      await openStream(id);
    } catch (e) {
      cameraStatus.className = "camera-status show";
      cameraStatus.textContent = `Camera switch failed: ${e instanceof Error ? e.message : String(e)}`;
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
  cameraStatus.textContent = `Camera blocked: ${e instanceof Error ? e.message : String(e)}. Allow camera in browser settings.`;
});
