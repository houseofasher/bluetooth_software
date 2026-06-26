"""Webcam + full-body pose, face oval, hand/finger tracking with smoothing."""

from __future__ import annotations

import base64
import math
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from .body_metrics import BodyMetricsResult, compute_body_metrics
from .skeleton import FACE_OVAL, POSE_LANDMARKS
from .smoothing import LandmarkSmoother

MODELS = {
    "pose": (
        "pose_landmarker_lite.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    ),
    "face": (
        "face_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    ),
    "hand": (
        "hand_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    ),
}

NOSE, L_SHOULDER, R_SHOULDER = 0, 11, 12
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24


@dataclass
class BodyMetrics:
    height_cm: float | None = None
    weight_kg_est: float | None = None
    face_width_cm: float | None = None
    face_height_cm: float | None = None
    face_width_norm: float | None = None
    face_height_norm: float | None = None
    visibility_score: float = 0.0
    measurements_ready: bool = False
    visibility_message: str = "Step into full view of the camera"


@dataclass
class PersonDetection:
    person_id: int
    pose: list[dict]
    face: list[dict]
    left_hand: list[dict]
    right_hand: list[dict]
    bbox: dict
    motion_energy: float
    metrics: BodyMetrics
    in_frame: bool = True
    last_seen: float = field(default_factory=time.time)

    # Back-compat alias
    @property
    def keypoints(self) -> list[dict]:
        return self.pose


@dataclass
class CameraFrame:
    jpeg_base64: str
    width: int
    height: int
    persons: list[PersonDetection]
    timestamp: float


def ensure_models() -> dict[str, Path]:
    base = Path(__file__).parent
    paths = {}
    for key, (fname, url) in MODELS.items():
        path = base / fname
        if not path.exists():
            print(f"Downloading {fname}...")
            urllib.request.urlretrieve(url, path)
        paths[key] = path
    return paths


def _lm_to_dict(lm, vis=None) -> dict:
    return {
        "x": lm.x,
        "y": lm.y,
        "z": getattr(lm, "z", 0.0),
        "confidence": vis if vis is not None else getattr(lm, "visibility", 0.8) or 0.8,
    }


def _pose_bbox(pose: list[dict]) -> dict:
    pts = [p for p in pose if p.get("confidence", 0) > 0.35]
    if not pts:
        return {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}
    xs = [p["x"] for p in pts]
    ys = [p["y"] for p in pts]
    x1, y1 = max(0.0, min(xs)), max(0.0, min(ys))
    x2, y2 = min(1.0, max(xs)), min(1.0, max(ys))
    return {"x": x1, "y": y1, "w": max(0.0, x2 - x1), "h": max(0.0, y2 - y1)}


def _bbox_iou(a: dict, b: dict) -> float:
    ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
    bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 1e-6 else 0.0


def _pose_score(pose: list[dict]) -> float:
    visible = [p.get("confidence", 0.0) for p in pose if p.get("confidence", 0.0) > 0.35]
    return sum(visible) / max(len(visible), 1) + len(visible) * 0.02


def _dedupe_pose_indices(raw_poses: list[list[dict]]) -> list[int]:
    """Remove duplicate MediaPipe pose detections for the same visible person."""
    scored = sorted(
        ((idx, _pose_bbox(pose), _pose_score(pose)) for idx, pose in enumerate(raw_poses)),
        key=lambda item: (item[2], item[1]["w"] * item[1]["h"]),
        reverse=True,
    )
    kept: list[tuple[int, dict]] = []
    for idx, bbox, _score in scored:
        cx, cy = bbox["x"] + bbox["w"] / 2, bbox["y"] + bbox["h"] / 2
        duplicate = False
        for _kept_idx, kept_bbox in kept:
            kcx, kcy = kept_bbox["x"] + kept_bbox["w"] / 2, kept_bbox["y"] + kept_bbox["h"] / 2
            center_dist = math.hypot(cx - kcx, cy - kcy)
            if _bbox_iou(bbox, kept_bbox) > 0.35 or center_dist < 0.12:
                duplicate = True
                break
        if not duplicate:
            kept.append((idx, bbox))
    return sorted(idx for idx, _bbox in kept)


class CameraTracker:
    def __init__(self, camera_index: int = 0, max_poses: int = 4) -> None:
        self.camera_index = camera_index
        self.max_poses = max_poses
        self._lock = threading.Lock()
        self._latest: CameraFrame | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._tracks: dict[int, dict] = {}
        self._next_id = 1

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=4)

    def get_latest(self) -> CameraFrame | None:
        with self._lock:
            return self._latest

    def _get_smoother(self, track: dict, key: str, count: int) -> LandmarkSmoother:
        smoothers = track.setdefault("smoothers", {})
        if key not in smoothers:
            smoothers[key] = LandmarkSmoother(count, key)
        return smoothers[key]

    def _center(self, kps: list[dict]) -> tuple[float, float]:
        lh, rh = kps[L_HIP], kps[R_HIP]
        if lh["confidence"] > 0.3 and rh["confidence"] > 0.3:
            return (lh["x"] + rh["x"]) / 2, (lh["y"] + rh["y"]) / 2
        return kps[NOSE]["x"], kps[NOSE]["y"]

    def _assign_ids(
        self,
        raw_poses: list[list[dict]],
        world_poses: list,
        faces: list[list[dict]],
        hands: list[tuple[str, list[dict]]],
        ts: float,
    ) -> list[PersonDetection]:
        now = time.time()
        used: set[int] = set()
        results: list[PersonDetection] = []

        for idx, kps in enumerate(raw_poses):
            cx, cy = self._center(kps)
            best_id, best_dist = None, 0.18

            for tid, track in self._tracks.items():
                if tid in used:
                    continue
                tx, ty = track["center"]
                d = math.hypot(cx - tx, cy - ty)
                if d < best_dist:
                    best_dist, best_id = d, tid

            if best_id is None:
                best_id = self._next_id
                self._next_id += 1
                self._tracks[best_id] = {"center": (cx, cy), "prev_pose": kps, "motion": 0.0}

            used.add(best_id)
            track = self._tracks[best_id]
            motion = self._motion_energy(track.get("prev_pose"), kps)
            track["center"] = (cx, cy)
            track["prev_pose"] = kps
            track["motion"] = motion * 0.65 + track.get("motion", 0) * 0.35
            track["last_seen"] = now

            pose_smooth = self._get_smoother(track, "pose", 33).smooth(kps, ts)

            # Match face by nose proximity
            face_pts = self._match_face(kps[NOSE], faces)
            face_smooth = self._get_smoother(track, "face", max(len(face_pts), 1)).smooth(face_pts, ts) if face_pts else []

            # Match hands by wrist proximity
            lh = self._match_hand(kps[L_WRIST], "Left", hands)
            rh = self._match_hand(kps[R_WRIST], "Right", hands)
            lh_smooth = self._get_smoother(track, "left_hand", 21).smooth(lh, ts) if lh else []
            rh_smooth = self._get_smoother(track, "right_hand", 21).smooth(rh, ts) if rh else []

            world = world_poses[idx] if idx < len(world_poses) else None

            all_pts_pre = pose_smooth + face_smooth + lh_smooth + rh_smooth
            xs = [p["x"] for p in all_pts_pre if p.get("confidence", 0) > 0.2]
            ys = [p["y"] for p in all_pts_pre if p.get("confidence", 0) > 0.2]
            if xs and ys:
                pad = 0.05
                bbox = {
                    "x": max(0, min(xs) - pad),
                    "y": max(0, min(ys) - pad),
                    "w": min(1, max(xs) + pad) - max(0, min(xs) - pad),
                    "h": min(1, max(ys) + pad) - max(0, min(ys) - pad),
                }
            else:
                bbox = {"x": cx - 0.12, "y": cy - 0.25, "w": 0.24, "h": 0.55}

            raw_metrics = compute_body_metrics(pose_smooth, face_smooth, bbox, world)

            # EMA smooth height/weight when measurements are stable
            ema = track.setdefault("metrics_ema", {"h": None, "w": None})
            alpha = 0.25
            if raw_metrics.measurements_ready and raw_metrics.height_cm:
                ema["h"] = raw_metrics.height_cm if ema["h"] is None else ema["h"] * (1 - alpha) + raw_metrics.height_cm * alpha
            if raw_metrics.measurements_ready and raw_metrics.weight_kg_est:
                ema["w"] = raw_metrics.weight_kg_est if ema["w"] is None else ema["w"] * (1 - alpha) + raw_metrics.weight_kg_est * alpha
            if not raw_metrics.measurements_ready:
                ema["h"], ema["w"] = None, None

            metrics = BodyMetrics(
                height_cm=round(ema["h"], 1) if ema["h"] else None,
                weight_kg_est=round(ema["w"], 1) if ema["w"] else None,
                face_width_cm=raw_metrics.face_width_cm,
                face_height_cm=raw_metrics.face_height_cm,
                face_width_norm=raw_metrics.face_width_norm,
                face_height_norm=raw_metrics.face_height_norm,
                visibility_score=raw_metrics.visibility_score,
                measurements_ready=raw_metrics.measurements_ready and ema["h"] is not None,
                visibility_message=raw_metrics.visibility_message,
            )

            all_pts = all_pts_pre
            face_oval = [face_smooth[i] for i in FACE_OVAL if i < len(face_smooth)] if face_smooth else []

            results.append(PersonDetection(
                person_id=best_id,
                pose=[{**p, "name": POSE_LANDMARKS[i] if i < len(POSE_LANDMARKS) else str(i)} for i, p in enumerate(pose_smooth)],
                face=face_oval,
                left_hand=lh_smooth,
                right_hand=rh_smooth,
                bbox=bbox,
                motion_energy=min(1.0, track["motion"]),
                metrics=metrics,
                last_seen=now,
            ))

        stale = [tid for tid, t in self._tracks.items() if now - t.get("last_seen", 0) > 2.5]
        for tid in stale:
            del self._tracks[tid]

        return results

    @staticmethod
    def _match_face(nose: dict, faces: list[list[dict]]) -> list[dict]:
        best, best_d = None, 0.12
        for face in faces:
            if not face:
                continue
            c = face[1] if len(face) > 1 else face[0]  # nose tip area
            d = math.hypot(nose["x"] - c["x"], nose["y"] - c["y"])
            if d < best_d:
                best_d, best = d, face
        return best or []

    @staticmethod
    def _match_hand(wrist: dict, side: str, hands: list[tuple[str, list[dict]]]) -> list[dict]:
        if wrist["confidence"] < 0.25:
            return []
        best, best_d = None, 0.15
        for hand_side, pts in hands:
            if not pts:
                continue
            c = pts[0]  # wrist
            d = math.hypot(wrist["x"] - c["x"], wrist["y"] - c["y"])
            if hand_side == side and d < best_d:
                best_d, best = d, pts
        # Fallback: nearest hand regardless of label
        if best is None:
            for hand_side, pts in hands:
                if not pts:
                    continue
                c = pts[0]
                d = math.hypot(wrist["x"] - c["x"], wrist["y"] - c["y"])
                if d < best_d:
                    best_d, best = d, pts
        return best or []

    @staticmethod
    def _motion_energy(prev: list[dict] | None, curr: list[dict]) -> float:
        if not prev:
            return 0.0
        total, count = 0.0, 0
        for a, b in zip(prev, curr):
            if a["confidence"] > 0.3 and b["confidence"] > 0.3:
                total += math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                count += 1
        return (total / count) * 18 if count else 0.0

    def _loop(self) -> None:
        paths = ensure_models()
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        pose_lm = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(paths["pose"])),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=self.max_poses,
            min_pose_detection_confidence=0.55,
            min_pose_presence_confidence=0.55,
            min_tracking_confidence=0.65,
            output_segmentation_masks=False,
        ))
        face_lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(paths["face"])),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=self.max_poses,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,
        ))
        hand_lm = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(paths["hand"])),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=self.max_poses * 2,
            min_hand_detection_confidence=0.45,
            min_hand_presence_confidence=0.45,
            min_tracking_confidence=0.55,
        ))

        frame_ts = 0
        while self._running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.02)
                continue

            h, w = frame.shape[:2]
            ts = time.time()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            frame_ts += 33

            pose_res = pose_lm.detect_for_video(mp_image, frame_ts)
            face_res = face_lm.detect_for_video(mp_image, frame_ts)
            hand_res = hand_lm.detect_for_video(mp_image, frame_ts)

            raw_poses: list[list[dict]] = []
            world_poses = []
            if pose_res.pose_landmarks:
                for i, plm in enumerate(pose_res.pose_landmarks):
                    raw_poses.append([_lm_to_dict(lm, lm.visibility) for lm in plm])
                    if pose_res.pose_world_landmarks and i < len(pose_res.pose_world_landmarks):
                        world_poses.append(pose_res.pose_world_landmarks[i])

            if len(raw_poses) > 1:
                keep = _dedupe_pose_indices(raw_poses)
                raw_poses = [raw_poses[i] for i in keep]
                world_poses = [world_poses[i] for i in keep if i < len(world_poses)]

            faces: list[list[dict]] = []
            if face_res.face_landmarks:
                for flm in face_res.face_landmarks:
                    faces.append([_lm_to_dict(lm) for lm in flm])

            hands: list[tuple[str, list[dict]]] = []
            if hand_res.hand_landmarks:
                for i, hlm in enumerate(hand_res.hand_landmarks):
                    side = "Left"
                    if hand_res.handedness and i < len(hand_res.handedness):
                        side = hand_res.handedness[i][0].category_name
                    hands.append((side, [_lm_to_dict(lm) for lm in hlm]))

            persons = self._assign_ids(raw_poses, world_poses, faces, hands, ts)

            # Clean camera frame only — skeleton drawn client-side for smooth visuals
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
            b64 = base64.b64encode(buf).decode("ascii")

            with self._lock:
                self._latest = CameraFrame(jpeg_base64=b64, width=w, height=h, persons=persons, timestamp=ts)

        cap.release()
        pose_lm.close()
        face_lm.close()
        hand_lm.close()
