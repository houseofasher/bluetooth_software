/** Pick a working color webcam on Windows (skips IR / dead streams). */

export interface CamDevice {
  deviceId: string;
  label: string;
}

function rank(label: string): number {
  const l = label.toLowerCase();
  let s = 0;
  if (/fhd|1080|uvc|usb|webcam|logitech|hd/.test(l)) s += 10;
  if (/integrated|built-in|front/.test(l)) s += 2;
  if (/ir|infrared|depth|virtual|obs|snap|teams/.test(l)) s -= 20;
  return s;
}

function meanLuma(video: HTMLVideoElement, scratch: HTMLCanvasElement): number {
  if (video.readyState < 2 || video.videoWidth <= 0) return 0;
  const ctx = scratch.getContext("2d", { willReadFrequently: true });
  if (!ctx) return 0;
  const w = 120;
  const h = Math.max(1, Math.round(w * (video.videoHeight / video.videoWidth)));
  scratch.width = w;
  scratch.height = h;
  ctx.drawImage(video, 0, 0, w, h);
  const px = ctx.getImageData(0, 0, w, h).data;
  let sum = 0;
  for (let i = 0; i < px.length; i += 4) sum += (px[i]! + px[i + 1]! + px[i + 2]!) / 3;
  return sum / (px.length / 4);
}

async function waitForFrames(video: HTMLVideoElement, ms = 1200): Promise<void> {
  const end = performance.now() + ms;
  while (performance.now() < end) {
    if (video.readyState >= 2 && video.videoWidth > 0) return;
    await new Promise((r) => setTimeout(r, 50));
  }
}

function stopVideo(video: HTMLVideoElement) {
  const stream = video.srcObject as MediaStream | null;
  stream?.getTracks().forEach((t) => t.stop());
  video.srcObject = null;
}

export async function listCameras(): Promise<CamDevice[]> {
  const raw = await navigator.mediaDevices.enumerateDevices();
  return raw
    .filter((d) => d.kind === "videoinput" && d.deviceId)
    .map((d, i) => ({ deviceId: d.deviceId, label: d.label?.trim() || `Camera ${i + 1}` }));
}

export async function ensureCameraPermission(): Promise<void> {
  const s = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  s.getTracks().forEach((t) => t.stop());
}

/** Try each camera; return the brightest working stream. */
export async function pickWorkingCamera(
  video: HTMLVideoElement,
  scratch: HTMLCanvasElement,
): Promise<{ deviceId: string; label: string; stream: MediaStream; luma: number }> {
  await ensureCameraPermission();
  const devices = (await listCameras()).sort((a, b) => rank(b.label) - rank(a.label));
  if (!devices.length) throw new Error("No camera found");

  let best: { deviceId: string; label: string; luma: number } | null = null;

  for (const dev of devices) {
    stopVideo(video);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { deviceId: { exact: dev.deviceId } },
        audio: false,
      });
      video.srcObject = stream;
      video.muted = true;
      video.playsInline = true;
      await video.play();
      await waitForFrames(video, 1500);
      await new Promise((r) => setTimeout(r, 400));
      const luma = meanLuma(video, scratch);

      if (luma >= 8) {
        return { deviceId: dev.deviceId, label: dev.label, stream, luma };
      }

      stream.getTracks().forEach((t) => t.stop());
      video.srcObject = null;
      if (!best || luma > best.luma) {
        best = { deviceId: dev.deviceId, label: dev.label, luma };
      }
    } catch {
      stopVideo(video);
    }
  }

  const pick = best ?? { deviceId: devices[0]!.deviceId, label: devices[0]!.label, luma: 0 };
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { deviceId: { exact: pick.deviceId } },
    audio: false,
  });
  video.srcObject = stream;
  video.muted = true;
  video.playsInline = true;
  await video.play();
  return { deviceId: pick.deviceId, label: pick.label, stream, luma: pick.luma };
}

export async function openCameraDevice(
  deviceId: string,
  video: HTMLVideoElement,
): Promise<MediaStream> {
  stopVideo(video);
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { deviceId: { exact: deviceId } },
    audio: false,
  });
  video.srcObject = stream;
  video.muted = true;
  video.playsInline = true;
  await video.play();
  return stream;
}
