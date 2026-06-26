"""Skeleton edge definitions for pose, face, and hands."""

from __future__ import annotations

# MediaPipe Pose — 33 landmarks (includes basic hand/foot points on body model)
POSE_LANDMARKS = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_pinky", "right_pinky", "left_index", "right_index",
    "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]

# Grouped edges for color-coded rendering
POSE_TORSO = [
    (11, 12), (11, 23), (12, 24), (23, 24),
]
POSE_LEFT_ARM = [(11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19)]
POSE_RIGHT_ARM = [(12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20)]
POSE_LEFT_LEG = [(23, 25), (25, 27), (27, 29), (27, 31), (29, 31)]
POSE_RIGHT_LEG = [(24, 26), (26, 28), (28, 30), (28, 32), (30, 32)]
POSE_NECK_HEAD = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10), (11, 0), (12, 0),
]

POSE_EDGE_GROUPS = [
    ("torso", POSE_TORSO, "#60a5fa"),
    ("left_arm", POSE_LEFT_ARM, "#34d399"),
    ("right_arm", POSE_RIGHT_ARM, "#fbbf24"),
    ("left_leg", POSE_LEFT_LEG, "#a78bfa"),
    ("right_leg", POSE_RIGHT_LEG, "#f472b6"),
    ("head_neck", POSE_NECK_HEAD, "#22d3ee"),
]

POSE_CONNECTIONS = (
    POSE_TORSO + POSE_LEFT_ARM + POSE_RIGHT_ARM
    + POSE_LEFT_LEG + POSE_RIGHT_LEG + POSE_NECK_HEAD
)

# Face oval (subset of 468 face mesh — key contour indices)
FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10,
]

# Hand — 21 landmarks each
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]
