// bluetooth-scan.ts — local Python scanner (primary) + browser connect (optional fallback).

export type HexString = `0x${string}`;

export type NameSource = "broadcast" | "paired" | "gatt" | "inferred" | "address";
export type ProximityZone = "immediate" | "near" | "far" | "unknown";
export type ScanPhase = "idle" | "running" | "resolving" | "completed" | "failed";

export interface HealthStatus {
  ready: boolean;
  message: string;
  reason?: string;
}

export interface ScannerLocation {
  latitude: number | null;
  longitude: number | null;
  accuracyMeters: number | null;
  address: string | null;
  addressShort: string | null;
  source: string | null;
  ready: boolean;
}

export interface DeviceLocationContext {
  coLocated: boolean;
  estimatedAddress: string | null;
  estimatedAddressShort: string | null;
  scannerLatitude: number | null;
  scannerLongitude: number | null;
  contextNote: string;
}

export interface PulledDeviceData {
  ok: boolean;
  address: string;
  data: Record<string, string | number>;
  errors: string[];
  pulledAt: number;
}

export interface ScannedDevice {
  id: string;
  displayName: string;
  name: string;
  nameSource: NameSource;
  broadcastName: string | null;
  manufacturer: string | null;
  inferredDetail: string | null;
  rssi: number | null;
  txPower: number | null;
  distanceMeters: number | null;
  distanceFeet: number | null;
  distanceMiles: number | null;
  distanceLabel: string;
  proximityZone: ProximityZone;
  distanceNote: string;
  location: DeviceLocationContext;
  pulledData: PulledDeviceData | null;
  pullStatus: "ready" | "ok" | "failed";
  uuids: string[];
  source?: string;
  lastSeen: number;
}

export interface ScanSnapshot {
  phase: ScanPhase;
  running: boolean;
  error: string | null;
  devices: ScannedDevice[];
  count: number;
  scannerLocation: ScannerLocation;
  zeroResultHint: string | null;
}

export interface ScanOptions {
  baseUrl?: string;
  pollIntervalMs?: number;
  signal?: AbortSignal;
  onUpdate?: (snapshot: ScanSnapshot) => void;
}

export interface ScanHandle {
  stop: () => Promise<void>;
  getSnapshot: () => ScanSnapshot | null;
}

export interface ConnectOptions {
  optionalServices?: BluetoothServiceUUID[];
  serviceUuid?: BluetoothServiceUUID;
  characteristicUuid?: BluetoothCharacteristicUUID;
  signal?: AbortSignal;
}

export interface ConnectedDevice {
  device: BluetoothDevice;
  server: BluetoothRemoteGATTServer;
  disconnect: () => void;
  readOnce?: () => Promise<DataView>;
}

const DEFAULT_BASE = "http://127.0.0.1:8765";

function assertNotAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw new Error("Aborted.");
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  const data = (await res.json()) as T & { error?: string };
  if (!res.ok) throw new Error(data.error ?? res.statusText);
  return data;
}

export class BluetoothClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string = DEFAULT_BASE) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  public async checkHealth(): Promise<HealthStatus> {
    return fetchJson<HealthStatus>(`${this.baseUrl}/api/health`);
  }

  public async getDevices(): Promise<ScanSnapshot> {
    return fetchJson<ScanSnapshot>(`${this.baseUrl}/api/devices`);
  }

  public async getScannerLocation(): Promise<ScannerLocation> {
    return fetchJson<ScannerLocation>(`${this.baseUrl}/api/location`);
  }

  public async setScannerLocation(
    latitude: number,
    longitude: number,
    accuracyMeters?: number,
  ): Promise<ScannerLocation & { message?: string }> {
    return fetchJson(`${this.baseUrl}/api/location`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ latitude, longitude, accuracyMeters }),
    });
  }

  public async pullDeviceData(address: string): Promise<PulledDeviceData> {
    return fetchJson<PulledDeviceData>(`${this.baseUrl}/api/pull`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address }),
    });
  }

  public async startScan(opts: ScanOptions = {}): Promise<ScanHandle> {
    assertNotAborted(opts.signal);

    const health = await this.checkHealth();
    if (!health.ready) {
      throw new Error(health.message);
    }

    await fetchJson(`${this.baseUrl}/api/scan`, { method: "POST" });

    let latest: ScanSnapshot | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;
    const interval = opts.pollIntervalMs ?? 400;

    const pollOnce = async () => {
      assertNotAborted(opts.signal);
      latest = await this.getDevices();
      opts.onUpdate?.(latest);
    };

    await pollOnce();
    timer = setInterval(() => {
      pollOnce().catch(() => {});
    }, interval);

    const stop = async () => {
      if (timer) clearInterval(timer);
      timer = null;
      await fetch(`${this.baseUrl}/api/stop`, { method: "POST" }).catch(() => {});
      await pollOnce();
    };

    opts.signal?.addEventListener("abort", () => {
      stop().catch(() => {});
    });

    return {
      stop,
      getSnapshot: () => latest,
    };
  }

  public async connectViaBrowser(opts: ConnectOptions = {}): Promise<ConnectedDevice> {
    assertNotAborted(opts.signal);

    if (typeof navigator === "undefined" || !("bluetooth" in navigator)) {
      throw new Error("Web Bluetooth not available in this browser.");
    }

    const device = await navigator.bluetooth.requestDevice({
      acceptAllDevices: true,
      optionalServices: opts.optionalServices ?? [],
    });

    const onGattDisconnected = () => {};
    device.addEventListener("gattserverdisconnected", onGattDisconnected);

    const server = await device.gatt?.connect();
    if (!server) throw new Error("Failed to connect to GATT server.");

    const disconnect = () => {
      device.removeEventListener("gattserverdisconnected", onGattDisconnected);
      try {
        server.disconnect();
      } catch {
        // ignore
      }
    };

    let readOnce: ConnectedDevice["readOnce"];
    if (opts.serviceUuid && opts.characteristicUuid) {
      const serviceUuid = opts.serviceUuid;
      const characteristicUuid = opts.characteristicUuid;
      readOnce = async () => {
        const service = await server.getPrimaryService(serviceUuid);
        const ch = await service.getCharacteristic(characteristicUuid);
        return ch.readValue();
      };
    }

    return { device, server, disconnect, readOnce };
  }
}
