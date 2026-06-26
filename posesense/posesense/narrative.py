"""
Narrative → Code bridge for PoseSense.

Maps Wayne's lab story arc to live system states and psychology-driven UI copy.
Each stage aligns a story beat with code conditions and modern UX intent (2027).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NarrativeStage:
    id: str
    index: int
    title: str
    story: str
    guidance: str
    psychology: str
    icon: str


STAGES: tuple[NarrativeStage, ...] = (
    NarrativeStage(
        id="awaiting",
        index=0,
        title="Lab Ready",
        story="Wayne opened PoseSense. The room is quiet — waiting for a presence to enter the field.",
        guidance="Step into the camera. The system will begin mapping when it sees you.",
        psychology="Anticipation without anxiety: one clear next step lowers cognitive load.",
        icon="◌",
    ),
    NarrativeStage(
        id="presence",
        index=1,
        title="Presence Detected",
        story="Someone entered the lab. Motion registered — the sensors awaken.",
        guidance="Hold still for a moment while the mesh finds your shoulders and hips.",
        psychology="Immediate feedback confirms 'I am seen' — core human need for acknowledgment.",
        icon="◎",
    ),
    NarrativeStage(
        id="mapping",
        index=2,
        title="Body Mapped",
        story="Dr. Emily moved through the room. PoseSense traced her full body — neck, limbs, fingertips — with startling precision.",
        guidance="Move naturally. Face the camera for face dimensions; show hands for finger tracking.",
        psychology="The 'awe moment': visual proof builds trust faster than numbers alone.",
        icon="◈",
    ),
    NarrativeStage(
        id="identity",
        index=3,
        title="Who Is This?",
        story="Wayne's next question: not just movement — identity. Multiple radio signatures filled the room.",
        guidance="Select yourself on camera, then choose your device below. Phones appear with 📱.",
        psychology="Choice restores agency when multiple signals compete — manual link reduces confusion.",
        icon="◉",
    ),
    NarrativeStage(
        id="recognition",
        index=4,
        title="Signal Recognized",
        story="A phone's Bluetooth radio broadcast its signature — not a bounce off the screen, but a whisper from the chip inside.",
        guidance="Hold your phone near you. Link it to confirm this signal belongs to you.",
        psychology="Transparency about HOW detection works prevents privacy paranoia.",
        icon="📱",
    ),
    NarrativeStage(
        id="harmony",
        index=5,
        title="Unified Tracking",
        story="Body and device linked. Wayne and Dr. Emily watched the screen — position, identity, and motion, woven together.",
        guidance="You're fully tracked. Move freely; metrics update in real time.",
        psychology="Flow state: when perceive + understand + connect merge, attention stays calm and focused.",
        icon="✦",
    ),
    NarrativeStage(
        id="through_wall",
        index=6,
        title="Through the Wall",
        story="Wayne pointed the camera at the drywall. The lens saw nothing — but the WiFi field rippled. Body reflections in the signal revealed someone moving in the next room.",
        guidance="WiFi CSI detects motion through walls. Camera confirms when you have line of sight.",
        psychology="Invisible sensing feels magical — but trust requires showing which sensor sees what.",
        icon="📡",
    ),
)


def resolve_narrative(
    person_count: int,
    device_count: int,
    binding_count: int,
    phone_nearby: bool,
    has_metrics: bool,
    has_hands: bool,
    wifi_occupied: bool = False,
    through_wall: bool = False,
) -> dict:
    """Derive current narrative stage from live fusion state."""

    if through_wall:
        stage = STAGES[6]
    elif person_count == 0 and wifi_occupied:
        stage = STAGES[1]
    elif person_count == 0:
        stage = STAGES[0]
    elif person_count > 0 and not has_metrics:
        stage = STAGES[1]
    elif binding_count == 0 and device_count == 0:
        stage = STAGES[2] if has_metrics else STAGES[1]
    elif binding_count == 0 and phone_nearby:
        stage = STAGES[4]
    elif binding_count == 0 and device_count > 0:
        stage = STAGES[3]
    else:
        stage = STAGES[5]

    zones = {
        "perceive": {
            "label": "Perceive",
            "status": "active" if (person_count > 0 or wifi_occupied) else "idle",
            "detail": f"{person_count} camera · WiFi {'active' if wifi_occupied else 'idle'}",
        },
        "understand": {
            "label": "Understand",
            "status": "active" if has_metrics or through_wall else "idle",
            "detail": "Through-wall motion" if through_wall else ("Body metrics" if has_metrics else "Building mesh"),
        },
        "connect": {
            "label": "Connect",
            "status": "active" if binding_count > 0 else ("ready" if device_count > 0 else "idle"),
            "detail": f"{binding_count} linked" if binding_count else f"{device_count} BLE signals",
        },
    }

    return {
        "stage": stage.id,
        "stage_index": stage.index,
        "stages_total": len(STAGES),
        "title": stage.title,
        "story": stage.story,
        "guidance": stage.guidance,
        "psychology": stage.psychology,
        "icon": stage.icon,
        "zones": zones,
        "journey": [
            {"id": s.id, "title": s.title, "icon": s.icon, "done": s.index < stage.index, "current": s.id == stage.id}
            for s in STAGES
        ],
    }
