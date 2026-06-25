# PoseSense

Live **camera pose + Bluetooth identity + WiFi CSI** fusion — inspired by CMU WiFi sensing research and Wayne's lab narrative. The dashboard shows what each sensor actually sees, including **through-wall motion** when the camera is blind.

## What it does

- **Camera** — MediaPipe full-body pose, face mesh, hands (line-of-sight only)
- **Bluetooth** — Device brand/model/type from advertisements; click-to-bind identity to a person
- **WiFi CSI** — Body reflections in router signal perturbations; motion behind walls when camera sees nothing
- **Smart-home simulation** — Home/lights/climate triggers when WiFi detects occupancy
- **2027 narrative UI** — Story-driven stages (Lab Ready → Through the Wall)

## Sensor honesty

| Sensor | What it actually detects |
|--------|-------------------------|
| Camera | Skeleton when you are in view |
| Bluetooth | Device identity from chip advertisements (not bounce off your body) |
| WiFi CSI | Motion/presence from RF reflections — can work through drywall in lab/research setups |

Consumer WiFi cannot render a full skeleton through walls on its own; PoseSense shows **ghost presence** from CSI when wall mode is on and the camera is empty.

## Quick start

```bash
cd posesense-bluetooth
pip install -r requirements.txt

# Full stack: BLE + webcam + WiFi CSI simulation (through-wall demo)
python server.py --mode ble --camera 0 --wifi sim

# Windows real WiFi RSSI as coarse CSI proxy
python server.py --mode ble --camera 0 --wifi rssi

# ESP32 CSI hardware (UDP JSON on port 9000)
python server.py --mode ble --camera 0 --wifi esp32
```

Open **http://127.0.0.1:8766**

Toggle **Wall mode** on the dashboard to overlay WiFi-only presences when someone moves behind the camera's blind spot.

## WiFi modes

| Mode | Source | Use case |
|------|--------|----------|
| `sim` | Synthetic CSI subcarriers | Demo through-wall without hardware |
| `rssi` | `netsh wlan` scan variance | Real but coarse on Windows |
| `esp32` | UDP port 9000 | Research ESP32 CSI firmware |

## Architecture

```
Camera (LOS pose) ──┐
BLE (device ID)   ──┼── FusionEngine ── WebSocket ── Dashboard
WiFi CSI (motion) ──┘         │
                              └── Smart-home automation state
```

When `wall_mode` is on and camera count = 0 but WiFi detects motion → **Through the Wall** narrative stage + purple ghost overlay.

## Next steps

- Push ESP32 CSI firmware for real subcarrier data
- Fuse WiFi zone estimate with BLE trilateration
- BLE 6.0 Channel Sounding for finer ranging