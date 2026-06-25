/** PoseSense 2027 — narrative-driven renderer */

const canvas = document.getElementById("stageCanvas");
const ctx = canvas.getContext("2d");
const bindBar = document.getElementById("bindBar");
const targetList = document.getElementById("targetList");
const deviceList = document.getElementById("deviceList");
const bodyStats = document.getElementById("bodyStats");
const journeyRail = document.getElementById("journeyRail");
const narrativeTitle = document.getElementById("narrativeTitle");
const narrativeStory = document.getElementById("narrativeStory");
const narrativeGuidance = document.getElementById("narrativeGuidance");
const narrativePsych = document.getElementById("narrativePsych");
const zonePerceive = document.getElementById("zonePerceive");
const zoneUnderstand = document.getElementById("zoneUnderstand");
const zoneConnect = document.getElementById("zoneConnect");
const wifiSpectrogram = document.getElementById("wifiSpectrogram");
const wifiSpecCtx = wifiSpectrogram?.getContext("2d");
const wallModeBtn = document.getElementById("wallModeBtn");

let ws, latestData = null, prevData = null, animStart = 0, animDur = 100;
let selectedPersonId = null, selectedDeviceAddr = null;
let wallModeEnabled = true;
let displayedMetrics = { h: 0, w: 0, fw: 0, fh: 0 };
const img = new Image();
let imgReady = false;
img.onload = () => { imgReady = true; };

const SKEL = {
  torso: "#818cf8",
  left_arm: "#34d399",
  right_arm: "#fbbf24",
  left_leg: "#c084fc",
  right_leg: "#f472b6",
  head_neck: "#22d3ee",
  handL: "#34d399",
  handR: "#fbbf24",
  joint: "#fde68a",
  face: "rgba(34,211,238,0.75)",
  linked: "#4ade80",
  wifiGhost: "rgba(167,139,250,0.85)",
};

function drawThroughWallGhosts(rect, wifi) {
  const ghosts = wifi?.through_wall_targets || [];
  if (!ghosts.length) return;

  for (const g of ghosts) {
    const gx = rect.ox + g.x * rect.dw;
    const gy = rect.oy + g.y * rect.dh;
    const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 400);
    const r = 28 + g.motion_energy * 40 * pulse;

    ctx.save();
    ctx.setLineDash([8, 6]);
    ctx.strokeStyle = SKEL.wifiGhost;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(gx, gy, r, 0, Math.PI * 2);
    ctx.stroke();

    const grad = ctx.createRadialGradient(gx, gy, 0, gx, gy, r);
    grad.addColorStop(0, "rgba(167,139,250,0.35)");
    grad.addColorStop(1, "transparent");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(gx, gy, r, 0, Math.PI * 2);
    ctx.fill();

    ctx.setLineDash([]);
    ctx.font = "600 11px Instrument Sans, Segoe UI, sans-serif";
    const label = `📡 ${g.label || "WiFi reflection"}`;
    const tw = ctx.measureText(label).width;
    ctx.fillStyle = "rgba(15, 18, 32, 0.92)";
    roundRect(ctx, gx - tw / 2 - 8, gy - r - 22, tw + 16, 18, 6);
    ctx.fill();
    ctx.strokeStyle = "rgba(167,139,250,0.6)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = SKEL.wifiGhost;
    ctx.fillText(label, gx - tw / 2, gy - r - 9);

    ctx.font = "500 10px Instrument Sans, Segoe UI, sans-serif";
    ctx.fillStyle = "rgba(251,191,36,0.9)";
    ctx.fillText(`Behind wall · ${Math.round((g.confidence || 0) * 100)}%`, gx - 52, gy + r + 14);
    ctx.restore();
  }
}

function drawWifiSpectrogram(wifi) {
  if (!wifiSpecCtx || !wifi?.spectrogram?.length) return;
  const w = wifiSpectrogram.width;
  const h = wifiSpectrogram.height;
  wifiSpecCtx.fillStyle = "#050810";
  wifiSpecCtx.fillRect(0, 0, w, h);

  const rows = wifi.spectrogram;
  const rowH = h / rows.length;
  rows.forEach((row, ri) => {
    const cols = row.length || 1;
    const colW = w / cols;
    row.forEach((val, ci) => {
      const v = Math.min(1, Math.max(0, val));
      const hue = 220 - v * 180;
      wifiSpecCtx.fillStyle = `hsla(${hue}, 85%, ${35 + v * 35}%, ${0.35 + v * 0.65})`;
      wifiSpecCtx.fillRect(ci * colW, ri * rowH, colW + 0.5, rowH + 0.5);
    });
  });
}

function updateWifiPanel(wifi, wallMode) {
  if (!wifi) return;
  const msg = document.getElementById("wifiMsg");
  if (msg) msg.textContent = wifi.message || "WiFi field idle";

  document.getElementById("wifiMotion").textContent = (wifi.motion_energy ?? 0).toFixed(2);
  document.getElementById("wifiZone").textContent = wifi.zone || "—";

  const auto = wifi.automation || {};
  const setAuto = (id, label, on) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = `${label}: ${on ? "ON" : "OFF"}`;
    el.className = "auto-chip" + (on ? " on" : " off");
  };
  setAuto("autoHome", "Home", wifi.home_detected);
  setAuto("autoLights", "Lights", auto.lights === "on");
  setAuto("autoWifi", "WiFi boost", auto.wifi_boost);

  if (wallModeBtn) {
    wallModeBtn.classList.toggle("active", wallMode);
    wallModeBtn.textContent = wallMode
      ? "📡 Wall mode ON — WiFi sees through camera blind spot"
      : "Wall mode OFF — WiFi presence only (no through-wall overlay)";
  }

  drawWifiSpectrogram(wifi);
}

function send(msg) { if (ws?.readyState === 1) ws.send(JSON.stringify(msg)); }
function lerp(a, b, t) { return a + (b - a) * t; }
function lerpPts(a, b, t) {
  if (!a?.length) return b || [];
  if (!b?.length) return a;
  return a.map((p, i) => {
    const q = b[i] || p;
    return { ...p, x: lerp(p.x, q.x, t), y: lerp(p.y, q.y, t), confidence: lerp(p.confidence || 0, q.confidence || 0, t) };
  });
}
function animVal(current, target, speed = 0.12) {
  if (target == null || isNaN(target)) return current;
  return lerp(current, target, speed);
}

function resizeCanvas() {
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * devicePixelRatio;
  canvas.height = rect.height * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();

function getImageRect(w, h) {
  if (!imgReady) return { ox: 0, oy: 0, dw: w, dh: h };
  const iw = img.naturalWidth, ih = img.naturalHeight;
  const scale = Math.min(w / iw, h / ih);
  const dw = iw * scale, dh = ih * scale;
  return { ox: (w - dw) / 2, oy: (h - dh) / 2, dw, dh };
}
function toCanvas(p, rect) {
  return { x: rect.ox + p.x * rect.dw, y: rect.oy + p.y * rect.dh, confidence: p.confidence };
}

function drawPoints(pts, rect, color, radius) {
  for (const p of pts) {
    if ((p.confidence ?? 0) < 0.22) continue;
    const c = toCanvas(p, rect);
    ctx.beginPath();
    ctx.arc(c.x, c.y, radius, 0, Math.PI * 2);
    const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, radius * 2);
    g.addColorStop(0, color);
    g.addColorStop(1, "transparent");
    ctx.fillStyle = g;
    ctx.fill();
  }
}

function drawEdges(pts, edges, rect, color, width) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = color;
  ctx.shadowBlur = 8;
  for (const [a, b] of edges) {
    const p1 = pts[a], p2 = pts[b];
    if (!p1 || !p2 || (p1.confidence ?? 0) < 0.22 || (p2.confidence ?? 0) < 0.22) continue;
    const c1 = toCanvas(p1, rect), c2 = toCanvas(p2, rect);
    ctx.beginPath();
    ctx.moveTo(c1.x, c1.y);
    ctx.lineTo(c2.x, c2.y);
    ctx.stroke();
  }
  ctx.shadowBlur = 0;
}

function drawFaceOval(face, rect) {
  if (face.length < 4) return;
  ctx.strokeStyle = SKEL.face;
  ctx.lineWidth = 1.8;
  ctx.shadowColor = SKEL.face;
  ctx.shadowBlur = 6;
  ctx.beginPath();
  face.forEach((p, i) => {
    if ((p.confidence ?? 0) < 0.15) return;
    const c = toCanvas(p, rect);
    i === 0 ? ctx.moveTo(c.x, c.y) : ctx.lineTo(c.x, c.y);
  });
  ctx.closePath();
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function interpTargets(t) {
  if (!latestData?.targets?.length) return [];
  if (!prevData?.targets?.length) return latestData.targets;
  return latestData.targets.map((tgt, i) => {
    const prev = prevData.targets[i];
    if (!prev || prev.person_id !== tgt.person_id) return tgt;
    return {
      ...tgt,
      pose: lerpPts(prev.pose, tgt.pose, t),
      face: lerpPts(prev.face, tgt.face, t),
      left_hand: lerpPts(prev.left_hand, tgt.left_hand, t),
      right_hand: lerpPts(prev.right_hand, tgt.right_hand, t),
    };
  });
}

function renderFrame() {
  const w = canvas.width / devicePixelRatio;
  const h = canvas.height / devicePixelRatio;
  ctx.clearRect(0, 0, w, h);

  if (imgReady) {
    const rect = getImageRect(w, h);
    ctx.drawImage(img, rect.ox, rect.oy, rect.dw, rect.dh);

    const t = Math.min(1, (performance.now() - animStart) / animDur);
    const targets = interpTargets(t);
    const edgeGroups = latestData?.pose_edge_groups || [];
    const handEdges = latestData?.hand_edges || [];

    for (const tgt of targets) {
      const pose = tgt.pose || [];
      for (const g of edgeGroups) {
        const col = SKEL[g.name] || g.color;
        drawEdges(pose, g.edges, rect, col, 2.8);
      }
      drawFaceOval(tgt.face || [], rect);
      drawEdges(tgt.left_hand || [], handEdges, rect, SKEL.handL, 2.2);
      drawEdges(tgt.right_hand || [], handEdges, rect, SKEL.handR, 2.2);
      drawPoints(tgt.left_hand || [], rect, SKEL.handL, 3);
      drawPoints(tgt.right_hand || [], rect, SKEL.handR, 3);
      drawPoints(pose, rect, SKEL.joint, 3.5);

      const b = tgt.bbox;
      const bx = rect.ox + b.x * rect.dw, by = rect.oy + b.y * rect.dh;
      const bw = b.w * rect.dw, bh = b.h * rect.dh;
      const bound = !!tgt.ble_address;
      const sel = tgt.person_id === selectedPersonId;

      ctx.strokeStyle = sel ? SKEL.right_arm : bound ? SKEL.linked : SKEL.head_neck;
      ctx.lineWidth = sel ? 2 : 1.5;
      ctx.setLineDash(bound ? [] : [6, 4]);
      ctx.strokeRect(bx, by, bw, bh);
      ctx.setLineDash([]);

      if (tgt.device && tgt.placement?.anchor) {
        drawDeviceBadge(tgt.device, tgt.placement, rect);
      } else if (tgt.device) {
        const label = tgt.device.display_name || tgt.ble_name || `Presence ${tgt.person_id}`;
        ctx.font = "600 12px Instrument Sans, Segoe UI, sans-serif";
        const tw = ctx.measureText(label).width;
        ctx.fillStyle = bound ? "rgba(74,222,128,0.9)" : "rgba(34,211,238,0.85)";
        roundRect(ctx, bx, by - 20, tw + 12, 18, 6);
        ctx.fill();
        ctx.fillStyle = "#04050a";
        ctx.fillText(label, bx + 6, by - 7);
      } else {
        const label = `Presence ${tgt.person_id}`;
        ctx.font = "600 12px Instrument Sans, Segoe UI, sans-serif";
        const tw = ctx.measureText(label).width;
        ctx.fillStyle = sel ? "rgba(251,191,36,0.9)" : "rgba(34,211,238,0.85)";
        roundRect(ctx, bx, by - 20, tw + 12, 18, 6);
        ctx.fill();
        ctx.fillStyle = "#04050a";
        ctx.fillText(label, bx + 6, by - 7);
      }

      for (const comp of tgt.companion_devices || []) {
        if (comp.placement?.anchor) drawDeviceBadge(comp, comp.placement, rect);
      }

      if (tgt.metrics?.measurements_ready) {
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.font = "600 11px Instrument Sans, Segoe UI, sans-serif";
        ctx.fillText(
          `${Math.round(tgt.metrics.height_cm)} cm · ~${Math.round(tgt.metrics.weight_kg_est)} kg`,
          bx + 4, by + bh - 6
        );
      } else if (tgt.metrics?.visibility_message) {
        ctx.fillStyle = "rgba(251,191,36,0.85)";
        ctx.font = "500 10px Instrument Sans, Segoe UI, sans-serif";
        ctx.fillText(tgt.metrics.visibility_message.slice(0, 42), bx + 4, by + bh - 6);
      }
    }

    if (latestData?.wifi?.through_wall && latestData?.wall_mode) {
      drawThroughWallGhosts(rect, latestData.wifi);
    }
  }
  requestAnimationFrame(renderFrame);
}

function roundRect(c, x, y, w, h, r) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r);
  c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r);
  c.arcTo(x, y, x + w, y, r);
  c.closePath();
}

function drawDeviceBadge(device, placement, rect) {
  const anchor = toCanvas(placement.anchor, rect);
  const ax = anchor.x, ay = anchor.y;

  // Pin line from anchor to label
  const labelLines = [
    `${device.icon || "📡"} ${device.brand || "?"} ${device.model || ""}`.trim(),
    `↳ ${placement.label}`,
  ];
  ctx.font = "600 11px Instrument Sans, Segoe UI, sans-serif";
  const lineW = Math.max(...labelLines.map(l => ctx.measureText(l).width)) + 16;
  const boxH = 36;
  let lx = ax + 14, ly = ay - boxH / 2;
  if (lx + lineW > rect.ox + rect.dw) lx = ax - lineW - 14;

  ctx.strokeStyle = "rgba(167,139,250,0.8)";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(ax, ay);
  ctx.lineTo(lx, ly + boxH / 2);
  ctx.stroke();
  ctx.setLineDash([]);

  // Anchor dot
  ctx.beginPath();
  ctx.arc(ax, ay, 5, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(167,139,250,0.95)";
  ctx.shadowColor = "#a78bfa";
  ctx.shadowBlur = 10;
  ctx.fill();
  ctx.shadowBlur = 0;

  // Label box
  ctx.fillStyle = "rgba(15, 18, 32, 0.92)";
  roundRect(ctx, lx, ly, lineW, boxH, 8);
  ctx.fill();
  ctx.strokeStyle = "rgba(167,139,250,0.5)";
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.fillStyle = "#f0f4fc";
  ctx.fillText(labelLines[0], lx + 8, ly + 14);
  ctx.fillStyle = "#22d3ee";
  ctx.font = "500 10px Instrument Sans, Segoe UI, sans-serif";
  ctx.fillText(labelLines[1], lx + 8, ly + 28);
}

requestAnimationFrame(renderFrame);

canvas.addEventListener("click", (e) => {
  if (!latestData?.targets) return;
  const cvs = canvas.getBoundingClientRect();
  const w = canvas.width / devicePixelRatio;
  const h = canvas.height / devicePixelRatio;
  const ir = getImageRect(w, h);
  const nx = (e.clientX - cvs.left - ir.ox) / ir.dw;
  const ny = (e.clientY - cvs.top - ir.oy) / ir.dh;
  for (const t of latestData.targets) {
    const b = t.bbox;
    if (nx >= b.x && nx <= b.x + b.w && ny >= b.y && ny <= b.y + b.h) {
      selectedPersonId = t.person_id;
      bindBar.className = "bind-prompt active";
      bindBar.textContent = `Presence ${t.person_id} selected — choose a signal below to link identity.`;
      renderUI();
      return;
    }
  }
});

function updateNarrative(n) {
  if (!n) return;
  narrativeTitle.innerHTML = `<span>${n.icon || "◈"}</span> ${n.title}`;
  narrativeStory.textContent = n.story;
  narrativeGuidance.textContent = n.guidance;
  narrativePsych.textContent = n.psychology;

  journeyRail.innerHTML = (n.journey || []).map(s => `
    <div class="journey-step ${s.done ? "done" : ""} ${s.current ? "current" : ""}">
      <span class="icon">${s.icon}</span>
      <span class="label">${s.title}</span>
    </div>`).join("");

  const zones = n.zones || {};
  [[zonePerceive, zones.perceive], [zoneUnderstand, zones.understand], [zoneConnect, zones.connect]].forEach(([el, z]) => {
    if (!el || !z) return;
    el.className = "zone" + (z.status === "active" ? " active" : z.status === "ready" ? " ready" : "");
    el.querySelector(".zone-detail").textContent = z.detail;
  });
}

function renderUI() {
  const data = latestData;
  if (!data) return;

  updateNarrative(data.narrative);
  updateWifiPanel(data.wifi, data.wall_mode ?? wallModeEnabled);

  document.getElementById("personCount").textContent = data.person_count;
  document.getElementById("deviceCount").textContent = data.device_count;
  document.getElementById("boundCount").textContent = data.bindings.length;
  const phones = data.unbound_devices.filter(d => d.is_phone).length + data.bindings.filter(b => b.is_phone).length;
  document.getElementById("phoneCount").textContent = phones;
  document.getElementById("countBadge").textContent = `${data.person_count} · ${data.device_count} signals`;
  document.getElementById("trustBody").textContent = [
    data.disclaimer || "",
    data.ble_scan?.tips?.length ? "\n\nTips: " + data.ble_scan.tips.join(" · ") : "",
  ].join("");

  const suggestions = data.bind_suggestions || [];
  if (suggestions.length && data.person_count > 0 && !data.targets[0]?.ble_address) {
    const top = suggestions[0];
    bindBar.className = "bind-prompt active";
    bindBar.innerHTML = `Camera sees you — likely device: <strong>${top.icon} ${top.display_name}</strong> (${top.rssi} dBm). `
      + `<button type="button" class="suggest-bind-btn" data-addr="${top.address}">Link now</button> `
      + `or pick from Radio Signatures below.`;
    bindBar.querySelector(".suggest-bind-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      send({ action: "bind", person_id: data.targets[0].person_id, address: top.address });
      bindBar.className = "bind-prompt";
      bindBar.textContent = "Identity linked. Phone/device now tracked on your body.";
    });
  } else if (!selectedPersonId) {
    bindBar.className = "bind-prompt";
    bindBar.textContent = data.person_count
      ? "Hold phone up in view to auto-link, or tap yourself on camera then a signal below."
      : "Step into camera view. Unlock phone so Bluetooth broadcasts its name.";
  }

  const identityCard = document.getElementById("identityCard");
  const t0 = data.targets[0];
  if (t0?.device && identityCard) {
    const d = t0.device;
    const p = t0.placement;
    const companions = (t0.companion_devices || []).map(c =>
      `<div class="id-row"><span class="id-key">${c.icon} Also</span><span class="id-val">${c.display_name} · ${c.placement?.label || c.likely_body_zone || ""}</span></div>`
    ).join("");
    identityCard.innerHTML = `
      <div class="id-row"><span class="id-key">Brand</span><span class="id-val">${d.brand || "Unknown"}</span></div>
      <div class="id-row"><span class="id-key">Model</span><span class="id-val">${d.model || "—"}</span></div>
      <div class="id-row"><span class="id-key">Type</span><span class="id-val">${d.icon} ${d.device_type}</span></div>
      <div class="id-row"><span class="id-key">On body</span><span class="id-val highlight">${p?.label || d.likely_body_zone || "—"}</span></div>
      <div class="id-row"><span class="id-key">Side</span><span class="id-val">${p?.side || "—"}</span></div>
      <div class="id-row"><span class="id-key">Link</span><span class="id-val">${t0.bind_method || "manual"}</span></div>
      <div class="id-row"><span class="id-key">Confidence</span><span class="id-val">${Math.round((p?.confidence || d.confidence || 0) * 100)}%</span></div>${companions}`;
    identityCard.style.display = "block";
  } else if (identityCard) {
    identityCard.innerHTML = `<p class="id-empty">Link a device to see brand, model, and body placement.</p>`;
  }

  if (t0?.metrics) {
    const m = t0.metrics;
    const ready = m.measurements_ready;
    const visEl = document.getElementById("visibilityStatus");
    if (visEl) {
      visEl.textContent = m.visibility_message || "";
      visEl.className = "visibility-status" + (ready ? " ready" : "");
    }
    if (ready && m.height_cm) displayedMetrics.h = animVal(displayedMetrics.h, m.height_cm);
    if (ready && m.weight_kg_est) displayedMetrics.w = animVal(displayedMetrics.w, m.weight_kg_est);
    if (ready && m.face_width_cm) displayedMetrics.fw = animVal(displayedMetrics.fw, m.face_width_cm);
    if (ready && m.face_height_cm) displayedMetrics.fh = animVal(displayedMetrics.fh, m.face_height_cm);
    bodyStats.innerHTML = `
      <div class="metric-tile"><div class="val">${ready && m.height_cm ? Math.round(displayedMetrics.h) + "<small style='font-size:0.5em;opacity:0.7'> cm</small>" : "—"}</div><div class="lbl">Height</div></div>
      <div class="metric-tile"><div class="val">${ready && m.weight_kg_est ? Math.round(displayedMetrics.w) + "<small style='font-size:0.5em;opacity:0.7'> kg</small>" : "—"}</div><div class="lbl">Weight est.</div></div>
      <div class="metric-tile"><div class="val">${ready && m.face_width_cm ? displayedMetrics.fw.toFixed(1) + "<small style='font-size:0.5em;opacity:0.7'> cm</small>" : "—"}</div><div class="lbl">Face width</div></div>
      <div class="metric-tile"><div class="val">${ready && m.face_height_cm ? displayedMetrics.fh.toFixed(1) + "<small style='font-size:0.5em;opacity:0.7'> cm</small>" : "—"}</div><div class="lbl">Face height</div></div>`;
  }

  targetList.innerHTML = "";
  if (!data.targets.length) {
    const wifiGhost = data.wifi?.through_wall_targets?.[0];
    if (wifiGhost && data.wall_mode) {
      targetList.innerHTML = `<li class="wifi-ghost-li" style="cursor:default;border-color:rgba(167,139,250,0.4)">
        <strong>📡 WiFi-only presence</strong><span class="rssi">${Math.round((wifiGhost.confidence || 0) * 100)}%</span>
        <div class="sub">${wifiGhost.label} · ${wifiGhost.zone} · camera blind</div></li>`;
    } else {
      targetList.innerHTML = `<li style="cursor:default;opacity:0.7">Awaiting presence in field of view…</li>`;
    }
  }
  data.targets.forEach(t => {
    const li = document.createElement("li");
    const d = t.device;
    li.className = (t.person_id === selectedPersonId ? "selected " : "") + (t.ble_address ? "bound " : "") + (t.ble_is_phone ? "phone" : "");
    const idLine = d
      ? `${d.brand || "?"} ${d.model} · ${t.placement?.label || d.likely_body_zone || ""}`
      : (t.ble_name || "Identity unlinked");
    li.innerHTML = `<strong>Presence ${t.person_id}</strong><span class="rssi">${t.rssi ?? "—"}</span>
      <div class="sub">${idLine}</div>`;
    li.onclick = () => {
      selectedPersonId = t.person_id;
      if (t.ble_address) send({ action: "unbind", person_id: t.person_id });
      renderUI();
    };
    targetList.appendChild(li);
  });

  deviceList.innerHTML = "";
  if (!data.unbound_devices.length) {
    deviceList.innerHTML = `<li style="cursor:default;opacity:0.7">All signals linked or scanning…</li>`;
  }
  data.unbound_devices.forEach(d => {
    const li = document.createElement("li");
    li.className = (d.address === selectedDeviceAddr ? "selected " : "")
      + (d.is_phone ? "phone " : "")
      + (d.suggested ? "suggested " : "")
      + (d.device_type === "audio" ? "audio " : "");
    const tag = d.is_phone ? `<span class="tag tag-phone">Phone</span>` : `<span class="tag">${d.device_type}</span>`;
    const zone = d.placement_hint?.label || d.likely_body_zone || "Unknown zone";
    const suggest = d.suggested ? `<div class="sub suggest-line">★ Likely yours — tap to link</div>` : "";
    li.innerHTML = `<strong>${d.icon} ${d.display_name || d.name}</strong>${tag}<span class="rssi">${d.rssi} dBm</span>
      <div class="sub">${d.brand || "Unknown brand"} · ${d.model || "—"}</div>
      <div class="sub">Likely: ${zone} · ${Math.round(d.type_confidence * 100)}% ID</div>${suggest}`;
    li.onclick = () => {
      if (selectedPersonId !== null) {
        send({ action: "bind", person_id: selectedPersonId, address: d.address });
        selectedPersonId = null;
        bindBar.className = "bind-prompt";
        bindBar.textContent = "Identity linked. The system now tracks body and device as one.";
      } else {
        selectedDeviceAddr = d.address;
        bindBar.className = "bind-prompt active";
        bindBar.textContent = `"${d.name}" selected — tap your presence on the camera view.`;
      }
      renderUI();
    };
    deviceList.appendChild(li);
  });
}

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => {
    document.getElementById("pulseDot").classList.add("on");
    document.getElementById("modeBadge").textContent = "Live";
    document.getElementById("modeBadge").classList.add("live");
  };
  ws.onclose = () => {
    document.getElementById("pulseDot").classList.remove("on");
    document.getElementById("modeBadge").classList.remove("live");
    setTimeout(connect, 2000);
  };
  ws.onmessage = (ev) => {
    prevData = latestData;
    latestData = JSON.parse(ev.data);
    animStart = performance.now();
    if (latestData.camera?.jpeg && latestData.camera.jpeg !== img._lastJpeg) {
      img._lastJpeg = latestData.camera.jpeg;
      img.src = "data:image/jpeg;base64," + latestData.camera.jpeg;
    }
    if (typeof latestData.wall_mode === "boolean") wallModeEnabled = latestData.wall_mode;
    renderUI();
  };
}
connect();

if (wallModeBtn) {
  wallModeBtn.addEventListener("click", () => {
    wallModeEnabled = !wallModeEnabled;
    send({ action: "set_wall_mode", enabled: wallModeEnabled });
    wallModeBtn.classList.toggle("active", wallModeEnabled);
    wallModeBtn.textContent = wallModeEnabled
      ? "📡 Wall mode ON — WiFi sees through camera blind spot"
      : "Wall mode OFF — WiFi presence only (no through-wall overlay)";
  });
}
