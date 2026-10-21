import type { HassEntityState, PlantRecord, PlantStatus } from "./types";

export const UNASSIGNED_LABEL = "Unassigned";

export type SectionKey = "suspect" | "dry" | "no_data" | "healthy";

export interface SectionSpec {
  key: SectionKey;
  status: PlantStatus;
  title: string;
  /** Section can be collapsed by the user. */
  collapsible: boolean;
  /** Section starts collapsed. */
  defaultCollapsed: boolean;
  /** Section is rendered even with zero plants. */
  alwaysVisible: boolean;
}

/**
 * Section order is fixed by the spec, not by the payload order. Statuses are
 * disjoint (one plant has exactly one status), so this is a partition.
 */
export const SECTIONS: readonly SectionSpec[] = [
  {
    key: "suspect",
    status: "suspect_battery",
    title: "Suspect battery",
    collapsible: true,
    defaultCollapsed: false,
    alwaysVisible: false,
  },
  {
    key: "dry",
    status: "dry",
    title: "Too dry",
    collapsible: true,
    defaultCollapsed: false,
    alwaysVisible: true,
  },
  {
    key: "no_data",
    status: "no_data",
    title: "No data",
    collapsible: true,
    defaultCollapsed: false,
    alwaysVisible: false,
  },
  {
    key: "healthy",
    status: "healthy",
    title: "Well watered",
    collapsible: true,
    defaultCollapsed: true,
    alwaysVisible: false,
  },
] as const;

export type MoistureLookup = (plant: PlantRecord) => number | null;

/** Parse a state string to a finite number; `null` for unknown/unavailable. */
export function parseNumericState(state: HassEntityState | undefined): number | null {
  if (!state) {
    return null;
  }
  const value = Number(state.state);
  return Number.isFinite(value) ? value : null;
}

export function areaLabel(plant: PlantRecord): string {
  return plant.area_name ?? UNASSIGNED_LABEL;
}

function compareText(a: string, b: string): number {
  return a.localeCompare(b, undefined, { sensitivity: "base" });
}

/**
 * Rooms alphabetically (`Unassigned` last), then moisture ascending (`null`
 * last), then label as a stable tie-break.
 *
 * `moistureOf` is injected because displayed values come from live
 * `hass.states`, not from the payload snapshot.
 */
export function comparePlants(
  a: PlantRecord,
  b: PlantRecord,
  moistureOf: MoistureLookup,
): number {
  const areaA = areaLabel(a);
  const areaB = areaLabel(b);
  if (areaA !== areaB) {
    if (areaA === UNASSIGNED_LABEL) {
      return 1;
    }
    if (areaB === UNASSIGNED_LABEL) {
      return -1;
    }
    return compareText(areaA, areaB);
  }

  const moistureA = moistureOf(a);
  const moistureB = moistureOf(b);
  if (moistureA === null || moistureB === null) {
    if (moistureA !== moistureB) {
      return moistureA === null ? 1 : -1;
    }
  } else if (moistureA !== moistureB) {
    return moistureA - moistureB;
  }

  return compareText(a.label, b.label);
}

export function groupPlants(
  plants: readonly PlantRecord[],
  moistureOf: MoistureLookup,
): Record<SectionKey, PlantRecord[]> {
  const grouped: Record<SectionKey, PlantRecord[]> = {
    suspect: [],
    dry: [],
    no_data: [],
    healthy: [],
  };

  for (const plant of plants) {
    const spec = SECTIONS.find((candidate) => candidate.status === plant.status);
    if (spec === undefined) {
      // A status this card does not know is a schema problem, reported elsewhere;
      // dropping it is safer than inventing a section.
      continue;
    }
    grouped[spec.key].push(plant);
  }

  for (const spec of SECTIONS) {
    grouped[spec.key].sort((a, b) => comparePlants(a, b, moistureOf));
  }

  return grouped;
}

/** Group already-sorted plants into room buckets for rendering. */
export function groupByRoom(plants: readonly PlantRecord[]): Array<{
  area: string;
  plants: PlantRecord[];
}> {
  const rooms: Array<{ area: string; plants: PlantRecord[] }> = [];
  for (const plant of plants) {
    const area = areaLabel(plant);
    const last = rooms[rooms.length - 1];
    if (last !== undefined && last.area === area) {
      last.plants.push(plant);
    } else {
      rooms.push({ area, plants: [plant] });
    }
  }
  return rooms;
}

export function formatMoisture(value: number | null): string {
  if (value === null) {
    return "—";
  }
  const rounded = Math.round(value * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)} %`;
}

/** Absolute timestamp only: relative text would need a render tick. */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "unknown";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatStateValue(state: HassEntityState | undefined, fallback = "—"): string {
  if (!state) {
    return fallback;
  }
  const value = parseNumericState(state);
  if (value === null) {
    return fallback;
  }
  const unit = typeof state.attributes["unit_of_measurement"] === "string"
    ? state.attributes["unit_of_measurement"]
    : "";
  const rounded = Math.round(value * 10) / 10;
  return unit ? `${rounded} ${unit}` : String(rounded);
}

export function isEntityUnavailable(state: HassEntityState | undefined): boolean {
  return parseNumericState(state) === null;
}
