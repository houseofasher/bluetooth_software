"""Procedural skeleton keypoints driven by motion state (not true pose estimation)."""

from __future__ import annotations

import math
import time

from .motion_engine import Activity, MotionState

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

SKELETON_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]


def motion_to_keypoints(state: MotionState) -> list[dict]:
    """Map coarse motion state to 17 normalized keypoints in [0, 1]."""
    cx = 0.5 + state.lateral * 0.12
    t = time.time()
    sway = math.sin(t * 2.5) * state.energy * 0.015
    cx += sway

    head_y = 0.12
    shoulder_y = 0.22
    hip_y = 0.48
    knee_y = 0.68
    ankle_y = 0.88
    arm_swing = 0.0
    leg_swing = 0.0

    if state.activity == Activity.WALKING:
        phase = t * 5.0
        leg_swing = math.sin(phase) * 0.04 * state.energy
        arm_swing = math.sin(phase + math.pi) * 0.05 * state.energy
        head_y += abs(math.sin(phase)) * 0.008
    elif state.activity == Activity.ARM_RAISE:
        arm_swing = -0.18 - state.vertical * 0.08
    elif state.activity == Activity.CROUCH:
        crouch = 0.12
        head_y += crouch
        shoulder_y += crouch
        hip_y += crouch * 0.6
        knee_y += crouch * 0.3
        ankle_y += crouch * 0.1
    elif state.activity == Activity.ACTIVE:
        arm_swing = math.sin(t * 3.0) * 0.04 * state.energy
    else:
        arm_swing = math.sin(t * 1.2) * 0.008 * state.energy

    shoulder_w = 0.11
    hip_w = 0.08

    if state.activity == Activity.ARM_RAISE:
        left_elbow_y = shoulder_y - 0.06
        right_elbow_y = shoulder_y - 0.06
        left_wrist_y = shoulder_y - 0.14 - state.vertical * 0.05
        right_wrist_y = shoulder_y - 0.14 - state.vertical * 0.05
        left_knee_y = knee_y
        right_knee_y = knee_y
        left_ankle_y = ankle_y
        right_ankle_y = ankle_y
    elif state.activity == Activity.WALKING:
        left_elbow_y = shoulder_y + 0.14 + arm_swing * 1.2
        right_elbow_y = shoulder_y + 0.14 - arm_swing * 1.2
        left_wrist_y = shoulder_y + 0.2 + arm_swing * 1.5
        right_wrist_y = shoulder_y + 0.2 - arm_swing * 1.5
        left_knee_y = knee_y + leg_swing
        right_knee_y = knee_y - leg_swing
        left_ankle_y = ankle_y + leg_swing * 1.5
        right_ankle_y = ankle_y - leg_swing * 1.5
    else:
        left_elbow_y = shoulder_y + 0.16 + arm_swing
        right_elbow_y = shoulder_y + 0.16 - arm_swing
        left_wrist_y = shoulder_y + 0.24 + arm_swing * 1.3
        right_wrist_y = shoulder_y + 0.24 - arm_swing * 1.3
        left_knee_y = knee_y
        right_knee_y = knee_y
        left_ankle_y = ankle_y
        right_ankle_y = ankle_y

    points = [
        (cx, head_y),
        (cx - 0.02, head_y - 0.015), (cx + 0.02, head_y - 0.015),
        (cx - 0.04, head_y), (cx + 0.04, head_y),
        (cx - shoulder_w, shoulder_y), (cx + shoulder_w, shoulder_y),
        (cx - shoulder_w - 0.03, left_elbow_y), (cx + shoulder_w + 0.03, right_elbow_y),
        (cx - shoulder_w - 0.05, left_wrist_y), (cx + shoulder_w + 0.05, right_wrist_y),
        (cx - hip_w, hip_y), (cx + hip_w, hip_y),
        (cx - hip_w, left_knee_y), (cx + hip_w, right_knee_y),
        (cx - hip_w, left_ankle_y), (cx + hip_w, right_ankle_y),
    ]

    return [
        {"name": KEYPOINT_NAMES[i], "x": p[0], "y": p[1], "confidence": state.confidence}
        for i, p in enumerate(points)
    ]
