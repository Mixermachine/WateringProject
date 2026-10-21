/**
 * Wire format of the `watering_project/subscribe` payload.
 *
 * The Python side owns every rule; these types only describe what the card is
 * allowed to read. `EXPECTED_SCHEMA` is bumped whenever this contract breaks, so
 * a card left behind by a browser cache renders a mismatch row instead of
 * cascading `undefined`s.
 */

export const EXPECTED_SCHEMA = 1;

export type PlantStatus = "suspect_battery" | "no_data" | "dry" | "healthy";

export interface BatteryInfo {
  last_value: number | null;
  last_seen: string | null;
  never_reported: boolean;
}

export interface PlantRecord {
  plant_id: string;
  label: string;
  area_id: string | null;
  area_name: string | null;
  moisture_entity_id: string;
  battery_entity_id: string | null;
  temperature_entity_id: string | null;
  threshold: number | null;
  status: PlantStatus;
  needs_water: boolean;
  moisture: number | null;
  zero_days: number | null;
  battery: BatteryInfo;
}

export interface PayloadSummary {
  total: number;
  dry: number;
  suspect_battery: number;
  no_data: number;
  healthy: number;
  needs_water: boolean;
}

export interface ExcludedRecord {
  device_id: string;
  label: string;
  reason: string;
}

export interface PayloadConfig {
  moisture_default: number;
  battery_suspect_days: number;
  include_devices: string[];
  exclude_devices: string[];
  notify_enabled: boolean;
}

export interface WateringPayload {
  schema_version: number;
  config: PayloadConfig;
  plants: PlantRecord[];
  summary: PayloadSummary;
  excluded: ExcludedRecord[];
}

export interface CardConfig {
  type: string;
  title?: string;
  id?: string;
}

/** Subset of `hass` the card actually touches. */
export interface HassEntityState {
  state: string;
  attributes: Record<string, unknown>;
  last_reported?: string | null;
  last_updated?: string | null;
}

export interface HomeAssistantLike {
  states: Record<string, HassEntityState | undefined>;
  connection?: {
    subscribeMessage?: (
      callback: (message: unknown) => void,
      subscribeMessage: { type: string },
    ) => Promise<() => Promise<void>> | (() => Promise<void>);
  };
  localize?: (path: string, ...args: unknown[]) => string;
}

export type ConnectionState =
  | { kind: "connecting" }
  | { kind: "ready" }
  | { kind: "not_loaded" }
  | { kind: "error"; message: string };
