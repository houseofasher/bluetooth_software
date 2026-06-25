#!/usr/bin/env node
/** #houseofasher tactical BLE server — TypeScript / Node.js */

import { BIND_ALL, PORT, createBleServer } from "./http-server.js";
import { startPoseSenseHub, stopPoseSenseHub } from "./posesense-server.js";
import { checkBluetoothReady, ensureScanLoop } from "./scanner.js";
import { HOP_INGEST_INTERVAL, STATE } from "./scan-state.js";
import { lanIp } from "../ble/frame-store.js";

async function main(): Promise<void> {
  const bindHost = BIND_ALL ? "0.0.0.0" : "127.0.0.1";
  const server = createBleServer();

  await new Promise<void>((resolve, reject) => {
    server.on("error", reject);
    server.listen(PORT, bindHost, () => resolve());
  });

  console.log(`#houseofasher tactical BLE HUD: http://127.0.0.1:${PORT}/`);

  await startPoseSenseHub();

  console.log(`Screen relay sender: http://127.0.0.1:${PORT}/relay`);
  if (BIND_ALL) {
    console.log(`LAN relay (phone): http://${lanIp()}:${PORT}/relay  [BLE_BIND_ALL=1]`);
  } else {
    console.log("Phone relay: set BLE_BIND_ALL=1 and restart, then use LAN IP in QR");
  }
  console.log(
    `CONTINUOUS SWEEP — domino hop ingest every ${HOP_INGEST_INTERVAL}s (no device-count stop).`,
  );

  const ready = await checkBluetoothReady();
  if (ready.ready) {
    if (ensureScanLoop()) console.log("Auto-started persistent BLE sweep.");
  } else {
    console.log(`Bluetooth not ready yet: ${ready.message}`);
  }

  process.on("SIGINT", () => {
    console.log("\nStopping…");
    STATE.scanShutdown = true;
    stopPoseSenseHub();
    server.close();
    process.exit(0);
  });
}

main().catch((e) => {
  console.error("FATAL:", e);
  process.exit(1);
});
