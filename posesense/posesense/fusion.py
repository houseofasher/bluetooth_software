"""Fuse camera-visible persons with nearby BLE devices."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from .body_placement import BodyPlacement, infer_placement
from .camera_tracker import PersonDetection
from .motion_engine import RssiBuffer


@dataclass
class BleDevice:
    address: str
    name: str
    rssi: float
    brand: str | None = None
    model: str = "Unknown"
    display_name: str = "Unknown device"
    device_type: str = "unknown"
    is_phone: bool = False
    likely_body_zone: str = "Unknown"
    icon: str = "📡"
    type_confidence: float = 0.3
    source: str = "ble_advertisement"
    is_paired: bool = False
    is_live_signal: bool = True
    scan_note: str = "Live BLE advertisement."
    buffer: RssiBuffer = field(default_factory=lambda: RssiBuffer(40))
    last_seen: float = 0.0

    @property
    def motion_energy(self) -> float:
        return min(1.0, self.buffer.stats()["std"] / 6.0)

    def identity_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "display_name": self.display_name,
            "device_type": self.device_type,
            "is_phone": self.is_phone,
            "likely_body_zone": self.likely_body_zone,
            "icon": self.icon,
            "confidence": self.type_confidence,
            "source": self.source,
            "is_paired": self.is_paired,
            "is_live_signal": self.is_live_signal,
            "scan_note": self.scan_note,
        }


@dataclass
class TrackedTarget:
    person_id: int
    ble_address: str | None
    device: dict | None
    placement: dict | None
    devices: list[dict]
    in_frame: bool
    pose: list[dict]
    face: list[dict]
    left_hand: list[dict]
    right_hand: list[dict]
    bbox: dict
    motion_energy: float
    rssi: float | None
    bind_method: str
    metrics: dict

    # Back-compat accessors
    @property
    def ble_name(self) -> str | None:
        return self.device.get("display_name") if self.device else None

    @property
    def ble_device_type(self) -> str | None:
        return self.device.get("device_type") if self.device else None

    @property
    def ble_is_phone(self) -> bool:
        return bool(self.device.get("is_phone")) if self.device else False


class FusionEngine:
    def __init__(self) -> None:
        self.devices: dict[str, BleDevice] = {}
        self.bindings: dict[int, str] = {}
        self.bind_methods: dict[int, str] = {}
        self._person_motion_history: dict[int, list[float]] = {}
        self._device_motion_history: dict[str, list[float]] = {}
        self._prev_pose: dict[int, list[dict]] = {}
        self._prev_hands: dict[str, list[dict]] = {}
        self._history_len = 24

    def ingest_ble(self, address: str, name: str, rssi: float, ts: float, meta: dict | None = None) -> None:
        meta = meta or {}
        if address not in self.devices:
            self.devices[address] = BleDevice(address=address, name=name, rssi=rssi)
        dev = self.devices[address]
        if meta.get("source") == "windows_paired" and dev.is_live_signal and ts - dev.last_seen < 15:
            return
        dev.name = name
        dev.rssi = rssi
        dev.brand = meta.get("brand", dev.brand)
        dev.model = meta.get("model", dev.model)
        dev.display_name = meta.get("display_name", name)
        dev.device_type = meta.get("device_type", dev.device_type)
        dev.is_phone = meta.get("is_phone", dev.is_phone)
        dev.likely_body_zone = meta.get("likely_body_zone", dev.likely_body_zone)
        dev.icon = meta.get("icon", dev.icon)
        dev.type_confidence = meta.get("confidence", dev.type_confidence)
        dev.source = meta.get("source", dev.source)
        dev.is_paired = meta.get("is_paired", dev.is_paired)
        dev.is_live_signal = meta.get("is_live_signal", dev.is_live_signal)
        dev.scan_note = meta.get("scan_note", dev.scan_note)
        dev.buffer.add(rssi, ts)
        dev.last_seen = ts

    def bind_manual(self, person_id: int, address: str) -> bool:
        if address not in self.devices:
            return False
        for pid, addr in list(self.bindings.items()):
            if addr == address:
                del self.bindings[pid]
                self.bind_methods.pop(pid, None)
        self.bindings[person_id] = address
        self.bind_methods[person_id] = "manual"
        return True

    def unbind(self, person_id: int) -> None:
        self.bindings.pop(person_id, None)
        self.bind_methods.pop(person_id, None)

    def _hand_motion_delta(self, person_id: int, hand: list[dict], side: str) -> float:
        key = f"{person_id}_{side}"
        prev = self._prev_hands.get(key, [])
        if not hand or not prev or len(hand) != len(prev):
            self._prev_hands[key] = hand
            return 0.0
        total = sum(
            math.hypot(hand[i]["x"] - prev[i]["x"], hand[i]["y"] - prev[i]["y"])
            for i in range(min(len(hand), len(prev)))
        )
        self._prev_hands[key] = hand
        return total

    def _record_motion(self, person_id: int, energy: float, address: str, dev_energy: float) -> None:
        self._person_motion_history.setdefault(person_id, []).append(energy)
        self._device_motion_history.setdefault(address, []).append(dev_energy)
        self._person_motion_history[person_id] = self._person_motion_history[person_id][-self._history_len:]
        self._device_motion_history[address] = self._device_motion_history[address][-self._history_len:]

    @staticmethod
    def _correlate(a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n < 5:
            return 0.0
        a, b = a[-n:], b[-n:]
        ma, mb = sum(a) / n, sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        da = math.sqrt(sum((x - ma) ** 2 for x in a))
        db = math.sqrt(sum((x - mb) ** 2 for x in b))
        return num / (da * db) if da > 1e-6 and db > 1e-6 else 0.0

    def _placement_for(self, person: PersonDetection, dev: BleDevice) -> BodyPlacement:
        stats = dev.buffer.stats()
        return infer_placement(
            device_type=dev.device_type,
            pose=person.pose,
            left_hand=person.left_hand,
            right_hand=person.right_hand,
            left_hand_motion=self._hand_motion_delta(person.person_id, person.left_hand, "L"),
            right_hand_motion=self._hand_motion_delta(person.person_id, person.right_hand, "R"),
            rssi_trend=stats.get("slope", 0),
        )

    @staticmethod
    def _placement_dict(p: BodyPlacement) -> dict:
        return {
            "zone": p.zone,
            "label": p.label,
            "side": p.side,
            "anchor": p.anchor,
            "confidence": round(p.confidence, 2),
            "method": p.method,
        }

    def _auto_attach_candidates(self) -> list[BleDevice]:
        now = time.time()
        candidates = [
            d for d in self.devices.values()
            if d.device_type in ("phone", "audio", "watch") and now - d.last_seen < 15
        ]
        return sorted(
            candidates,
            key=lambda d: (
                -int(d.is_phone),
                -int(d.device_type == "audio"),
                -int(d.is_live_signal),
                -d.rssi,
            ),
        )

    def _associated_devices_for(self, person: PersonDetection, person_count: int) -> list[BleDevice]:
        """Devices that should be displayed on this person without manual clicks."""
        devices: list[BleDevice] = []
        manual_addr = self.bindings.get(person.person_id)
        if manual_addr and manual_addr in self.devices:
            devices.append(self.devices[manual_addr])

        # If there is only one visible person, attach the user's phone/headphones
        # automatically. With multiple people, keep correlation/manual binding to
        # avoid assigning everyone's devices to the wrong body.
        if person_count == 1:
            seen = {d.address for d in devices}
            for dev in self._auto_attach_candidates():
                if dev.address in seen:
                    continue
                devices.append(dev)
                seen.add(dev.address)

        return devices

    def _device_with_placement(self, person: PersonDetection, dev: BleDevice) -> dict:
        placement = self._placement_for(person, dev)
        info = dev.identity_dict()
        info["address"] = dev.address
        info["rssi"] = dev.rssi
        info["placement"] = self._placement_dict(placement)
        return info

    def _try_auto_bind(self, persons: list[PersonDetection]) -> None:
        bound = set(self.bindings.values())
        unbound_p = [p for p in persons if p.person_id not in self.bindings]
        unbound_d = [d for d in self.devices.values() if d.address not in bound and time.time() - d.last_seen < 6]
        if not unbound_p or not unbound_d:
            return

        phones = [d for d in unbound_d if d.is_phone]
        if len(unbound_p) == 1 and len(phones) == 1:
            self.bindings[unbound_p[0].person_id] = phones[0].address
            self.bind_methods[unbound_p[0].person_id] = "auto-phone"
            return

        if len(unbound_p) == 1 and len(unbound_d) == 1:
            self.bindings[unbound_p[0].person_id] = unbound_d[0].address
            self.bind_methods[unbound_p[0].person_id] = "auto"
            return

        best_score, best_pair = 0.42, None
        for person in unbound_p:
            for dev in unbound_d:
                self._record_motion(person.person_id, person.motion_energy, dev.address, dev.motion_energy)
                score = self._correlate(
                    self._person_motion_history.get(person.person_id, []),
                    self._device_motion_history.get(dev.address, []),
                )
                if dev.is_phone:
                    score += 0.12
                if score > best_score:
                    best_score, best_pair = score, (person.person_id, dev.address)

        if best_pair:
            pid, addr = best_pair
            self.bindings[pid] = addr
            self.bind_methods[pid] = "auto-phone" if self.devices[addr].is_phone else "auto"

    def update(self, persons: list[PersonDetection]) -> list[TrackedTarget]:
        self._try_auto_bind(persons)
        targets: list[TrackedTarget] = []

        for person in persons:
            linked_devices = [
                self._device_with_placement(person, dev)
                for dev in self._associated_devices_for(person, len(persons))
            ]
            primary = linked_devices[0] if linked_devices else None
            addr = primary.get("address") if primary else None
            m = person.metrics

            device_info = primary
            placement_info = primary.get("placement") if primary else None
            bind_method = self.bind_methods.get(person.person_id)
            if not bind_method and linked_devices:
                bind_method = "auto-camera"

            targets.append(TrackedTarget(
                person_id=person.person_id,
                ble_address=addr,
                device=device_info,
                placement=placement_info,
                devices=linked_devices,
                in_frame=True,
                pose=person.pose,
                face=person.face,
                left_hand=person.left_hand,
                right_hand=person.right_hand,
                bbox=person.bbox,
                motion_energy=person.motion_energy,
                rssi=primary.get("rssi") if primary else None,
                bind_method=bind_method or "none",
                metrics={
                    "height_cm": m.height_cm,
                    "weight_kg_est": m.weight_kg_est,
                    "face_width_cm": m.face_width_cm,
                    "face_height_cm": m.face_height_cm,
                    "visibility_score": m.visibility_score,
                    "measurements_ready": m.measurements_ready,
                    "visibility_message": m.visibility_message,
                },
            ))
        return targets

    def _device_payload(self, dev: BleDevice, person: PersonDetection | None = None) -> dict:
        stats = dev.buffer.stats()
        placement = None
        if person:
            placement = self._placement_dict(self._placement_for(person, dev))
        return {
            "address": dev.address,
            "name": dev.display_name,
            "brand": dev.brand,
            "model": dev.model,
            "display_name": dev.display_name,
            "rssi": dev.rssi,
            "device_type": dev.device_type,
            "is_phone": dev.is_phone,
            "likely_body_zone": dev.likely_body_zone,
            "icon": dev.icon,
            "type_confidence": dev.type_confidence,
            "source": dev.source,
            "is_paired": dev.is_paired,
            "is_live_signal": dev.is_live_signal,
            "scan_note": dev.scan_note,
            "motion_energy": round(dev.motion_energy, 3),
            "history": dev.buffer.values[-30:],
            "std": round(stats["std"], 2),
            "placement_hint": placement,
        }

    def unbound_devices(self, persons: list[PersonDetection] | None = None) -> list[dict]:
        bound = set(self.bindings.values())
        auto_attached = set()
        if persons and len(persons) == 1:
            auto_attached = {d.address for d in self._auto_attach_candidates()}
        now = time.time()
        primary = persons[0] if persons else None
        result = []
        for dev in sorted(self.devices.values(), key=lambda d: (-int(d.is_phone), -d.rssi)):
            if dev.address in bound or dev.address in auto_attached or now - dev.last_seen > 12:
                continue
            result.append(self._device_payload(dev, primary))
        return result

    def bound_summary(self) -> list[dict]:
        items = []
        for pid, addr in self.bindings.items():
            dev = self.devices.get(addr)
            if not dev:
                continue
            items.append({
                "person_id": pid,
                "address": addr,
                **dev.identity_dict(),
                "rssi": dev.rssi,
                "method": self.bind_methods.get(pid, "unknown"),
            })
        return items
