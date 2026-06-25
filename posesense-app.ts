/**
 * PoseSense browser app — camera probe + native video + skeleton overlay.
 * Theory: narrative → flaw → fix → code (browser_camera_black)
 */

import {
  FaceLandmarker,
  FilesetResolver,
  HandLandmarker,
  PoseLandmarker,
} from "@mediapipe/tasks-vision";

import {
  BLACK_MEAN_THRESHOLD,
  listVideoDevices,
  openCameraStream,
  probeCameras,
  sampleBrightness,
  type VideoDevice,
} from "./camera-probe.js";

const canvas = document.getElementById("stageCanvas") as HTMLCanvasElement;
const ctx = canvas.getContext("2d", { alpha: true })!;
const video = document.getElementById("webcam") as HTMLVideoElement;
const bindBar = document.getElementById("bindBar")!;
const cameraStatus = document.getElementById("cameraStatus")!;
const cameraSelect = document.getElementById("cameraSelect") as HTMLSelectElement;
const brightnessChip = document.getElementById("brightnessChip")!;

const scratch = document.createElement("canvas");

let ws: WebSocket | null = null;
let latestData: Record<string, unknown> | null = null;
let latestTargets: Array<Record<string, unknown>> = [];
let edgeGroups: Array<{ name: string; edges: number[][]; color: string }> = [];
let wallModeEnabled = true;
let localPersons: Array<Record<string, unknown>> = [];
let currentStream: MediaStream | null = null;
let activeDeviceId = "";
let localBrightness = 0;
let mediaPipeReady = false;
let switchingCamera = false;

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

function cameraState(): { status: string; status_message: string; brightness: number } {
  if (switchingCamera) {
    return { status: "starting", status_message: "Switching camera…", brightness: localBrightness };
  }
  if (localBrightness >= BLACK_MEAN_THRESHOLD) {
    return { status: "live", status_message: "Browser camera live", brightness: localBrightness };
  }
  if (localBrightness > 0) {
    return {
      status: "black",
      status_message:
        "Camera is dark — pick USB FHD UVC from dropdown, close Zoom/Teams, or check privacy shutter.",
      brightness: localBrightness,
    };
  }
  return { status: "starting", status_message: "Starting camera…", brightness: 0 };
}

function updateCameraStatus(cam?: Record<string, unknown>) {
  const state = String(cam?.status ?? cameraState().status);
  const msg = String(cam?.status_message ?? cameraState().status_message);
  const bright = Number(cam?.brightness ?? localBrightness);
  brightnessChip.textContent = `${bright.toFixed(0)}/255`;
  brightnessChip.className = "brightness-chip " + (bright >= BLACK_MEAN_THRESHOLD ? "ok" : "warn");

  if (state === "live" && bright >= BLACK_MEAN_THRESHOLD) {
    cameraStatus.className = "camera-status ok";
    cameraStatus.textContent = "";
    return;
  }
  cameraStatus.className = "camera-status show";
  cameraStatus.textContent = msg;
}

function updateNarrative(n: Record<string, unknown>) {
  el("narrativeTitle").innerHTML = `<span>${n.icon ?? "◈"}</span> ${n.title ?? ""}`;
  (el("narrativeStory") as HTMLElement).textContent = String(n.story ?? "");
  (el("narrativeGuidance") as HTMLElement).textContent = String(n.guidance ?? "");
  (el("narrativePsych") as HTMLElement).textContent = String(n.psychology ?? "");

  const rail = el("journeyRail");
  rail.innerHTML = ((n.journey as Array<Record<string, unknown>>) ?? []).map((s) => `
    <div class="journey-step ${s.done ? "done" : ""} ${s.current ? "current" : ""}">
      <span class="icon">${s.icon}</span>
      <span class="label">${s.title}</span>
    </div>`).join("");

  const zones = n.zones as Record<string, Record<string, string>> | undefined;
  if (zones) {
    for (const [id, z] of [
      ["zonePerceive", zones.perceive],
      ["zoneUnderstand", zones.understand],
      ["zoneConnect", zones.connect],
    ] as const) {
      const node = el(id);
      if (!z) continue;
      node.className = "zone" + (z.status === "active" ? " active" : z.status === "ready" ? " ready" : "");
      node.querySelector(".zone-detail")!.textContent = z.detail ?? "";
    }
  }
}

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
    const bx = (1 - b.x - b.w) * w, by = b.y * h;
    ctx.strokeStyle = tgt.ble_address ? SKEL.linked : "#22d3ee";
    ctx.lineWidth = 2;
    ctx.strokeRect(bx, by, b.w * w, b.h * h);
  }
}

function renderUI() {
  const data = latestData;
  if (!data) return;

  if (data.narrative) updateNarrative(data.narrative as Record<string, unknown>);

  const theory = data.camera_theory as Record<string, unknown> | undefined;
  const chain = theory?.chain ?? theory
    ? `${theory?.narrative} → ${theory?.flaw} → ${theory?.fix} → ${theory?.code}`
    : "";
  (el("trustBody") as HTMLElement).textContent = [
    data.disclaimer ?? "",
    chain ? `\n\nTheory chain: ${chain}` : "",
    (data.ble_scan as Record<string, unknown>)?.tips
      ? `\n\nTips: ${((data.ble_scan as Record<string, unknown>).tips as string[]).join(" · ")}`
      : "",
  ].join("");

  updateCameraStatus((data.camera as Record<string, unknown>) ?? undefined);

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
}

function populateCameraSelect(devices: VideoDevice[], selectedId: string) {
  cameraSelect.innerHTML = devices
    .map((d) => `<option value="${d.deviceId}" ${d.deviceId === selectedId ? "selected" : ""}>${d.label}</option>`)
    .join("");
  cameraSelect.disabled = devices.length <= 1;
}

async function attachCamera(deviceId: string, label: string) {
  switchingCamera = true;
  updateCameraStatus();
  currentStream?.getTracks().forEach((t) => t.stop());
  const stream = await openCameraStream(deviceId);
  currentStream = stream;
  activeDeviceId = deviceId;
  video.srcObject = stream;
  video.setAttribute("playsinline", "true");
  await video.play();
  switchingCamera = false;
  cameraSelect.value = deviceId;
  localBrightness = 0;
  send({
    action: "pose_frame",
    persons: localPersons,
    camera: {
      ...cameraState(),
      width: video.videoWidth,
      height: video.videoHeight,
      device_label: label,
      device_id: deviceId,
    },
  });
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

async function startCamera() {
  // Permission unlocks device labels on Windows
  const boot = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  boot.getTracks().forEach((t) => t.stop());

  const devices = await listVideoDevices();
  const probe = await probeCameras(devices);
  const pick = probe ?? devices[0];
  if (!pick) throw new Error("No camera found");

  populateCameraSelect(devices, pick.deviceId);
  await attachCamera(pick.deviceId, pick.label);

  if (probe && !probe.ok) {
    cameraStatus.className = "camera-status show";
    cameraStatus.textContent = probe.note;
  }

  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm",
  );
  const poseLm = await PoseLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    numPoses: 2,
  });
  const handLm = await HandLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    numHands: 4,
  });
  const faceLm = await FaceLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    numFaces: 2,
  });
  mediaPipeReady = true;

  let ts = 0;
  let frameN = 0;
  const loop = () => {
    resizeCanvas();
    if (video.readyState >= 2 && video.videoWidth > 0) {
      frameN++;
      if (frameN % 3 === 0) {
        localBrightness = sampleBrightness(video, scratch);
        updateCameraStatus();
      }

      if (mediaPipeReady) {
        ts += 33;
        const poseRes = poseLm.detectForVideo(video, ts);
        const handRes = handLm.detectForVideo(video, ts);
        const faceRes = faceLm.detectForVideo(video, ts);

        localPersons = (poseRes.landmarks ?? []).map((plm, i) => {
          const pose = plm.map((p, idx) => lm(p, String(idx)));
          const face = faceRes.faceLandmarks?.[i]?.map((p) => lm(p)) ?? [];
          const lh = handRes.landmarks?.[0]?.map((p) => lm(p)) ?? [];
          const rh = handRes.landmarks?.[1]?.map((p) => lm(p)) ?? [];
          return {
            person_id: i + 1,
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

        send({
          action: "pose_frame",
          persons: localPersons,
          camera: {
            ...cameraState(),
            width: video.videoWidth,
            height: video.videoHeight,
            device_label: cameraSelect.selectedOptions[0]?.textContent ?? "",
            device_id: activeDeviceId,
          },
        });
      }

      const drawTargets = latestTargets.length ? latestTargets : localPersons;
      drawOverlay(drawTargets);
    }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

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
