"""Estimate body dimensions only when the person is clearly fully visible."""

from __future__ import annotations

import math
from dataclasses import dataclass

# MediaPipe pose indices
NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_HEEL, R_HEEL = 29, 30

# Face mesh indices (full 468-point mesh)
FACE_FOREHEAD = 10
FACE_CHIN = 152
FACE_L_CHEEK = 234
FACE_R_CHEEK = 454

# Anthropometric constants (adult averages, cm)
AVG_FACE_LENGTH_CM = 19.0  # forehead to chin
AVG_HEAD_ABOVE_NOSE_RATIO = 0.08  # nose-to-ankle → add for top of head
MIN_HEIGHT_CM = 120.0
MAX_HEIGHT_CM = 220.0
MIN_WEIGHT_KG = 35.0
MAX_WEIGHT_KG = 180.0

# Need this score (0–1) before showing height/weight
VISIBILITY_THRESHOLD = 0.72


@dataclass
class BodyMetricsResult:
    height_cm: float | None = None
    weight_kg_est: float | None = None
    face_width_cm: float | None = None
    face_height_cm: float | None = None
    face_width_norm: float | None = None
    face_height_norm: float | None = None
    visibility_score: float = 0.0
    measurements_ready: bool = False
    visibility_message: str = "Step into full view of the camera"


def _dist(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _kp(pose: list[dict], idx: int, min_conf: float = 0.35) -> dict | None:
    if idx >= len(pose):
        return None
    p = pose[idx]
    return p if (p.get("confidence") or 0) >= min_conf else None


def assess_visibility(pose: list[dict], face: list[dict], bbox: dict) -> tuple[float, str]:
    """
    Score how clearly the full body is visible (not occluded, not clipped, not partial).
    Returns (score 0-1, human-readable status).
    """
    if len(pose) < 33:
        return 0.0, "Body not detected — stand in front of the camera"

    checks: list[tuple[str, float, str]] = []

    nose = _kp(pose, NOSE, 0.4)
    ls, rs = _kp(pose, L_SHOULDER, 0.4), _kp(pose, R_SHOULDER, 0.4)
    lh, rh = _kp(pose, L_HIP, 0.4), _kp(pose, R_HIP, 0.4)
    lk, rk = _kp(pose, L_KNEE, 0.35), _kp(pose, R_KNEE, 0.35)
    la, ra = _kp(pose, L_ANKLE, 0.35), _kp(pose, R_ANKLE, 0.35)

    # Head & shoulders
    checks.append(("head", 1.0 if nose else 0.0, "Face/head not visible"))
    checks.append(("shoulders", 1.0 if ls and rs else 0.5 if ls or rs else 0.0, "Turn to show both shoulders"))

    # Core body
    checks.append(("hips", 1.0 if lh and rh else 0.0, "Hips not visible — step back"))

    # Legs & feet (critical for height)
    feet_score = 0.0
    if la and ra:
        feet_score = 1.0
    elif la or ra:
        feet_score = 0.45
    checks.append(("feet", feet_score, "Feet not visible — step back so legs are in frame"))

    checks.append(("knees", 1.0 if lk and rk else 0.4 if lk or rk else 0.0, "Knees obscured"))

    # Full body vertical span
    if nose and la and ra:
        ankle_y = (la["y"] + ra["y"]) / 2
        span = ankle_y - nose["y"]
        if span >= 0.55:
            span_score = 1.0
        elif span >= 0.40:
            span_score = 0.6
        else:
            span_score = 0.2
        checks.append(("span", span_score, "Too close or upper body only — step back for full body"))
    else:
        checks.append(("span", 0.0, "Cannot measure full body span"))

    # Not clipped by frame edges (proxy for "behind something" / partial exit)
    margin = 0.04
    clip_ok = (
        bbox.get("x", 0) > margin
        and bbox.get("y", 0) > margin
        and bbox.get("x", 0) + bbox.get("w", 1) < 1 - margin
        and bbox.get("y", 0) + bbox.get("h", 1) < 1 - margin
    )
    checks.append(("frame", 1.0 if clip_ok else 0.35, "Body clipped at edge — center yourself in frame"))

    if nose and la and ra:
        if nose["y"] < margin or (la["y"] + ra["y"]) / 2 > 1 - margin:
            checks[-1] = ("frame", 0.2, "Head or feet cut off — adjust position")

    # Landmark density (occlusion lowers average confidence)
    confs = [p.get("confidence", 0) for p in pose if p.get("confidence", 0) > 0.1]
    high_conf = sum(1 for c in confs if c > 0.5)
    density = min(1.0, high_conf / 20)
    checks.append(("density", density, "Body partially blocked — move into clear view"))

    # Left/right symmetry (one side hidden behind wall/object)
    left_pts = [pose[i] for i in (L_SHOULDER, L_ELBOW, L_WRIST, L_HIP, L_KNEE, L_ANKLE) if i < len(pose)]
    right_pts = [pose[i] for i in (R_SHOULDER, R_ELBOW, R_WRIST, R_HIP, R_KNEE, R_ANKLE) if i < len(pose)]
    l_avg = sum(p.get("confidence", 0) for p in left_pts) / max(len(left_pts), 1)
    r_avg = sum(p.get("confidence", 0) for p in right_pts) / max(len(right_pts), 1)
    asym = abs(l_avg - r_avg)
    sym_score = 1.0 if asym < 0.15 else 0.5 if asym < 0.3 else 0.15
    checks.append(("symmetry", sym_score, "One side blocked — face the camera squarely"))

    weights = {
        "head": 0.10, "shoulders": 0.10, "hips": 0.12, "feet": 0.22,
        "knees": 0.08, "span": 0.18, "frame": 0.10, "density": 0.05, "symmetry": 0.05,
    }
    score = sum(weights[name] * val for name, val, _ in checks)

    # Message from worst failing check
    failing = [(val, msg) for name, val, msg in checks if val < 0.6]
    if not failing and score >= VISIBILITY_THRESHOLD:
        msg = "Full body clearly visible — measurements active"
    elif failing:
        failing.sort(key=lambda x: x[0])
        msg = failing[0][1]
    else:
        msg = "Almost there — show full body head to feet"

    return round(min(1.0, score), 3), msg


def _face_dims_full(face: list[dict]) -> dict:
    if len(face) < 455:
        return {"width": 0, "height": 0, "width_cm": None, "height_cm": None}
    lc, rc = face[FACE_L_CHEEK], face[FACE_R_CHEEK]
    forehead, chin = face[FACE_FOREHEAD], face[FACE_CHIN]
    w_norm = _dist(lc, rc)
    h_norm = _dist(forehead, chin)
    if h_norm < 0.008:
        return {"width": 0, "height": 0, "width_cm": None, "height_cm": None}
    # Scale face height to real cm, then derive width proportionally
    face_h_cm = AVG_FACE_LENGTH_CM
    face_w_cm = (w_norm / h_norm) * face_h_cm
    return {
        "width": round(w_norm, 4),
        "height": round(h_norm, 4),
        "width_cm": round(face_w_cm, 1),
        "height_cm": round(face_h_cm, 1),
    }


def _height_from_world(world_landmarks) -> float | None:
    if not world_landmarks or len(world_landmarks) < 33:
        return None
    ys = [lm.y for lm in world_landmarks]
    zs = [lm.z for lm in world_landmarks]
    span = max(ys) - min(ys)
    depth = max(zs) - min(zs)
    height_m = math.sqrt(span ** 2 + depth ** 2)
    if MIN_HEIGHT_CM / 100 < height_m < MAX_HEIGHT_CM / 100:
        return round(height_m * 100, 1)
    return None


def _height_from_face_scale(pose: list[dict], face: list[dict]) -> float | None:
    """Calibrate pixel body span using known average face length."""
    nose = _kp(pose, NOSE, 0.4)
    la, ra = _kp(pose, L_ANKLE, 0.35), _kp(pose, R_ANKLE, 0.35)
    if len(face) < 455 or not nose or not (la and ra):
        return None
    forehead, chin = face[FACE_FOREHEAD], face[FACE_CHIN]
    face_h_norm = _dist(forehead, chin)
    if face_h_norm < 0.012:
        return None
    ankle_y = (la["y"] + ra["y"]) / 2
    body_span = ankle_y - nose["y"]
    if body_span < 0.35:
        return None
    # cm per normalized unit from face calibration
    cm_per_unit = AVG_FACE_LENGTH_CM / face_h_norm
    height_cm = body_span * cm_per_unit * (1 + AVG_HEAD_ABOVE_NOSE_RATIO)
    if MIN_HEIGHT_CM <= height_cm <= MAX_HEIGHT_CM:
        return round(height_cm, 1)
    return None


def _height_from_proportions(pose: list[dict]) -> float | None:
    """2D fallback when face not available."""
    nose = _kp(pose, NOSE, 0.4)
    la, ra = _kp(pose, L_ANKLE, 0.35), _kp(pose, R_ANKLE, 0.35)
    if not nose or not (la and ra):
        return None
    ankle_y = (la["y"] + ra["y"]) / 2
    body_span = ankle_y - nose["y"]
    if body_span < 0.45:
        return None
    # At ~2m distance full body ≈ 0.78 of frame height for ~170cm person
    height_cm = body_span * (170 / 0.78) * (1 + AVG_HEAD_ABOVE_NOSE_RATIO)
    if MIN_HEIGHT_CM <= height_cm <= MAX_HEIGHT_CM:
        return round(height_cm, 1)
    return None


def _estimate_weight(pose: list[dict], height_cm: float, visibility: float) -> float | None:
    if not height_cm or len(pose) < 33:
        return None
    ls, rs = _kp(pose, L_SHOULDER, 0.4), _kp(pose, R_SHOULDER, 0.4)
    lh, rh = _kp(pose, L_HIP, 0.4), _kp(pose, R_HIP, 0.4)
    la, ra = _kp(pose, L_ANKLE, 0.35), _kp(pose, R_ANKLE, 0.35)
    if not all([ls, rs, lh, rh, la, ra]):
        return None

    nose = pose[NOSE]
    ankle_y = (la["y"] + ra["y"]) / 2
    body_span = max(ankle_y - nose["y"], 0.01)

    shoulder_w = _dist(ls, rs) / body_span
    hip_w = _dist(lh, rh) / body_span
    torso_depth = (shoulder_w + hip_w) / 2

    # Frame-normalized breadth → BMI proxy (calibrated for typical adult range)
    bmi = 19.5 + (torso_depth - 0.22) * 38
    bmi = max(17.0, min(36.0, bmi))

    # Reduce confidence in extreme estimates when visibility isn't perfect
    if visibility < 0.85:
        bmi = 22.0 + (bmi - 22.0) * 0.7

    h_m = height_cm / 100
    weight = bmi * h_m * h_m
    weight = max(MIN_WEIGHT_KG, min(MAX_WEIGHT_KG, weight))
    return round(weight, 1)


def compute_body_metrics(
    pose: list[dict],
    face_full: list[dict],
    bbox: dict,
    world_landmarks=None,
) -> BodyMetricsResult:
    """
    Compute height/weight only when visibility score passes threshold.
    """
    vis_score, vis_msg = assess_visibility(pose, face_full, bbox)
    fd = _face_dims_full(face_full) if len(face_full) >= 455 else {}

    ready = vis_score >= VISIBILITY_THRESHOLD
    height_cm: float | None = None
    weight_kg: float | None = None

    if ready:
        height_cm = (
            _height_from_world(world_landmarks)
            or _height_from_face_scale(pose, face_full)
            or _height_from_proportions(pose)
        )
        if height_cm:
            weight_kg = _estimate_weight(pose, height_cm, vis_score)

    return BodyMetricsResult(
        height_cm=height_cm if ready else None,
        weight_kg_est=weight_kg if ready else None,
        face_width_cm=fd.get("width_cm") if ready and fd.get("width_cm") else None,
        face_height_cm=fd.get("height_cm") if ready and fd.get("height_cm") else None,
        face_width_norm=fd.get("width"),
        face_height_norm=fd.get("height"),
        visibility_score=vis_score,
        measurements_ready=ready and height_cm is not None,
        visibility_message=vis_msg if not ready or not height_cm else "Full body clearly visible — measurements active",
    )
