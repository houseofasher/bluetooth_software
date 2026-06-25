"""Fuse camera-visible persons with nearby BLE devices."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from .body_placement import BodyPlacement, infer_placement, person_holding_phone
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
        }


@dataclass
class TrackedTarget:
    person_id: int
    ble_address: str | None
    device: dict | None
    placement: dict | None
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
    companion_devices: list[dict] = field(default_factory=list)

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
        self._companion_bindings: dict[int, list[str]] = {}

    def _phone_candidates(self, devices: list[BleDevice]) -> list[BleDevice]:
        return [
            d for d in devices
            if d.is_phone or d.device_type in ("phone", "tablet")
            or (d.brand == "Apple" and d.device_type != "audio" and d.device_type != "watch")
        ]

    def _audio_candidates(self, devices: list[BleDevice]) -> list[BleDevice]:
        return [d for d in devices if d.device_type == "audio"]

    def _try_hand_proximity_bind(self, persons: list[PersonDetection], unbound_d: list[BleDevice]) -> None:
        """When camera sees phone-in-hand, bind strongest nearby phone signal."""
        bound = set(self.bindings.values())
        unbound_p = [p for p in persons if p.person_id not in self.bindings]
        if not unbound_p or not unbound_d:
            return

        for person in unbound_p:
            holding, _side = person_holding_phone(person.pose, person.left_hand, person.right_hand)
            if not holding:
                continue

            phones = self._phone_candidates(unbound_d)
            if not phones:
                phones = [d for d in unbound_d if d.brand == "Apple"]
            if not phones:
                continue

            best = max(phones, key=lambda d: d.rssi)
            if best.rssi >= -92:
                self.bindings[person.person_id] = best.address
                self.bind_methods[person.person_id] = "auto-hand-proximity"
                bound.add(best.address)
                unbound_d = [d for d in unbound_d if d.address not in bound]
                break

    def _try_audio_companion_bind(self, persons: list[PersonDetection], unbound_d: list[BleDevice]) -> None:
        """Attach nearby headphones to person already holding / using phone."""
        audio = self._audio_candidates(unbound_d)
        if not audio:
            return

        for person in persons:
            pid = person.person_id
            if pid not in self.bindings:
                continue
            companions = self._companion_bindings.setdefault(pid, [])
            for dev in sorted(audio, key=lambda d: -d.rssi):
                if dev.address in companions or dev.rssi < -94:
                    continue
                companions.append(dev.address)
                if len(companions) >= 2:
                    break

    def ingest_ble(self, address: str, name: str, rssi: float, ts: float, meta: dict | None = None) -> None:
        meta = meta or {}
        if address not in self.devices:
            self.devices[address] = BleDevice(address=address, name=name, rssi=rssi)
        dev = self.devices[address]
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

    def unbind(self, person_id: int) -> None:
        self.bindings.pop(person_id, None)
        self.bind_methods.pop(person_id, None)
        self._companion_bindings.pop(person_id, None)

    def _device_priority(self, dev: BleDevice) -> tuple:
        return (
            int(dev.is_phone or dev.device_type == "audio"),
            dev.type_confidence,
            dev.rssi,
        )

    def _try_auto_bind(self, persons: list[PersonDetection]) -> None:
        bound = set(self.bindings.values())
        unbound_p = [p for p in persons if p.person_id not in self.bindings]
        unbound_d = [
            d for d in self.devices.values()
            if d.address not in bound and time.time() - d.last_seen < 20
        ]
        if not unbound_p or not unbound_d:
            self._try_audio_companion_bind(persons, unbound_d)
            return

        self._try_hand_proximity_bind(persons, unbound_d)
        bound = set(self.bindings.values())
        unbound_p = [p for p in persons if p.person_id not in self.bindings]
        unbound_d = [
            d for d in self.devices.values()
            if d.address not in bound and time.time() - d.last_seen < 20
        ]
        if not unbound_p or not unbound_d:
            self._try_audio_companion_bind(persons, unbound_d)
            return

        phones = self._phone_candidates(unbound_d)
        if len(unbound_p) == 1 and len(phones) == 1:
            self.bindings[unbound_p[0].person_id] = phones[0].address
            self.bind_methods[unbound_p[0].person_id] = "auto-phone"
            self._try_audio_companion_bind(persons, unbound_d)
            return

        if len(unbound_p) == 1 and len(unbound_d) == 1:
            self.bindings[unbound_p[0].person_id] = unbound_d[0].address
            self.bind_methods[unbound_p[0].person_id] = "auto"
            self._try_audio_companion_bind(persons, unbound_d)
            return

        if len(unbound_p) == 1 and phones:
            best_phone = max(phones, key=lambda d: d.rssi)
            if best_phone.rssi >= -88 and len(phones) <= 8:
                self.bindings[unbound_p[0].person_id] = best_phone.address
                self.bind_methods[unbound_p[0].person_id] = "auto-strongest-phone"
                self._try_audio_companion_bind(persons, unbound_d)
                return

        best_score, best_pair = 0.32, None
        for person in unbound_p:
            for dev in unbound_d:
                self._record_motion(person.person_id, person.motion_energy, dev.address, dev.motion_energy)
                score = self._correlate(
                    self._person_motion_history.get(person.person_id, []),
                    self._device_motion_history.get(dev.address, []),
                )
                if dev.is_phone or dev.device_type == "phone":
                    score += 0.15
                if dev.rssi >= -75:
                    score += 0.08
                if score > best_score:
                    best_score, best_pair = score, (person.person_id, dev.address)

        if best_pair:
            pid, addr = best_pair
            self.bindings[pid] = addr
            self.bind_methods[pid] = "auto-phone" if self.devices[addr].is_phone else "auto"

        self._try_audio_companion_bind(persons, unbound_d)

    def update(self, persons: list[PersonDetection]) -> list[TrackedTarget]:
        self._try_auto_bind(persons)
        targets: list[TrackedTarget] = []

        for person in persons:
            addr = self.bindings.get(person.person_id)
            dev = self.devices.get(addr) if addr else None
            m = person.metrics

            device_info = None
            placement_info = None
            if dev:
                placement = self._placement_for(person, dev)
                device_info = dev.identity_dict()
                device_info["address"] = dev.address
                device_info["rssi"] = dev.rssi
                placement_info = self._placement_dict(placement)

            companion_devices = []
            for addr in self._companion_bindings.get(person.person_id, []):
                cdev = self.devices.get(addr)
                if not cdev or time.time() - cdev.last_seen > 20:
                    continue
                c_payload = cdev.identity_dict()
                c_payload["address"] = cdev.address
                c_payload["rssi"] = cdev.rssi
                c_payload["placement"] = self._placement_dict(self._placement_for(person, cdev))
                companion_devices.append(c_payload)

            targets.append(TrackedTarget(
                person_id=person.person_id,
                ble_address=addr,
                device=device_info,
                placement=placement_info,
                in_frame=True,
                pose=person.pose,
                face=person.face,
                left_hand=person.left_hand,
                right_hand=person.right_hand,
                bbox=person.bbox,
                motion_energy=person.motion_energy,
                rssi=dev.rssi if dev else None,
                bind_method=self.bind_methods.get(person.person_id, "none"),
                metrics={
                    "height_cm": m.height_cm,
                    "weight_kg_est": m.weight_kg_est,
                    "face_width_cm": m.face_width_cm,
                    "face_height_cm": m.face_height_cm,
                    "visibility_score": m.visibility_score,
                    "measurements_ready": m.measurements_ready,
                    "visibility_message": m.visibility_message,
                },
                companion_devices=companion_devices,
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
            "motion_energy": round(dev.motion_energy, 3),
            "history": dev.buffer.values[-30:],
            "std": round(stats["std"], 2),
            "placement_hint": placement,
        }

    def unbound_devices(self, persons: list[PersonDetection] | None = None) -> list[dict]:
        bound = set(self.bindings.values())
        for addrs in self._companion_bindings.values():
            bound.update(addrs)
        now = time.time()
        primary = persons[0] if persons else None
        result = []
        for dev in sorted(self.devices.values(), key=lambda d: self._device_priority(d), reverse=True):
            if dev.address in bound or now - dev.last_seen > 25:
                continue
            payload = self._device_payload(dev, primary)
            payload["suggested"] = self._is_suggested(dev, persons)
            result.append(payload)
        return result[:40]

    def _is_suggested(self, dev: BleDevice, persons: list[PersonDetection] | None) -> bool:
        if not persons:
            return dev.is_phone or dev.device_type == "audio"
        person = persons[0]
        holding, _ = person_holding_phone(person.pose, person.left_hand, person.right_hand)
        if holding and (dev.is_phone or dev.brand == "Apple"):
            return dev.rssi >= max(-92, max((d.rssi for d in self._phone_candidates(list(self.devices.values()))), default=-999) - 3)
        if dev.device_type == "audio" and dev.rssi >= -93:
            return True
        return False

    def bind_suggestions(self, persons: list[PersonDetection]) -> list[dict]:
        if not persons:
            return []
        person = persons[0]
        if person.person_id in self.bindings:
            return []
        holding, side = person_holding_phone(person.pose, person.left_hand, person.right_hand)
        bound = set(self.bindings.values())
        candidates = [
            d for d in self.devices.values()
            if d.address not in bound and time.time() - d.last_seen < 20
        ]
        phones = self._phone_candidates(candidates)
        picks = phones if phones else candidates
        picks = sorted(picks, key=lambda d: self._device_priority(d), reverse=True)[:3]
        out = []
        for dev in picks:
            out.append({
                "address": dev.address,
                "display_name": dev.display_name,
                "brand": dev.brand,
                "device_type": dev.device_type,
                "icon": dev.icon,
                "rssi": dev.rssi,
                "reason": (
                    f"Camera sees phone in {side} hand — strongest match"
                    if holding and dev in phones
                    else "Strongest phone signal nearby"
                    if dev.is_phone
                    else "Strongest BLE signal nearby"
                ),
            })
        return out

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
