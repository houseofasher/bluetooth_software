/** Narrative stages for PoseSense 2027 UI. */

const STAGES = [
  { id: "awaiting", index: 0, title: "Lab Ready", icon: "◌", story: "Wayne opened PoseSense. The room is quiet — waiting for a presence to enter the field.", guidance: "Step into the camera. The system will begin mapping when it sees you.", psychology: "Anticipation without anxiety: one clear next step lowers cognitive load." },
  { id: "presence", index: 1, title: "Presence Detected", icon: "◎", story: "Someone entered the lab. Motion registered — the sensors awaken.", guidance: "Hold still for a moment while the mesh finds your shoulders and hips.", psychology: "Immediate feedback confirms 'I am seen'." },
  { id: "mapping", index: 2, title: "Body Mapped", icon: "◈", story: "Dr. Emily moved through the room. PoseSense traced her full body with startling precision.", guidance: "Move naturally. Face the camera; show hands for finger tracking.", psychology: "Visual proof builds trust faster than numbers alone." },
  { id: "identity", index: 3, title: "Who Is This?", icon: "◉", story: "Wayne's next question: not just movement — identity.", guidance: "Select yourself on camera, then choose your device below.", psychology: "Choice restores agency when multiple signals compete." },
  { id: "recognition", index: 4, title: "Signal Recognized", icon: "📱", story: "A phone's Bluetooth radio broadcast its signature from the chip inside.", guidance: "Hold your phone near you. Link it to confirm identity.", psychology: "Transparency about HOW detection works prevents privacy paranoia." },
  { id: "harmony", index: 5, title: "Unified Tracking", icon: "✦", story: "Body and device linked — position, identity, and motion woven together.", guidance: "You're fully tracked. Move freely.", psychology: "Flow state: perceive + understand + connect merge." },
  { id: "through_wall", index: 6, title: "Through the Wall", icon: "📡", story: "The lens saw nothing — but the WiFi field rippled. Body reflections revealed someone behind the wall.", guidance: "WiFi CSI detects motion through walls. Camera confirms line of sight.", psychology: "Invisible sensing feels magical — show which sensor sees what." },
] as const;

type Stage = (typeof STAGES)[number];

export function resolveNarrative(opts: {
  person_count: number;
  device_count: number;
  binding_count: number;
  phone_nearby: boolean;
  has_metrics: boolean;
  wifi_occupied: boolean;
  through_wall: boolean;
}): Record<string, unknown> {
  let stage: Stage = STAGES[0];
  if (opts.through_wall) stage = STAGES[6];
  else if (opts.person_count === 0 && opts.wifi_occupied) stage = STAGES[1];
  else if (opts.person_count === 0) stage = STAGES[0];
  else if (opts.person_count > 0 && !opts.has_metrics) stage = STAGES[1];
  else if (opts.binding_count === 0 && opts.device_count === 0) stage = opts.has_metrics ? STAGES[2] : STAGES[1];
  else if (opts.binding_count === 0 && opts.phone_nearby) stage = STAGES[4];
  else if (opts.binding_count === 0 && opts.device_count > 0) stage = STAGES[3];
  else stage = STAGES[5];

  return {
    stage: stage.id,
    title: stage.title,
    story: stage.story,
    guidance: stage.guidance,
    psychology: stage.psychology,
    icon: stage.icon,
    zones: {
      perceive: { label: "Perceive", status: opts.person_count > 0 || opts.wifi_occupied ? "active" : "idle", detail: `${opts.person_count} camera · WiFi ${opts.wifi_occupied ? "active" : "idle"}` },
      understand: { label: "Understand", status: opts.has_metrics || opts.through_wall ? "active" : "idle", detail: opts.through_wall ? "Through-wall motion" : opts.has_metrics ? "Body metrics" : "Building mesh" },
      connect: { label: "Connect", status: opts.binding_count > 0 ? "active" : opts.device_count > 0 ? "ready" : "idle", detail: opts.binding_count > 0 ? `${opts.binding_count} linked` : `${opts.device_count} BLE signals` },
    },
    journey: STAGES.map((s) => ({ id: s.id, title: s.title, icon: s.icon, done: s.index < stage.index, current: s.id === stage.id })),
  };
}
