import { beforeEach, describe, expect, it, vi } from "vitest";

import { CARD_TYPE, WateringProjectCard } from "../src/watering-project-card";
import type {
  CardConfig,
  HassEntityState,
  HomeAssistantLike,
  PlantRecord,
  WateringPayload,
} from "../src/types";
import golden from "./fixtures/plants.golden.json";

const CARD_TAG = "watering-project-card";
const CONFIG = { type: `custom:${CARD_TYPE}` };

function cloneGolden(): WateringPayload {
  return JSON.parse(JSON.stringify(golden)) as WateringPayload;
}

function payload(plants: PlantRecord[], overrides: Partial<WateringPayload> = {}): WateringPayload {
  const summary = {
    total: plants.length,
    dry: plants.filter((item) => item.status === "dry").length,
    suspect_battery: plants.filter((item) => item.status === "suspect_battery").length,
    no_data: plants.filter((item) => item.status === "no_data").length,
    healthy: plants.filter((item) => item.status === "healthy").length,
    needs_water: plants.some((item) => item.needs_water),
  };
  return {
    schema_version: 1,
    config: {
      moisture_default: 70,
      battery_suspect_days: 30,
      include_devices: [],
      exclude_devices: [],
      notify_enabled: false,
    },
    summary,
    excluded: [],
    ...overrides,
    plants,
  };
}

function makePlant(overrides: Partial<PlantRecord> = {}): PlantRecord {
  return {
    plant_id: overrides.plant_id ?? "plant",
    label: overrides.label ?? "Plant",
    area_id: overrides.area_id ?? null,
    area_name: overrides.area_name ?? null,
    moisture_entity_id: overrides.moisture_entity_id ?? "sensor.plant_moisture",
    battery_entity_id: overrides.battery_entity_id ?? null,
    temperature_entity_id: overrides.temperature_entity_id ?? null,
    threshold: null,
    status: overrides.status ?? "dry",
    needs_water: overrides.needs_water ?? overrides.status === "dry",
    moisture: overrides.moisture ?? 40,
    zero_days: overrides.zero_days ?? null,
    battery: overrides.battery ?? { last_value: null, last_seen: null, never_reported: true },
  };
}

interface FakeConnection {
  callbacks: Array<(message: unknown) => void>;
  subscribes: number;
  unsubscribe: ReturnType<typeof vi.fn>;
}

interface FakeHass extends HomeAssistantLike {
  fake: FakeConnection;
}

function makeHass(
  states: Record<string, HassEntityState> = {},
  options: { rejectWith?: unknown } = {},
): FakeHass {
  const fake: FakeConnection = {
    callbacks: [],
    subscribes: 0,
    unsubscribe: vi.fn(async () => undefined),
  };

  const hass: FakeHass = {
    states,
    connection: {
      subscribeMessage: (callback) => {
        fake.subscribes += 1;
        if (options.rejectWith !== undefined) {
          return Promise.reject(options.rejectWith);
        }
        fake.callbacks.push(callback);
        return Promise.resolve(fake.unsubscribe);
      },
    },
    fake,
  };
  return hass;
}

function push(hass: FakeHass, message: unknown): void {
  const callback = hass.fake.callbacks[hass.fake.callbacks.length - 1];
  if (callback === undefined) {
    throw new Error("card did not subscribe");
  }
  callback(message);
}

async function mount(
  payloadOrHass: WateringPayload | FakeHass,
  states: Record<string, HassEntityState> = {},
  config: CardConfig = CONFIG,
): Promise<{ card: WateringProjectCard; hass: FakeHass; element: HTMLElement }> {
  const hass = "fake" in payloadOrHass ? payloadOrHass : makeHass(states);
  const card = document.createElement(CARD_TAG) as WateringProjectCard;
  card.setConfig(config);
  document.body.appendChild(card);
  card.hass = hass;
  await card.updateComplete;

  if (!("fake" in payloadOrHass)) {
    push(hass, payloadOrHass);
    await card.updateComplete;
  }

  return { card, hass, element: card };
}

function query<T extends Element = HTMLElement>(root: HTMLElement, selector: string): T | null {
  return root.shadowRoot?.querySelector<T>(selector) ?? null;
}

function queryAll<T extends Element = HTMLElement>(root: HTMLElement, selector: string): T[] {
  return Array.from(root.shadowRoot?.querySelectorAll<T>(selector) ?? []);
}

function textOf(root: HTMLElement, selector: string): string {
  return query(root, selector)?.textContent?.trim() ?? "";
}

beforeEach(() => {
  window.localStorage.clear();
  document.body.innerHTML = "";
});

describe("card registration", () => {
  it("registers itself in the card picker", () => {
    const entry = window.customCards?.find((card) => card["type"] === CARD_TYPE);
    expect(entry).toBeDefined();
    expect(entry?.["name"]).toBe("Watering Project");
  });

  it("rejects a foreign card type", () => {
    const card = document.createElement(CARD_TAG) as WateringProjectCard;
    expect(() => card.setConfig({ type: "custom:other" })).toThrow(/watering-project-card/);
  });
});

describe("render", () => {
  it("renders four sections with the golden fixture", async () => {
    const { element } = await mount(cloneGolden());

    const sections = queryAll(element, "[data-section]").map((node) =>
      node.getAttribute("data-section"),
    );
    expect(sections).toEqual(["suspect", "dry", "no_data", "healthy"]);

    expect(query(element, ".section-suspect .count")?.textContent).toBe("1");
    expect(query(element, ".section-dry .count")?.textContent).toBe("2");
    expect(query(element, ".section-no_data .count")?.textContent).toBe("1");
    expect(query(element, ".section-healthy .count")?.textContent).toBe("1");
  });

  it("hides the suspect section when empty and keeps the dry section", async () => {
    const plants = [makePlant({ plant_id: "a", label: "A", status: "healthy" })];
    const { element } = await mount(payload(plants));

    expect(query(element, ".section-suspect")).toBeNull();
    expect(query(element, ".section-dry")).not.toBeNull();
    expect(textOf(element, ".section-dry .section-empty")).toBe("No plants.");
  });

  it("collapses the healthy section by default", async () => {
    const { element } = await mount(cloneGolden());

    const body = query(element, ".section-healthy .section-body");
    expect(body?.hasAttribute("hidden")).toBe(true);
    expect(
      query(element, ".section-healthy .section-header")?.getAttribute("aria-expanded"),
    ).toBe("false");
  });

  it("orders rooms alphabetically with Unassigned last", async () => {
    const plants = [
      makePlant({ plant_id: "u", label: "Unassigned plant", area_name: null, moisture: 10 }),
      makePlant({ plant_id: "k", label: "Kitchen plant", area_name: "Kitchen", moisture: 50 }),
      makePlant({ plant_id: "b", label: "Bedroom plant", area_name: "Bedroom", moisture: 20 }),
      makePlant({ plant_id: "k2", label: "Kitchen low", area_name: "Kitchen", moisture: 30 }),
    ];
    const { element } = await mount(payload(plants));

    const rooms = queryAll(element, ".section-dry .room-title").map((node) => node.textContent);
    expect(rooms).toEqual(["Bedroom", "Kitchen", "Unassigned"]);

    const kitchenRows = queryAll(element, ".section-dry .room").map((room) =>
      Array.from(room.querySelectorAll(".plant-name")).map((node) => node.textContent),
    );
    expect(kitchenRows[1]).toEqual(["Kitchen low", "Kitchen plant"]);
  });

  it("uses live hass states for the displayed moisture", async () => {
    const plant = makePlant({ plant_id: "a", label: "A", moisture: 40 });
    const hass = makeHass({
      "sensor.plant_moisture": { state: "64", attributes: { unit_of_measurement: "%" } },
    });
    const { element, card } = await mount(hass);
    push(hass, payload([plant]));
    await card.updateComplete;

    expect(textOf(element, ".moisture")).toBe("64 %");
  });

  it("badges a battery that never reported and an unavailable temperature", async () => {
    const plant = makePlant({
      plant_id: "a",
      label: "A",
      battery_entity_id: "sensor.a_battery",
      temperature_entity_id: "sensor.a_temperature",
      battery: { last_value: null, last_seen: null, never_reported: true },
    });
    const hass = makeHass({
      "sensor.plant_moisture": { state: "40", attributes: {} },
      "sensor.a_battery": { state: "unavailable", attributes: {} },
      "sensor.a_temperature": { state: "unknown", attributes: {} },
    });
    const { element, card } = await mount(hass);
    push(hass, payload([plant]));
    await card.updateComplete;

    const badges = queryAll(element, ".badge").map((node) => node.textContent);
    expect(badges).toEqual(["temp?", "batt?"]);
  });

  it("does not badge a missing battery sensor", async () => {
    const plant = makePlant({ plant_id: "a", label: "A", battery_entity_id: null });
    const { element } = await mount(payload([plant]));

    expect(queryAll(element, ".badge")).toEqual([]);
  });

  it("expands a row into details with an absolute timestamp", async () => {
    const plant = makePlant({
      plant_id: "a",
      label: "A",
      area_name: "Kitchen",
      moisture: 40,
      battery_entity_id: "sensor.a_battery",
      temperature_entity_id: "sensor.a_temperature",
    });
    const hass = makeHass({
      "sensor.plant_moisture": {
        state: "40",
        attributes: {},
        last_reported: "2026-01-15T10:00:00+00:00",
        last_updated: "2026-01-14T09:00:00+00:00",
      },
      "sensor.a_battery": { state: "80", attributes: { unit_of_measurement: "%" } },
      "sensor.a_temperature": { state: "21.5", attributes: { unit_of_measurement: "°C" } },
    });
    const { element, card } = await mount(hass);
    push(hass, payload([plant]));
    await card.updateComplete;

    expect(query(element, ".details")).toBeNull();
    query<HTMLButtonElement>(element, ".plant-row")?.click();
    await card.updateComplete;

    const details = query(element, ".details");
    expect(details).not.toBeNull();
    expect(details?.textContent).toContain("80 %");
    expect(details?.textContent).toContain("21.5 °C");
    expect(details?.textContent).toContain("2026");
    expect(
      query(element, ".plant-row")?.getAttribute("aria-expanded"),
    ).toBe("true");
  });

  it("shows the flat-battery age for a suspect plant", async () => {
    const { element } = await mount(cloneGolden());

    const suspectRow = query(element, ".section-suspect .plant-row") as HTMLButtonElement;
    suspectRow.click();
    await (element as WateringProjectCard).updateComplete;

    const details = query(element, ".section-suspect .details");
    expect(details?.textContent).toContain("Battery flat for");
    expect(details?.textContent).toContain("31 days");
  });

  it("renders the excluded footer collapsed", async () => {
    const { element } = await mount(cloneGolden());

    const footer = query<HTMLDetailsElement>(element, "details.excluded");
    expect(footer).not.toBeNull();
    expect(footer?.open).toBe(false);
    expect(footer?.textContent).toContain("2 device(s) excluded");
    expect(footer?.textContent).toContain("keyword:leak");
  });

  it("renders an empty state without sections", async () => {
    const { element } = await mount(payload([]));

    expect(query(element, "[data-section]")).toBeNull();
    expect(textOf(element, ".status-title")).toBe("No plants found.");
  });
});

describe("collapse persistence", () => {
  it("round-trips through localStorage when an id is set", async () => {
    const { element } = await mount(cloneGolden(), {}, { ...CONFIG, id: "plants-main" });

    const header = query<HTMLButtonElement>(element, ".section-dry .section-header");
    header?.click();
    await (element as WateringProjectCard).updateComplete;

    const stored = window.localStorage.getItem("watering-project:plants-main:collapsed");
    expect(stored).toContain('"dry":true');

    document.body.innerHTML = "";
    const second = await mount(cloneGolden(), {}, { ...CONFIG, id: "plants-main" });
    expect(
      query(second.element, ".section-dry .section-body")?.hasAttribute("hidden"),
    ).toBe(true);
  });

  it("does not persist without an id", async () => {
    const { element } = await mount(cloneGolden());

    query<HTMLButtonElement>(element, ".section-dry .section-header")?.click();
    await (element as WateringProjectCard).updateComplete;

    expect(window.localStorage.length).toBe(0);
  });

  it("survives unreadable storage", async () => {
    window.localStorage.setItem("watering-project:bad:collapsed", "{not json");
    const { element } = await mount(cloneGolden(), {}, { ...CONFIG, id: "bad" });

    expect(query(element, ".section-suspect")).not.toBeNull();
  });
});

describe("connection states", () => {
  it("shows a loading row until the first payload arrives", async () => {
    const card = document.createElement(CARD_TAG) as WateringProjectCard;
    card.setConfig(CONFIG);
    document.body.appendChild(card);
    card.hass = makeHass();
    await card.updateComplete;

    expect(textOf(card, ".status-title")).toBe("Loading plant status…");
  });

  it("shows not_loaded with a working retry", async () => {
    const hass = makeHass(
      {},
      { rejectWith: Object.assign(new Error("not_loaded"), { code: "not_loaded" }) },
    );
    const { element, card } = await mount(hass, {});
    await card.updateComplete;

    expect(textOf(element, ".status-title")).toBe("Watering Project is not loaded.");
    expect(query(element, ".retry")).not.toBeNull();

    const before = hass.fake.subscribes;
    query<HTMLButtonElement>(element, ".retry")?.click();
    await Promise.resolve();
    expect(hass.fake.subscribes).toBe(before + 1);
  });

  it("reports a schema mismatch instead of rendering undefined", async () => {
    const mismatched = { ...cloneGolden(), schema_version: 99 };
    const { element } = await mount(mismatched as WateringPayload);

    expect(textOf(element, ".status-title")).toMatch(/versions do not match/);
    expect(textOf(element, ".status-detail")).toContain("99");
    expect(query(element, "[data-section]")).toBeNull();
  });

  it("reports a missing websocket connection", async () => {
    const card = document.createElement(CARD_TAG) as WateringProjectCard;
    card.setConfig(CONFIG);
    document.body.appendChild(card);
    card.hass = { states: {} };
    await card.updateComplete;

    expect(textOf(card, ".status-title")).toBe("Could not load plant status.");
  });

  it("rejects a payload it cannot read", async () => {
    const hass = makeHass();
    const { card } = await mount(hass, {});
    push(hass, { nope: true });
    await card.updateComplete;

    expect(textOf(card, ".status-title")).toBe("Could not load plant status.");
  });
});

describe("update budget", () => {
  it("renders zero times for 1000 unrelated state updates", async () => {
    const { card, hass } = await mount(cloneGolden());

    let renders = 0;
    const original = card.requestUpdate.bind(card);
    card.requestUpdate = ((...args: Parameters<typeof original>) => {
      renders += 1;
      return original(...args);
    }) as typeof card.requestUpdate;

    for (let index = 0; index < 1000; index += 1) {
      card.hass = {
        ...hass,
        states: {
          ...hass.states,
          "sensor.unrelated": { state: String(index), attributes: {} },
        },
      };
    }

    expect(renders).toBe(0);
  });

  it("re-renders when a tracked entity changes", async () => {
    const { card, hass } = await mount(cloneGolden());

    let renders = 0;
    const original = card.requestUpdate.bind(card);
    card.requestUpdate = ((...args: Parameters<typeof original>) => {
      renders += 1;
      return original(...args);
    }) as typeof card.requestUpdate;

    card.hass = {
      ...hass,
      states: {
        "sensor.ficus_moisture": { state: "41", attributes: {} },
      },
    };

    expect(renders).toBe(1);
  });

  it("renders 200 plants under budget and hits the memo", async () => {
    const plants = Array.from({ length: 200 }, (_, index) =>
      makePlant({
        plant_id: `plant-${index}`,
        label: `Plant ${index}`,
        moisture_entity_id: `sensor.plant_${index}`,
        area_name: `Room ${index % 10}`,
        moisture: index % 100,
        status: index % 3 === 0 ? "healthy" : "dry",
      }),
    );

    const started = performance.now();
    const { card, hass } = await mount(payload(plants));
    const initial = performance.now() - started;
    expect(initial).toBeLessThan(300);

    const memoStart = performance.now();
    for (let index = 0; index < 200; index += 1) {
      card.hass = { ...hass, states: { ...hass.states } };
    }
    const perUpdate = (performance.now() - memoStart) / 200;
    expect(perUpdate).toBeLessThan(0.1);
  });
});
