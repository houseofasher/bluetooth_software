/** Camera black-screen theory — narrative → flaw → fix → code. */

export const BLACK_MEAN_THRESHOLD = 8;

export const BROWSER_CAMERA_BLACK_THEORY = {
  id: "browser_camera_black",
  category: "wifi_pose",
  narrative: "Wayne opened PoseSense — the lens showed only darkness",
  flaw: "Windows laptops expose IR + FHD UVC sensors; wrong index or OpenCV backend yields black frames",
  flawType: "operational",
  fix: "Probe all videoinput devices; pick brightest stream; browser getUserMedia + device picker",
  code: "camera-probe.probeCameras",
  module: "posesense/camera-probe.ts",
  feasibility: "high",
} as const;

export function cameraTheoryChain(brightness: number, deviceLabel: string): string {
  const t = BROWSER_CAMERA_BLACK_THEORY;
  const status =
    brightness >= BLACK_MEAN_THRESHOLD
      ? `live (${brightness.toFixed(0)}/255 via ${deviceLabel})`
      : `black (${brightness.toFixed(0)}/255 — below ${BLACK_MEAN_THRESHOLD})`;
  return `${t.narrative} → ${t.flaw} → ${t.fix} → ${t.code} [${status}]`;
}
