import { expect, test, type Page } from "@playwright/test";

import { callService, getState, sleep, waitForState } from "../harness/api";
import {
  enableNotifications,
  excludeCactus,
  expectCardReady,
  openDashboard,
  resetBaseline,
  setMoisture,
  state,
  token,
  waitForReloadedOptions,
} from "../harness/state";

// Not `serial`: one failure must not skip the remaining scenarios. Each test
// resets the fake plants and the options it depends on in `beforeEach`, so a
// single worker can still run them in isolation.

const card = (page: Page) => page.locator("watering-project-card");
const section = (page: Page, key: string) => card(page).locator(`[data-section="${key}"]`);

test.beforeEach(async ({}, testInfo) => {
  testInfo.setTimeout(180_000);
  await resetBaseline();
});

test("1. mounts the card without console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });

  await openDashboard(page);

  await expect(card(page)).toBeVisible();
  expect(errors).toEqual([]);
});

test("2. renders sections that match the needs_water entities", async ({ page }) => {
  await openDashboard(page);

  await expect(section(page, "dry").locator(".count")).toHaveText("3");
  await expect(section(page, "no_data").locator(".count")).toHaveText("1");
  await expect(section(page, "healthy").locator(".count")).toHaveText("1");
  await expect(section(page, "suspect")).toHaveCount(0);

  const ficus = await getState(token, "binary_sensor.ficus_needs_water");
  const cactus = await getState(token, "binary_sensor.cactus_needs_water");
  expect(ficus?.state).toBe("on");
  expect(cactus?.state).toBe("off");

  await expect(card(page).locator('.plant-row[data-status="dry"]')).toHaveCount(3);
});

test("3. section 1 appears only when a battery goes suspect", async ({ page }) => {
  await openDashboard(page);
  await expect(section(page, "suspect")).toHaveCount(0);

  await callService(token, "fake_plants", "age_battery", {
    entity_id: "sensor.monstera_battery",
    days: 31,
  });
  await waitForState(token, "sensor.monstera_status", (value) => value === "suspect_battery");

  await page.reload();
  await expectCardReady(page);

  const suspect = section(page, "suspect");
  await expect(suspect.locator(".count")).toHaveText("1");
  await expect(suspect).toContainText("Monstera");
});

test("4. hysteresis keeps 72 % dry and releases at 76 % live", async ({ page }) => {
  await openDashboard(page);

  await setMoisture("sensor.ficus_moisture", "72");
  await sleep(2_000);
  await expect(card(page).locator('[data-plant-id="' + (await plantId(page, "Ficus")) + '"]')).toHaveCount(1);
  await expect(section(page, "dry")).toContainText("Ficus");

  await setMoisture("sensor.ficus_moisture", "76");
  await waitForState(token, "sensor.ficus_status", (value) => value === "healthy");

  // No reload: the websocket push must move the row.
  await expect(section(page, "healthy")).toContainText("Ficus");
  await expect(section(page, "dry")).not.toContainText("Ficus");
});

test("5. collapse state survives a reload when the card has an id", async ({ page }) => {
  await openDashboard(page);

  const header = section(page, "dry").locator(".section-header");
  await expect(header).toHaveAttribute("aria-expanded", "true");
  await header.click();
  await expect(header).toHaveAttribute("aria-expanded", "false");

  await page.reload();
  await expectCardReady(page);

  await expect(section(page, "dry").locator(".section-header")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await expect(section(page, "dry").locator(".section-body")).toBeHidden();
});

test("6. rooms sort alphabetically with Unassigned last", async ({ page }) => {
  await setMoisture("sensor.cactus_moisture", "20");
  await waitForState(token, "sensor.cactus_status", (value) => value === "dry");
  await openDashboard(page);

  const rooms = section(page, "dry").locator(".room-title");
  await expect(rooms).toHaveText(["Bedroom", "Kitchen", "Unassigned"]);
});

test("7. an excluded device leaves the list and shows in the footer", async ({ page }) => {
  await openDashboard(page);
  await expect(section(page, "healthy")).toContainText("Cactus");

  await excludeCactus();
  await waitForReloadedOptions();
  await page.reload();
  await expectCardReady(page);

  await expect(card(page).locator(".excluded")).toContainText("Cactus");
  await expect(card(page).locator(".excluded")).toContainText("option");
  await expect(card(page).locator(".plant-name", { hasText: "Cactus" })).toHaveCount(0);
});

test("8. notify.fake_phone fires once per drought", async ({ page }) => {
  await enableNotifications();
  await waitForReloadedOptions();

  // Clear the drought: every plant above the release threshold, including Basil,
  // whose dead sensor would otherwise block confirmed recovery.
  for (const entityId of [
    "sensor.ficus_moisture",
    "sensor.orchid_moisture",
    "sensor.monstera_moisture",
    "sensor.basil_moisture",
    "sensor.cactus_moisture",
  ]) {
    await setMoisture(entityId, "95");
  }
  await waitForState(
    token,
    "sensor.watering_project_plants_needing_water",
    (value) => value === "0",
  );

  // A previous run may have left notifications enabled and a recorded push.
  await callService(token, "fake_plants", "reset_notifications", {});
  const baseline = 0;

  await setMoisture("sensor.ficus_moisture", "20");
  await waitForState(
    token,
    "sensor.fake_last_notification",
    (value) => value.endsWith("Ficus") && value.includes("1 plant needs water"),
  );

  // Second thirsty plant inside the repeat window: still one push.
  await setMoisture("sensor.orchid_moisture", "20");
  await waitForState(token, "sensor.orchid_status", (value) => value === "dry");
  await sleep(3_000);

  const after = await getState(token, "sensor.fake_notification_count");
  expect(Number(after?.state ?? "0")).toBe(baseline + 1);
  const message = await getState(token, "sensor.fake_last_notification");
  expect(message?.state).toContain("1 plant needs water");

  // Leave the instance quiet for the next run.
  await resetBaseline();
});

async function plantId(page: Page, label: string): Promise<string> {
  const id = await card(page)
    .locator(".plant", { hasText: label })
    .first()
    .getAttribute("data-plant-id");
  return id ?? "";
}
