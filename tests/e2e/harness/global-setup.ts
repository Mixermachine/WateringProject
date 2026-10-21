/**
 * Bootstraps a running Home Assistant for the e2e suite and leaves the ids the
 * specs need in `.auth/state.json` (gitignored).
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import {
  createEntry,
  ensureOnboarded,
  findDeviceId,
  listEntries,
  setOptions,
  waitForHomeAssistant,
  waitForState,
} from "./api";

const STATE_PATH = resolve(process.cwd(), ".auth/state.json");

async function ensureEntry(
  token: string,
  domain: string,
): Promise<string> {
  const entries = await listEntries(token);
  const existing = entries.find((entry) => entry.domain === domain);
  if (existing !== undefined) {
    return existing.entry_id;
  }
  const created = await createEntry(token, domain);
  return created.entry_id;
}

export default async function globalSetup(): Promise<void> {
  await waitForHomeAssistant();
  const tokens = await ensureOnboarded();

  // fake_plants first: its `notify.fake_phone` service must exist before the
  // options flow validates the notify target.
  const fakeEntryId = await ensureEntry(tokens.access_token, "fake_plants");
  await waitForState(tokens.access_token, "sensor.ficus_moisture", () => true);

  const wateringEntryId = await ensureEntry(tokens.access_token, "watering_project");
  await waitForState(tokens.access_token, "sensor.watering_project_plants_needing_water", () => true);

  const entries = await listEntries(tokens.access_token);
  const watering = entries.find((entry) => entry.entry_id === wateringEntryId);
  if (watering === undefined || watering.state !== "loaded") {
    throw new Error(`watering_project entry not loaded: ${JSON.stringify(watering)}`);
  }

  const hasNotify = (watering.options ?? {})["notify_service"] === "fake_phone";
  await setOptions(tokens.access_token, wateringEntryId, {
    moisture_default: 70,
    battery_suspect_days: 30,
    include_devices: [],
    exclude_devices: [],
    notify_enabled: false,
    notify_service: hasNotify ? "fake_phone" : "",
    notify_repeat_hours: 24,
    notify_url: "/watering-project",
  });

  const monsteraDeviceId = await findDeviceId(tokens.access_token, "Monstera");
  const cactusDeviceId = await findDeviceId(tokens.access_token, "Cactus");

  mkdirSync(dirname(STATE_PATH), { recursive: true });
  writeFileSync(
    STATE_PATH,
    JSON.stringify(
      {
        tokens,
        fakeEntryId,
        wateringEntryId,
        monsteraDeviceId,
        cactusDeviceId,
        baseUrl: process.env["HA_URL"] ?? "http://localhost:8123",
      },
      null,
      2,
    ),
  );
}
