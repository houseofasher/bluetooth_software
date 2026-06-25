/** BLE device identity from advertisement metadata. */

const COMPANY_NAMES: Record<number, string> = {
  0x004c: "Apple", 0x0075: "Samsung", 0x00e0: "Google", 0x05d6: "JLab", 0x05a7: "Samsung",
};

const ICONS: Record<string, string> = { phone: "📱", tablet: "📱", watch: "⌚", audio: "🎧", unknown: "📡" };

export function classifyDevice(
  name: string,
  manufacturerData: Record<string, string> | undefined,
  address: string,
  pairedName?: string | null,
): Record<string, unknown> {
  let rawName = name && name !== "Unknown" ? name : pairedName ?? "";
  let brand: string | null = null;
  let model = rawName || "Unknown device";
  let deviceType = "unknown";
  let confidence = 0.3;
  let isPhone = false;

  const lower = rawName.toLowerCase();
  if (/iphone|ipad|pixel|galaxy s|galaxy z|oneplus|redmi/i.test(rawName)) {
    brand = /iphone|ipad|airpods|beats/i.test(rawName) ? "Apple" : brand;
    if (/iphone|pixel|galaxy|oneplus|redmi/i.test(rawName)) {
      deviceType = "phone";
      isPhone = true;
      confidence = 0.9;
    }
    if (/ipad/i.test(rawName)) deviceType = "tablet";
    if (/airpods|buds|jlab|beats|bose|sony wh/i.test(rawName)) {
      deviceType = "audio";
      isPhone = false;
      confidence = 0.88;
    }
  }

  if (manufacturerData) {
    for (const [hex, data] of Object.entries(manufacturerData)) {
      const cid = parseInt(hex, 16);
      if (cid === 0x004c) {
        brand = "Apple";
        const byte = parseInt(data.slice(0, 2), 16);
        if ([0x05, 0x12].includes(byte)) {
          deviceType = "audio";
          model = rawName || "AirPods / Beats";
        } else if (byte === 0x10) {
          deviceType = "watch";
          model = rawName || "Apple Watch";
        } else if (!rawName) {
          deviceType = "phone";
          model = "iPhone (nearby)";
          isPhone = true;
          confidence = 0.68;
        }
      }
      if (cid === 0x05d6) {
        brand = "JLab";
        deviceType = "audio";
        model = rawName || "JLab earbuds";
        confidence = 0.88;
      }
      if (COMPANY_NAMES[cid] && !brand) brand = COMPANY_NAMES[cid];
    }
  }

  if (/jlab/i.test(rawName)) {
    brand = "JLab";
    deviceType = "audio";
    confidence = 0.9;
  }

  const display = brand && !model.includes(brand) ? `${brand} ${model}` : model;
  return {
    brand,
    model,
    display_name: display,
    device_type: deviceType,
    is_phone: isPhone || deviceType === "phone" || deviceType === "tablet",
    likely_body_zone: deviceType === "audio" ? "Ears / neck" : deviceType === "phone" ? "Hand or pocket" : "Unknown",
    icon: ICONS[deviceType] ?? "📡",
    confidence,
    address,
  };
}
