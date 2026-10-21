import { describe, expect, it } from "vitest";

import {
  UNASSIGNED_LABEL,
  areaLabel,
  comparePlants,
  formatMoisture,
  formatStateValue,
  formatTimestamp,
  groupByRoom,
  groupPlants,
  parseNumericState,
  type SectionKey,
} from "../src/grouping";
import type { PlantRecord, PlantStatus } from "../src/types";

function plant(overrides: Partial<PlantRecord> = {}): PlantRecord {
  return {
    plant_id: overrides.plant_id ?? "plant",
    label: overrides.label ?? "Plant",
    area_id: overrides.area_id ?? null,
    area_name: overrides.area_name ?? null,
    moisture_entity_id: overrides.moisture_entity_id ?? "sensor.moisture",
    battery_entity_id: overrides.battery_entity_id ?? null,
    temperature_entity_id: overrides.temperature_entity_id ?? null,
    threshold: null,
    status: overrides.status ?? "dry",
    needs_water: overrides.needs_water ?? false,
    moisture: overrides.moisture ?? null,
    zero_days: overrides.zero_days ?? null,
    battery: overrides.battery ?? { last_value: null, last_seen: null, never_reported: true },
  };
}

function withStatus(status: PlantStatus, label: string, area: string | null = null): PlantRecord {
  return plant({ plant_id: label.toLowerCase(), label, area_name: area, status });
}

const payloadMoisture = (record: PlantRecord): number | null => record.moisture;

describe("comparePlants", () => {
  it("sorts rooms alphabetically and unassigned last", () => {
    const plants = [
      withStatus("dry", "Zed"),
      withStatus("dry", "Basil", "Bedroom"),
      withStatus("dry", "Ficus", "Kitchen"),
      withStatus("dry", "Aaa", "Attic"),
    ];

    const sorted = [...plants].sort((a, b) => comparePlants(a, b, payloadMoisture));

    expect(sorted.map((item) => areaLabel(item))).toEqual([
      "Attic",
      "Bedroom",
      "Kitchen",
      UNASSIGNED_LABEL,
    ]);
  });

  it("sorts by moisture ascending with null last", () => {
    const plants = [
      plant({ plant_id: "null", label: "Null", moisture: null }),
      plant({ plant_id: "high", label: "High", moisture: 80 }),
      plant({ plant_id: "low", label: "Low", moisture: 12 }),
    ];

    const sorted = [...plants].sort((a, b) => comparePlants(a, b, payloadMoisture));

    expect(sorted.map((item) => item.plant_id)).toEqual(["low", "high", "null"]);
  });

  it("falls back to the label for equal rooms and moisture", () => {
    const plants = [
      plant({ plant_id: "b", label: "B", moisture: 40 }),
      plant({ plant_id: "a", label: "A", moisture: 40 }),
    ];

    const sorted = [...plants].sort((a, b) => comparePlants(a, b, payloadMoisture));

    expect(sorted.map((item) => item.plant_id)).toEqual(["a", "b"]);
  });

  it("uses the injected live moisture, not the payload snapshot", () => {
    const a = plant({ plant_id: "a", label: "A", moisture: 10 });
    const b = plant({ plant_id: "b", label: "B", moisture: 90 });

    const live: Record<string, number> = { a: 55, b: 20 };
    const sorted = [a, b].sort((x, y) => comparePlants(x, y, (item) => live[item.plant_id] ?? null));

    expect(sorted.map((item) => item.plant_id)).toEqual(["b", "a"]);
  });
});

describe("groupPlants", () => {
  it("partitions by status and keeps the section order stable", () => {
    const plants = [
      withStatus("healthy", "H1"),
      withStatus("dry", "D2", "Kitchen"),
      withStatus("no_data", "N1"),
      withStatus("suspect_battery", "S1"),
      withStatus("dry", "D1", "Attic"),
      withStatus("healthy", "H2"),
    ];

    const grouped = groupPlants(plants, payloadMoisture);
    const counts = Object.fromEntries(
      Object.entries(grouped).map(([key, value]) => [key, value.length]),
    ) as Record<SectionKey, number>;

    expect(counts).toEqual({ suspect: 1, dry: 2, no_data: 1, healthy: 2 });
    expect(grouped.dry.map((item) => item.label)).toEqual(["D1", "D2"]);
  });

  it("does not count a plant twice", () => {
    const plants = [withStatus("dry", "A"), withStatus("dry", "B")];

    const grouped = groupPlants(plants, payloadMoisture);
    const total = Object.values(grouped).reduce((sum, list) => sum + list.length, 0);

    expect(total).toBe(plants.length);
  });
});

describe("groupByRoom", () => {
  it("buckets consecutive plants of the same room", () => {
    const plants = [
      plant({ plant_id: "1", label: "A", area_name: "Kitchen" }),
      plant({ plant_id: "2", label: "B", area_name: "Kitchen" }),
      plant({ plant_id: "3", label: "C", area_name: "Attic" }),
    ];

    const rooms = groupByRoom(plants);

    expect(rooms.map((room) => [room.area, room.plants.length])).toEqual([
      ["Kitchen", 2],
      ["Attic", 1],
    ]);
  });
});

describe("formatting", () => {
  it("rounds moisture and handles null", () => {
    expect(formatMoisture(null)).toBe("—");
    expect(formatMoisture(42)).toBe("42 %");
    expect(formatMoisture(42.25)).toBe("42.3 %");
  });

  it("renders an absolute timestamp, never a relative one", () => {
    const text = formatTimestamp("2026-01-15T10:00:00+00:00");
    expect(text).not.toMatch(/ago/);
    expect(text).toMatch(/2026/);
  });

  it("returns unknown for unparsable timestamps", () => {
    expect(formatTimestamp("not a date")).toBe("unknown");
    expect(formatTimestamp(null)).toBe("unknown");
  });

  it("formats live entity values with their unit", () => {
    expect(formatStateValue({ state: "21.5", attributes: { unit_of_measurement: "°C" } })).toBe(
      "21.5 °C",
    );
    expect(formatStateValue({ state: "80", attributes: { unit_of_measurement: "%" } })).toBe(
      "80 %",
    );
    expect(formatStateValue(undefined)).toBe("—");
    expect(formatStateValue({ state: "unavailable", attributes: {} })).toBe("—");
  });

  it("treats unknown and unavailable as no value", () => {
    expect(parseNumericState(undefined)).toBeNull();
    expect(parseNumericState({ state: "unavailable", attributes: {} })).toBeNull();
    expect(parseNumericState({ state: "0", attributes: {} })).toBe(0);
  });
});
