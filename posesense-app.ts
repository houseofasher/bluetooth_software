/**
 * PoseSense browser app — getUserMedia camera + MediaPipe pose → WebSocket fusion.
 * 100% TypeScript (bundled to dist/posesense.js).
 */

import {
  FaceLandmarker,
  FilesetResolver,
  HandLandmarker,
  PoseLandmarker,
} from "@mediapipe/tasks-vision";

const canvas = document.getElementById("stageCanvas") as HTMLCanvasElement;
const ctx = canvas.getContext("2d")!;
const video = document.getElementById("webcam") as HTMLVideoElement;
const bindBar = document.getElementById("bindBar")!;
const cameraStatus = document.getElementById("cameraStatus")!;

let ws: WebSocket | null = null;
let latestData: Record<string, unknown> | null = null;
let selectedPersonId: number | null = null;
let selectedDeviceAddr: string | null = null;
let wallModeEnabled = true;
let personIdCounter = 1;

const SKEL: Record<string, string> = {
  torso: "#818cf8", left_arm: "#34d399", right_arm: "#fbbf24",
  left_leg: "#c084fc", right_leg: "#f472b6", head_neck: "#22d3ee",
  handL: "#34d399", handR: "#fbbf24", joint: "#fde68a", linked: "#4ade80",
};

function send(msg: Record<string, unknown>) {
  if (ws?.readyState === 1) ws.send(JSON.stringify(msg));
}

function resizeCanvas() {
  const rect = canvas.parentElement!.getBoundingClientRect();
  canvas.width = rect.width * devicePixelRatio;
  canvas.height = rect.height * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();

function lm(lm: { x: number; y: number; visibility?: number; presence?: number }, name?: string) {
  return { x: lm.x, y: lm.y, confidence: lm.visibility ?? lm.presence ?? 0.8, name };
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

function drawSkeleton(targets: Array<Record<string, unknown>>, edgeGroups: Array<{ name: string; edges: number[][]; color: string }>) {
  const w = canvas.width / devicePixelRatio;
  const h = canvas.height / devicePixelRatio;
  ctx.drawImage(video, 0, 0, w, h);

  for (const tgt of targets) {
    const pose = (tgt.pose as Array<{ x: number; y: number; confidence?: number }>) ?? [];
    for (const g of edgeGroups) {
      ctx.strokeStyle = SKEL[g.name] ?? g.color;
      ctx.lineWidth = 2.5;
      for (const [a, b] of g.edges) {
        const p1 = pose[a], p2 = pose[b];
        if (!p1 || !p2 || (p1.confidence ?? 0) < 0.2 || (p2.confidence ?? 0) < 0.2) continue;
        ctx.beginPath();
        ctx.moveTo(p1.x * w, p1.y * h);
        ctx.lineTo(p2.x * w, p2.y * h);
        ctx.stroke();
      }
    }
    const b = tgt.bbox as { x: number; y: number; w: number; h: number };
    ctx.strokeStyle = tgt.ble_address ? SKEL.linked : "#22d3ee";
    ctx.strokeRect(b.x * w, b.y * h, b.w * w, b.h * h);
  }
}

function el(id: string) { return document.getElementById(id)!; }

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
      if (selectedPersonId !== null) {
        send({ action: "bind", person_id: selectedPersonId, address: d.address });
        selectedPersonId = null;
      } else if (targets[0]) {
        send({ action: "bind", person_id: targets[0].person_id, address: d.address });
      }
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
    renderUI();
    drawSkeleton(
      (latestData?.targets as Array<Record<string, unknown>>) ?? [],
      (latestData?.pose_edge_groups as Array<{ name: string; edges: number[][]; color: string }>) ?? [],
    );
  };
}

async function startCamera() {
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 1280, height: 720 }, audio: false });
  video.srcObject = stream;
  await video.play();
  cameraStatus.className = "camera-status ok";

  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm",
  );
  const poseLm = await PoseLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task", delegate: "GPU" },
    runningMode: "VIDEO", numPoses: 2,
  });
  const handLm = await HandLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task", delegate: "GPU" },
    runningMode: "VIDEO", numHands: 4,
  });
  const faceLm = await FaceLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task", delegate: "GPU" },
    runningMode: "VIDEO", numFaces: 2,
  });

  let ts = 0;
  const loop = () => {
    if (video.readyState >= 2) {
      ts += 33;
      const poseRes = poseLm.detectForVideo(video, ts);
      const handRes = handLm.detectForVideo(video, ts);
      const faceRes = faceLm.detectForVideo(video, ts);

      const persons = (poseRes.landmarks ?? []).map((plm, i) => {
        const pose = plm.map((p, idx) => lm(p, String(idx)));
        const face = faceRes.faceLandmarks?.[i]?.map((p) => lm(p)) ?? [];
        const lh = handRes.landmarks?.[0]?.map((p) => lm(p)) ?? [];
        const rh = handRes.landmarks?.[1]?.map((p) => lm(p)) ?? [];
        return {
          person_id: personIdCounter,
          pose,
          face,
          left_hand: lh,
          right_hand: rh,
          bbox: bboxFromPose(pose),
          motion_energy: 0.2,
          metrics: {
            height_cm: null, weight_kg_est: null, face_width_cm: null, face_height_cm: null,
            visibility_score: 0.5, measurements_ready: false,
            visibility_message: "Stand fully in view for biometrics",
          },
        };
      });
      if (persons.length) personIdCounter = persons[0].person_id;

      send({
        action: "pose_frame",
        persons,
        camera: { status: "live", status_message: "Browser camera live", width: video.videoWidth, height: video.videoHeight, brightness: 128 },
      });

      if (latestData) {
        drawSkeleton(
          (latestData.targets as Array<Record<string, unknown>>)?.length ? (latestData.targets as Array<Record<string, unknown>>) : persons,
          (latestData.pose_edge_groups as Array<{ name: string; edges: number[][]; color: string }>) ?? [],
        );
      }
    }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

el("wallModeBtn").addEventListener("click", () => {
  wallModeEnabled = !wallModeEnabled;
  send({ action: "set_wall_mode", enabled: wallModeEnabled });
  (el("wallModeBtn") as HTMLButtonElement).classList.toggle("active", wallModeEnabled);
});

connect();
startCamera().catch((e) => {
  cameraStatus.className = "camera-status show";
  cameraStatus.textContent = `Camera blocked: ${e.message}. Allow camera in browser settings.`;
});
