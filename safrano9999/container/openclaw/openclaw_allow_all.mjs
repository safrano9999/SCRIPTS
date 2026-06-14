#!/usr/bin/env node
import fs from "node:fs";
import {
  approveDevicePairing,
  listDevicePairing,
} from "file:///app/dist/plugin-sdk/device-bootstrap.js";

const identity = JSON.parse(fs.readFileSync("/root/.openclaw/identity/device.json", "utf8"));
const { pending } = await listDevicePairing();
for (const request of pending.filter((item) => item.deviceId === identity.deviceId)) {
  await approveDevicePairing(request.requestId, {
    callerScopes: ["operator.admin", "operator.pairing", "operator.read", "operator.write"],
  });
}
