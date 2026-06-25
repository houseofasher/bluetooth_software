/**
 * Browser camera probe — finds color FHD webcam vs IR/black sensor (Windows UVC).
 * narrative → flaw → fix → code (see src/posesense/camera-theory.ts)
 */

export const BLACK_MEAN_THRESHOLD = 8;

export interface VideoDevice {
  deviceId: string;
  label: string;
}

export interface ProbeResult {
  deviceId: string;
  label: string;
  brightness: number;
  note: string;
  ok: boolean;
}

const ADVANCED: MediaTrackConstraints = {
  width: { ideal: 1280 },
  height: { ideal: 720 },
  frameRate: { ideal: 30 },
  // @ts-expect-error exposure / white balance — helps some UVC webcams
  exposureMode: "continuous",
  whiteBalanceMode: "continuous",
};

export function sampleBrightness(video: HTMLVideoElement, scratch: HTMLCanvasElement): number {
  if (video.readyState < 2 || video.videoWidth <= 0) return 0;
  const ctx = scratch.getContext("2d", { willReadFrequently: true });
  if (!ctx) return 0;
  const w = 160;
  const h = Math.max(1, Math.round(w * (video.videoHeight / video.videoWidth)));
  scratch.width = w;
  scratch.height = h;
  ctx.drawImage(video, 0, 0, w, h);
  const px = ctx.getImageData(0, 0, w, h).data;
  let sum = 0;
  const n = px.length / 4;
  for (let i = 0; i < px.length; i += 4) {
    sum += (px[i]! + px[i + 1]! + px[i + 2]!) / 3;
  }
  return n ? sum / n : 0;
}

export async function listVideoDevices(): Promise<VideoDevice[]> {
  const all = await navigator.mediaDevices.enumerateDevices();
  return all
    .filter((d) => d.kind === "videoinput" && d.deviceId)
    .map((d, i) => ({
      deviceId: d.deviceId,
      label: d.label?.trim() || `Camera ${i + 1}`,
    }));
}

export async function openCameraStream(deviceId?: string): Promise<MediaStream> {
  const video: MediaTrackConstraints = deviceId
    ? { deviceId: { exact: deviceId }, ...ADVANCED }
    : { facingMode: "user", ...ADVANCED };
  return navigator.mediaDevices.getUserMedia({ video, audio: false });
}

async function warmupBrightness(
  video: HTMLVideoElement,
  scratch: HTMLCanvasElement,
  frames = 6,
): Promise<number> {
  let best = 0;
  for (let i = 0; i < frames; i++) {
    await new Promise<void>((r) => requestAnimationFrame(() => r()));
    best = Math.max(best, sampleBrightness(video, scratch));
    if (best >= BLACK_MEAN_THRESHOLD) break;
  }
  return best;
}

async function tryDevice(
  device: VideoDevice,
  scratch: HTMLCanvasElement,
  probeVideo: HTMLVideoElement,
): Promise<ProbeResult | null> {
  let stream: MediaStream | null = null;
  try {
    stream = await openCameraStream(device.deviceId);
    probeVideo.srcObject = stream;
    await probeVideo.play();
    await new Promise((r) => setTimeout(r, 200));
    const brightness = await warmupBrightness(probeVideo, scratch);
    const ok = brightness >= BLACK_MEAN_THRESHOLD;
    const note = ok
      ? `${device.label} ready (brightness ${brightness.toFixed(0)})`
      : `${device.label} opens but image is dark (${brightness.toFixed(0)}/255)`;
    return { deviceId: device.deviceId, label: device.label, brightness, note, ok };
  } catch {
    return null;
  } finally {
    probeVideo.srcObject = null;
    stream?.getTracks().forEach((t) => t.stop());
  }
}

/** Prefer FHD/color camera; skip IR sensors that return near-black frames. */
export async function probeCameras(devices?: VideoDevice[]): Promise<ProbeResult | null> {
  const list = devices ?? (await listVideoDevices());
  if (!list.length) return null;

  const scratch = document.createElement("canvas");
  const probeVideo = document.createElement("video");
  probeVideo.muted = true;
  probeVideo.playsInline = true;
  probeVideo.setAttribute("playsinline", "true");

  // Prefer labels that look like color / FHD webcams
  const sorted = [...list].sort((a, b) => scoreLabel(b.label) - scoreLabel(a.label));

  let fallback: ProbeResult | null = null;
  for (const dev of sorted) {
    const result = await tryDevice(dev, scratch, probeVideo);
    if (!result) continue;
    if (result.ok) return result;
    if (!fallback || result.brightness > fallback.brightness) fallback = result;
  }

  if (fallback) {
    fallback.note =
      `${fallback.label} is still dark — pick another camera, close Zoom/Teams, ` +
      "or remove the privacy shutter. WiFi can still sense motion through walls.";
  }
  return fallback;
}

function scoreLabel(label: string): number {
  const l = label.toLowerCase();
  let s = 0;
  if (l.includes("fhd") || l.includes("1080") || l.includes("uvc")) s += 4;
  if (l.includes("usb")) s += 2;
  if (l.includes("integrated") || l.includes("built-in")) s += 1;
  if (l.includes("ir") || l.includes("infrared") || l.includes("depth")) s -= 6;
  if (l.includes("virtual") || l.includes("obs")) s -= 3;
  return s;
}
