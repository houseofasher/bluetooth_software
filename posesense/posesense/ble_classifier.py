"""Deep BLE device identification — brand, model, category."""

from __future__ import annotations

import re

# Bluetooth SIG company identifiers (common consumer brands)
COMPANY_NAMES: dict[int, str] = {
    0x004C: "Apple",
    0x0075: "Samsung",
    0x00E0: "Google",
    0x0006: "Microsoft",
    0x0087: "Garmin",
    0x0093: "Sony",
    0x0059: "Nordic Semiconductor",
    0x0171: "Amazon",
    0x0310: "Xiaomi",
    0x0157: "Huawei",
    0x008A: "Bose",
    0x0066: "Jabra",
    0x012D: "OnePlus",
    0x02E5: "Fitbit",
    0x038F: "Tile",
}

APPLE_TYPES: dict[int, tuple[str, str, str]] = {
    # type_byte -> (category, model_hint, device_type)
    0x02: ("Apple", "iPhone / iPad", "phone"),
    0x03: ("Apple", "Mac", "laptop"),
    0x05: ("Apple", "AirPods", "audio"),
    0x07: ("Apple", "iPhone / iPad", "phone"),
    0x0A: ("Apple", "AirTag", "tracker"),
    0x0C: ("Apple", "HomePod", "audio"),
    0x0F: ("Apple", "iPhone / iPad", "phone"),
    0x10: ("Apple", "Apple Watch", "watch"),
    0x12: ("Apple", "AirPods", "audio"),
}

# Name patterns → (brand, model extract regex or None, device_type)
NAME_RULES: list[tuple[re.Pattern, str, str | None, str]] = [
    (re.compile(r"iPhone\s*(\d+\s*Pro\s*Max|\d+\s*Pro|\d+\s*Plus|\d+)?", re.I), "Apple", "iPhone", "phone"),
    (re.compile(r"iPad\s*(Pro|Air|Mini)?", re.I), "Apple", "iPad", "tablet"),
    (re.compile(r"Apple\s*Watch\s*(Ultra|SE|\d+)?", re.I), "Apple", "Apple Watch", "watch"),
    (re.compile(r"AirPods\s*(Pro|Max|\d+)?", re.I), "Apple", "AirPods", "audio"),
    (re.compile(r"Galaxy\s*(S\d+|Z\s*Fold|Z\s*Flip|A\d+|Note\s*\d+)[\w\s]*", re.I), "Samsung", None, "phone"),
    (re.compile(r"Galaxy\s*Watch[\w\s]*", re.I), "Samsung", "Galaxy Watch", "watch"),
    (re.compile(r"Galaxy\s*Buds[\w\s]*", re.I), "Samsung", "Galaxy Buds", "audio"),
    (re.compile(r"SM-[A-Z]\d{3,4}[\w]*", re.I), "Samsung", None, "phone"),
    (re.compile(r"Pixel\s*(\d+\s*Pro|\d+[aA]?)?", re.I), "Google", "Pixel", "phone"),
    (re.compile(r"Pixel\s*Watch", re.I), "Google", "Pixel Watch", "watch"),
    (re.compile(r"Pixel\s*Buds", re.I), "Google", "Pixel Buds", "audio"),
    (re.compile(r"OnePlus[\w\s\d]*", re.I), "OnePlus", None, "phone"),
    (re.compile(r"Redmi[\w\s\d]*", re.I), "Xiaomi", "Redmi", "phone"),
    (re.compile(r"Mi\s*Band[\w\s\d]*", re.I), "Xiaomi", "Mi Band", "watch"),
    (re.compile(r"WHOOP", re.I), "WHOOP", "WHOOP", "watch"),
    (re.compile(r"Fitbit[\w\s]*", re.I), "Fitbit", "Fitbit", "watch"),
    (re.compile(r"Garmin[\w\s]*", re.I), "Garmin", None, "watch"),
    (re.compile(r"WH-1000|WF-1000|LinkBuds", re.I), "Sony", None, "audio"),
    (re.compile(r"QuietComfort|Bose[\w\s]*", re.I), "Bose", None, "audio"),
    (re.compile(r"Beats[\w\s]*", re.I), "Apple", None, "audio"),
    (re.compile(r"JBL[\w\s-]*", re.I), "JBL", None, "audio"),
    (re.compile(r"Soundcore[\w\s-]*", re.I), "Soundcore", None, "audio"),
    (re.compile(r"(Earbuds|Buds|Headphones|Headset|Earphones)[\w\s-]*", re.I), "Unknown", None, "audio"),
    (re.compile(r"Tile[\w\s]*", re.I), "Tile", "Tile", "tracker"),
    (re.compile(r"AirTag", re.I), "Apple", "AirTag", "tracker"),
]

CATEGORY_ICONS = {
    "phone": "📱",
    "tablet": "📱",
    "watch": "⌚",
    "audio": "🎧",
    "tracker": "📍",
    "laptop": "💻",
    "unknown": "📡",
}

LIKELY_BODY_ZONE = {
    "phone": "Hand or pocket",
    "tablet": "Hand",
    "watch": "Wrist",
    "audio": "Ears / neck",
    "tracker": "Pocket, bag, or keychain",
    "laptop": "Bag or desk nearby",
    "unknown": "Unknown",
}


def _extract_model_from_name(name: str, brand: str, hint: str | None) -> str:
    if hint:
        m = re.search(rf"{re.escape(hint)}[\w\s\d]*", name, re.I)
        if m:
            return m.group(0).strip()
    if brand == "Samsung" and re.search(r"SM-", name, re.I):
        return name.strip()
    return hint or name if name != "Unknown" else "Unknown model"


def classify_device(
    name: str,
    manufacturer_data: dict[int, bytes] | None = None,
    service_uuids: list[str] | None = None,
    address: str = "",
) -> dict:
    """Return rich device identity: brand, model, category, likely body zone."""
    manufacturer_data = manufacturer_data or {}
    service_uuids = service_uuids or []
    raw_name = name if name and name != "Unknown" else ""

    brand: str | None = None
    model = raw_name or "Unknown device"
    device_type = "unknown"
    confidence = 0.3
    is_phone = False

    # Name-based rules (highest precision when name is broadcast)
    for pattern, rule_brand, hint, dtype in NAME_RULES:
        m = pattern.search(raw_name)
        if m:
            brand = rule_brand
            device_type = dtype
            model = _extract_model_from_name(raw_name, brand, hint)
            if m.lastindex and m.group(1):
                model = f"{hint or rule_brand} {m.group(0).strip()}".strip()
            else:
                model = m.group(0).strip() if m.group(0) else model
            confidence = 0.92
            is_phone = dtype in ("phone", "tablet")
            break

    # Manufacturer data
    for cid, data in manufacturer_data.items():
        cname = COMPANY_NAMES.get(cid)
        if cname and not brand:
            brand = cname

        if cid == 0x004C and data:  # Apple
            brand = "Apple"
            apple = APPLE_TYPES.get(data[0])
            if apple and confidence < 0.85:
                _, model_hint, dtype = apple
                if not raw_name:
                    model = model_hint
                device_type = dtype
                confidence = max(confidence, 0.86)
                is_phone = dtype in ("phone", "tablet")
            elif not raw_name:
                model = "Apple device"
                confidence = max(confidence, 0.55)
                device_type = device_type if device_type != "unknown" else "phone"
                is_phone = True

        if cid == 0x0075 and confidence < 0.7:  # Samsung
            brand = "Samsung"
            if not raw_name:
                model = "Galaxy device"
            device_type = device_type if device_type != "unknown" else "phone"
            is_phone = device_type == "phone"
            confidence = max(confidence, 0.72)

        if cid == 0x00E0 and confidence < 0.7:  # Google
            brand = "Google"
            if not raw_name:
                model = "Pixel device"
            device_type = device_type if device_type != "unknown" else "phone"
            is_phone = True
            confidence = max(confidence, 0.72)

    if not brand:
        for cid in manufacturer_data:
            if cid in COMPANY_NAMES:
                brand = COMPANY_NAMES[cid]
                break

    if not raw_name and address:
        short = address.replace(":", "")[-4:].upper()
        model = f"{brand or 'BLE'} ···{short}" if brand else f"Unknown ···{short}"

    display_name = model if model != "Unknown device" else (raw_name or f"Unknown ···{address[-5:]}" if address else "Unknown device")
    if brand and brand not in display_name and model != "Unknown model":
        display_name = f"{brand} {model}"

    icon = CATEGORY_ICONS.get(device_type, "📡")

    return {
        "brand": brand,
        "model": model,
        "display_name": display_name,
        "device_type": device_type,
        "device_category": device_type,
        "is_phone": is_phone,
        "manufacturer": brand,
        "confidence": round(confidence, 2),
        "icon": icon,
        "likely_body_zone": LIKELY_BODY_ZONE.get(device_type, "Unknown"),
        "detection_note": (
            "Identity from BLE advertisement name and manufacturer ID. "
            "Body placement refined by camera pose when linked to a person."
        ),
    }
