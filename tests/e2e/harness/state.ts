import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { Page } from "@playwright/test";

import {
  browserTokens,
  callService,
  setOptions,
  sleep,
  waitForState,
  type Tokens,
} from "./api";

export interface HarnessState {
  tokens: Tokens;
  fakeEntryId: string;
  wateringEntryId: string;
  monsteraDeviceId: string;
  cactusDeviceId: string;
  baseUrl: string;
}

function load(): HarnessState {
  const path = resolve(process.cwd(), ".auth/state.json");
  return JSON.parse(readFileSync(path, "utf8")) as HarnessState;
}

export const state: HarnessState = load();
export const token = state.tokens.access_token;

const PLANTS: Array<[string, string]> = [
  ["sensor.ficus_moisture", "42"],
  ["sensor.orchid_moisture", "65"],
  ["sensor.monstera_moisture", "12.5"],
  ["sensor.basil_moisture", "unavailable"],
  ["sensor.cactus_moisture", "91"],
];

/** Return the instance to the committed fixture baseline. */
export async function resetBaseline(): Promise<void> {
  for (const [entityId, value] of PLANTS) {
    await callService(token, "fake_plants", "set_moisture", { entity_id: entityId, value });
  }
  await callService(token, "fake_plants", "set_battery", {
    entity_id: "sensor.monstera_battery",
    value: "0",
  });
  await callService(token, "fake_plants", "age_battery", {
    entity_id: "sensor.monstera_battery",
    days: 0,
  });

  await setOptions(token, state.wateringEntryId, {
    moisture_default: 70,
    battery_suspect_days: 30,
    include_devices: [],
    exclude_devices: [],
    notify_enabled: false,
    notify_service: "fake_phone",
    notify_repeat_hours: 24,
    notify_url: "/watering-project",
  });

  await waitForState(token, "sensor.watering_project_plants_needing_water", (value) => value === "3");
}

export async function setMoisture(entityId: string, value: string): Promise<void> {
  await callService(token, "fake_plants", "set_moisture", { entity_id: entityId, value });
}

export async function enableNotifications(): Promise<void> {
  await setOptions(token, state.wateringEntryId, {
    moisture_default: 70,
    battery_suspect_days: 30,
    include_devices: [],
    exclude_devices: [],
    notify_enabled: true,
    notify_service: "fake_phone",
    notify_repeat_hours: 24,
    notify_url: "/watering-project",
  });
}

export async function excludeCactus(): Promise<void> {
  await setOptions(token, state.wateringEntryId, {
    moisture_default: 70,
    battery_suspect_days: 30,
    include_devices: [],
    exclude_devices: [state.cactusDeviceId],
    notify_enabled: false,
    notify_service: "fake_phone",
    notify_repeat_hours: 24,
    notify_url: "/watering-project",
  });
}

/** Open the dashboard with a pre-seeded token and wait for the card. */
export async function openDashboard(page: Page): Promise<void> {
  await page.addInitScript(await browserTokens(state.tokens));
  await page.goto("/watering-project");
  await expectCardReady(page);
}

export async function openDashboardWithoutReloadWait(page: Page): Promise<void> {
  await page.addInitScript(await browserTokens(state.tokens));
}

/** The card is only ready once the subscription delivered its first payload. */
export async function expectCardReady(page: Page): Promise<void> {
  const card = page.locator("watering-project-card");
  await card.waitFor({ state: "attached" });
  await card.locator("[data-section]").first().waitFor({ state: "visible", timeout: 30_000 });
}

export async function waitForReloadedOptions(): Promise<void> {
  // Options save triggers an entry reload; give it a moment before asserting.
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const stateResponse = await fetch(
      `${state.baseUrl}/api/config/config_entries/entry`,
      { headers: { authorization: `Bearer ${token}` } },
    );
    const entries = (await stateResponse.json()) as Array<{ entry_id: string; state: string }>;
    const entry = entries.find((item) => item.entry_id === state.wateringEntryId);
    if (entry?.state === "loaded") {
      return;
    }
    await sleep(500);
  }
  throw new Error("watering_project entry did not reload");
}
