/** Infer body placement + phone-in-hand detection. */

import type { Landmark } from "./types.js";

const L_SHOULDER = 11, R_SHOULDER = 12, L_ELBOW = 13, R_ELBOW = 14, L_WRIST = 15, R_WRIST = 16;
const L_HIP = 23, R_HIP = 24, NOSE = 0, L_EAR = 7, R_EAR = 8;

function kp(pose: Landmark[], idx: number): Landmark | null {
  const p = pose[idx];
  return p && (p.confidence ?? 0) > 0.25 ? p : null;
}

function wristRaised(w: Landmark, e: Landmark, s: Landmark): boolean {
  return w.y < e.y && e.y < s.y + 0.05;
}

export function personHoldingPhone(pose: Landmark[], leftHand: Landmark[], rightHand: Landmark[]): [boolean, string | null] {
  const lw = kp(pose, L_WRIST), rw = kp(pose, R_WRIST);
  const le = kp(pose, L_ELBOW), re = kp(pose, R_ELBOW);
  const ls = kp(pose, L_SHOULDER), rs = kp(pose, R_SHOULDER);
  const nose = kp(pose, NOSE);

  const presenting = (w: Landmark, e: Landmark, s: Landmark, hand: Landmark[]) =>
    hand.length > 8 || wristRaised(w, e, s) || !!(nose && w.y < s.y + 0.18 && Math.abs(w.x - s.x) < 0.35);

  if (lw && le && ls && presenting(lw, le, ls, leftHand)) return [true, "left"];
  if (rw && re && rs && presenting(rw, re, rs, rightHand)) return [true, "right"];
  return [false, null];
}

export function inferPlacement(
  deviceType: string,
  pose: Landmark[],
  leftHand: Landmark[],
  rightHand: Landmark[],
): Record<string, unknown> {
  const lw = kp(pose, L_WRIST), rw = kp(pose, R_WRIST);
  const le = kp(pose, L_ELBOW), re = kp(pose, R_ELBOW);
  const ls = kp(pose, L_SHOULDER), rs = kp(pose, R_SHOULDER);
  const lear = kp(pose, L_EAR), rear = kp(pose, R_EAR);
  const nose = kp(pose, NOSE);

  if (deviceType === "audio") {
    const anchor = lear && rear ? { x: (lear.x + rear.x) / 2, y: (lear.y + rear.y) / 2, confidence: 0.7 } : nose ?? { x: 0.5, y: 0.35, confidence: 0.5 };
    return { zone: "ear", label: "Head / ears", side: "both", anchor, confidence: 0.75, method: "type_default" };
  }

  if (deviceType === "phone" || deviceType === "tablet") {
    if (lw && le && ls && wristRaised(lw, le, ls) && leftHand.length > 10)
      return { zone: "hand", label: "Left hand (holding device)", side: "left", anchor: lw, confidence: 0.88, method: "hand_pose" };
    if (rw && re && rs && wristRaised(rw, re, rs) && rightHand.length > 10)
      return { zone: "hand", label: "Right hand (holding device)", side: "right", anchor: rw, confidence: 0.88, method: "hand_pose" };
    if (lw && rw) {
      const anchor = lw.y > rw.y ? lw : rw;
      const side = anchor === lw ? "left" : "right";
      return { zone: "hand", label: `${side} hand (likely)`, side, anchor, confidence: 0.55, method: "type_default" };
    }
  }

  return { zone: "nearby", label: "On person (uncertain)", side: null, anchor: nose ?? { x: 0.5, y: 0.5, confidence: 0.2 }, confidence: 0.35, method: "type_default" };
}
