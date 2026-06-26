"""Infer where on the body a BLE device is likely carried."""

from __future__ import annotations

import math
from dataclasses import dataclass

# MediaPipe pose indices
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
NOSE, L_EAR, R_EAR = 0, 7, 8

# Default body zone by device category
DEFAULT_ZONE = {
    "phone": ("hand", "Hand (likely)"),
    "watch": ("wrist", "Wrist"),
    "audio": ("ear", "Ear / head"),
    "tracker": ("pocket", "Pocket / bag"),
    "tablet": ("hand", "Hand"),
    "laptop": ("bag", "Bag / nearby"),
    "unknown": ("nearby", "On person (uncertain)"),
}


@dataclass
class BodyPlacement:
    zone: str
    label: str
    side: str | None  # left, right, center, both
    anchor: dict  # normalized x, y for UI badge
    confidence: float
    method: str  # type_default, hand_pose, motion, pocket


def _kp(pose: list[dict], idx: int) -> dict | None:
    if not pose or idx >= len(pose):
        return None
    p = pose[idx]
    return p if (p.get("confidence") or 0) > 0.25 else None


def _hand_motion(hand: list[dict]) -> float:
    if len(hand) < 5:
        return 0.0
    return sum(math.hypot(hand[i]["x"] - hand[i + 1]["x"], hand[i]["y"] - hand[i + 1]["y"]) for i in range(4))


def _mid(a: dict, b: dict) -> dict:
    return {"x": (a["x"] + b["x"]) / 2, "y": (a["y"] + b["y"]) / 2, "confidence": min(a["confidence"], b["confidence"])}


def _wrist_raised(wrist: dict, elbow: dict, shoulder: dict) -> bool:
    return wrist["y"] < elbow["y"] < shoulder["y"] + 0.05


def _wrist_at_pocket(wrist: dict, hip: dict, shoulder: dict) -> bool:
    return abs(wrist["y"] - hip["y"]) < 0.12 and abs(wrist["x"] - hip["x"]) < 0.15 and wrist["y"] > shoulder["y"]


def infer_placement(
    device_type: str,
    pose: list[dict],
    left_hand: list[dict],
    right_hand: list[dict],
    left_hand_motion: float = 0.0,
    right_hand_motion: float = 0.0,
    rssi_trend: float = 0.0,
) -> BodyPlacement:
    """Estimate body location using device type + pose + hand tracking."""

    zone_key, zone_label = DEFAULT_ZONE.get(device_type, DEFAULT_ZONE["unknown"])

    lw, rw = _kp(pose, L_WRIST), _kp(pose, R_WRIST)
    le, re = _kp(pose, L_ELBOW), _kp(pose, R_ELBOW)
    ls, rs = _kp(pose, L_SHOULDER), _kp(pose, R_SHOULDER)
    lh, rh = _kp(pose, L_HIP), _kp(pose, R_HIP)
    nose = _kp(pose, NOSE)
    lear, rear = _kp(pose, L_EAR), _kp(pose, R_EAR)

    # --- Watch: anchor to wrist ---
    if device_type == "watch" and lw and rw:
        # Weaker signal side sometimes means farther — prefer visible raised wrist
        if le and ls and _wrist_raised(lw, le, ls):
            return BodyPlacement("wrist", "Left wrist", "left", lw, 0.82, "hand_pose")
        if re and rs and _wrist_raised(rw, re, rs):
            return BodyPlacement("wrist", "Right wrist", "right", rw, 0.82, "hand_pose")
        side_w = lw if (lw["y"] < rw["y"]) else rw
        side = "left" if side_w is lw else "right"
        return BodyPlacement("wrist", f"{side.title()} wrist", side, side_w, 0.65, "type_default")

    # --- Audio: anchor near ear ---
    if device_type == "audio":
        if lear and rear:
            anchor = _mid(lear, rear)
            return BodyPlacement("ear", "Head / ears", "both", anchor, 0.75, "type_default")
        if nose:
            return BodyPlacement("ear", "Head / ears", "center", nose, 0.6, "type_default")

    # --- Phone / tablet: hand, pocket, or motion-inferred side ---
    if device_type in ("phone", "tablet"):
        # Phone visibly in raised hand
        if lw and le and ls and _wrist_raised(lw, le, ls) and len(left_hand) > 10:
            return BodyPlacement("hand", "Left hand (holding device)", "left", lw, 0.88, "hand_pose")
        if rw and re and rs and _wrist_raised(rw, re, rs) and len(right_hand) > 10:
            return BodyPlacement("hand", "Right hand (holding device)", "right", rw, 0.88, "hand_pose")

        # Pocket detection
        if lw and lh and ls and _wrist_at_pocket(lw, lh, ls):
            anchor = {"x": lh["x"], "y": lh["y"] + 0.04, "confidence": lh["confidence"]}
            return BodyPlacement("pocket", "Left pocket", "left", anchor, 0.72, "pocket")
        if rw and rh and rs and _wrist_at_pocket(rw, rh, rs):
            anchor = {"x": rh["x"], "y": rh["y"] + 0.04, "confidence": rh["confidence"]}
            return BodyPlacement("pocket", "Right pocket", "right", anchor, 0.72, "pocket")

        # Motion correlation: hand moving more while signal fluctuates
        if left_hand_motion > right_hand_motion * 1.4 and lw:
            return BodyPlacement("hand", "Left hand (motion match)", "left", lw, 0.68, "motion")
        if right_hand_motion > left_hand_motion * 1.4 and rw:
            return BodyPlacement("hand", "Right hand (motion match)", "right", rw, 0.68, "motion")

        # Default: dominant hand area (lower wrist = likely holding)
        if lw and rw:
            anchor = lw if lw["y"] > rw["y"] else rw
            side = "left" if anchor is lw else "right"
            return BodyPlacement("hand", f"{side.title()} hand (likely)", side, anchor, 0.55, "type_default")
        if lw:
            return BodyPlacement("hand", "Left hand (likely)", "left", lw, 0.5, "type_default")
        if rw:
            return BodyPlacement("hand", "Right hand (likely)", "right", rw, 0.5, "type_default")

    # --- Tracker / unknown: hip pocket zone ---
    if lh and rh:
        anchor = _mid(lh, rh)
        return BodyPlacement("pocket", zone_label, "center", anchor, 0.45, "type_default")

    if nose:
        return BodyPlacement("nearby", zone_label, "center", nose, 0.35, "type_default")

    return BodyPlacement("nearby", zone_label, None, {"x": 0.5, "y": 0.5, "confidence": 0.2}, 0.2, "type_default")
