/** Shared PoseSense types (server + browser). */

export interface Landmark {
  x: number;
  y: number;
  z?: number;
  confidence?: number;
  name?: string;
}

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface BodyMetrics {
  height_cm: number | null;
  weight_kg_est: number | null;
  face_width_cm: number | null;
  face_height_cm: number | null;
  visibility_score: number;
  measurements_ready: boolean;
  visibility_message: string;
}

export interface PersonDetection {
  person_id: number;
  pose: Landmark[];
  face: Landmark[];
  left_hand: Landmark[];
  right_hand: Landmark[];
  bbox: BBox;
  motion_energy: number;
  metrics: BodyMetrics;
}

export interface DeviceIdentity {
  brand: string | null;
  model: string;
  display_name: string;
  device_type: string;
  is_phone: boolean;
  likely_body_zone: string;
  icon: string;
  confidence: number;
  address?: string;
  rssi?: number;
}

export interface TrackedTarget {
  person_id: number;
  ble_address: string | null;
  device: DeviceIdentity | null;
  placement: Record<string, unknown> | null;
  pose: Landmark[];
  face: Landmark[];
  left_hand: Landmark[];
  right_hand: Landmark[];
  bbox: BBox;
  motion_energy: number;
  rssi: number | null;
  bind_method: string;
  metrics: BodyMetrics;
  companion_devices: DeviceIdentity[];
}

export interface WiFiState {
  source: string;
  occupied: boolean;
  motion_energy: number;
  activity: string;
  through_wall: boolean;
  through_wall_confidence: number;
  zone: string;
  zone_x: number;
  home_detected: boolean;
  automation: Record<string, unknown>;
  message: string;
  spectrogram: number[][];
  through_wall_targets: Array<Record<string, unknown>>;
}

export interface LivePayload {
  mode: string;
  timestamp: number;
  wall_mode: boolean;
  narrative: Record<string, unknown>;
  wifi: WiFiState;
  camera: {
    status: string;
    status_message: string;
    width: number;
    height: number;
  };
  targets: TrackedTarget[];
  unbound_devices: Array<Record<string, unknown>>;
  bind_suggestions: Array<Record<string, unknown>>;
  bindings: Array<Record<string, unknown>>;
  person_count: number;
  device_count: number;
  disclaimer: string;
  pose_edge_groups: Array<{ name: string; edges: number[][]; color: string }>;
  hand_edges: number[][];
}
