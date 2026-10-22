import { LitElement, css, html, nothing, type TemplateResult } from "lit";

import {
  SECTIONS,
  areaLabel,
  formatMoisture,
  formatStateValue,
  formatTimestamp,
  groupByRoom,
  groupPlants,
  isEntityUnavailable,
  parseNumericState,
  type SectionKey,
  type SectionSpec,
} from "./grouping";
import { PANEL_TYPE, WateringProjectPanel } from "./panel";
import {
  EXPECTED_SCHEMA,
  type CardConfig,
  type ConnectionState,
  type HassEntityState,
  type HomeAssistantLike,
  type PlantRecord,
  type WateringPayload,
} from "./types";

export const CARD_TYPE = "watering-project-card";
export const SUBSCRIBE_TYPE = "watering_project/subscribe";
const STORAGE_PREFIX = "watering-project:";

let uidCounter = 0;

function isWateringPayload(value: unknown): value is WateringPayload {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate["schema_version"] === "number" &&
    Array.isArray(candidate["plants"]) &&
    typeof candidate["summary"] === "object" &&
    candidate["summary"] !== null &&
    Array.isArray(candidate["excluded"])
  );
}

function errorCode(error: unknown): string {
  if (typeof error !== "object" || error === null) {
    return "";
  }
  const code = (error as { code?: unknown }).code;
  return typeof code === "string" ? code : "";
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "object" && error !== null) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string") {
      return message;
    }
  }
  return String(error);
}

export class WateringProjectCard extends LitElement {
  // `hass` is intentionally *not* a Lit reactive property: Lit would generate an
  // accessor on this prototype and shadow the memoising setter below, re-rendering
  // the card on every one of Home Assistant's state writes.
  static override properties = {
    _payload: { state: true },
    _connection: { state: true },
    _expanded: { state: true },
    _collapsed: { state: true },
  };

  private _config?: CardConfig;
  private _hassValue?: HomeAssistantLike;
  private _payload?: WateringPayload;
  private _connection: ConnectionState = { kind: "connecting" };
  private _expanded = new Set<string>();
  private _collapsed = new Map<SectionKey, boolean>();
  private _unsub?: () => void | Promise<void>;
  private _memo = "";
  private _payloadSeq = 0;
  private _subscribing = false;
  private _uid = `wp-${(uidCounter += 1)}`;

  setConfig(config: CardConfig): void {
    if (!config || config.type !== `custom:${CARD_TYPE}`) {
      throw new Error(`Card type must be custom:${CARD_TYPE}`);
    }
    this._config = { ...config };
    this._initCollapseState();
  }

  getCardSize(): number {
    const plants = this._payload?.plants.length ?? 0;
    return 2 + SECTIONS.length + Math.ceil(plants / 2);
  }

  getGridOptions(): Record<string, unknown> {
    return { columns: 12, min_columns: 6, min_rows: 2 };
  }

  get hass(): HomeAssistantLike | undefined {
    return this._hassValue;
  }

  set hass(value: HomeAssistantLike | undefined) {
    const previous = this._hassValue;
    this._hassValue = value;
    if (value === undefined) {
      return;
    }
    const memo = this._signature(value);
    if (previous !== undefined && memo === this._memo) {
      return;
    }
    this._memo = memo;
    this.requestUpdate();
    if (previous === undefined) {
      void this._subscribe(value);
    }
  }

  override connectedCallback(): void {
    super.connectedCallback();
    this._initCollapseState();
    if (this._hassValue !== undefined && this._unsub === undefined) {
      void this._subscribe(this._hassValue);
    }
  }

  override disconnectedCallback(): void {
    this._teardown();
    super.disconnectedCallback();
  }

  override render(): TemplateResult {
    const payload = this._payload;

    if (this._connection.kind === "not_loaded") {
      return this._frame(
        this._statusRow(
          "Watering Project is not loaded.",
          "The integration has no active config entry. Add it under Settings → Devices & services.",
          true,
        ),
      );
    }

    if (this._connection.kind === "error") {
      return this._frame(
        this._statusRow("Could not load plant status.", this._connection.message, true),
      );
    }

    if (payload === undefined) {
      return this._frame(this._statusRow("Loading plant status…", "", false));
    }

    if (payload.schema_version !== EXPECTED_SCHEMA) {
      return this._frame(
        this._statusRow(
          "Card and integration versions do not match.",
          `The card expects schema ${EXPECTED_SCHEMA} but received ${payload.schema_version}. ` +
            "Bump the `?v=` suffix of the card resource URL so the browser reloads the card.",
          false,
        ),
      );
    }

    if (payload.plants.length === 0) {
      return this._frame(html`
        <div class="status">
          <p class="status-title">No plants found.</p>
          <p class="status-detail">
            Add Zigbee moisture sensors with a moisture device class, or adjust the
            included and excluded devices in the integration options.
          </p>
        </div>
      `);
    }

    return this._frame(html`
      ${this._config?.title
        ? html`<h2 class="card-title">${this._config.title}</h2>`
        : nothing}
      ${SECTIONS.map((spec) => this._renderSection(spec, payload))}
      ${this._renderExcluded(payload)}
    `);
  }

  // -- subscription ----------------------------------------------------------

  private async _subscribe(hass: HomeAssistantLike): Promise<void> {
    if (this._subscribing) {
      return;
    }
    const connection = hass.connection;
    if (connection?.subscribeMessage === undefined) {
      this._setConnection({ kind: "error", message: "Websocket connection unavailable." });
      return;
    }

    this._subscribing = true;
    try {
      const result = await connection.subscribeMessage(
        (message: unknown) => this._handleMessage(message),
        { type: SUBSCRIBE_TYPE },
      );
      if (typeof result === "function") {
        this._unsub = result;
      }
    } catch (error: unknown) {
      const code = errorCode(error);
      const message = errorMessage(error);
      if (code === "not_loaded" || message.includes("not_loaded")) {
        this._setConnection({ kind: "not_loaded" });
      } else {
        this._setConnection({ kind: "error", message });
      }
    } finally {
      this._subscribing = false;
    }
  }

  private _handleMessage(message: unknown): void {
    if (!isWateringPayload(message)) {
      this._setConnection({
        kind: "error",
        message: "The integration sent a payload this card cannot read.",
      });
      return;
    }
    this._payload = message;
    this._payloadSeq += 1;
    this._setConnection({ kind: "ready" });
    this._refreshMemo();
    this.requestUpdate();
  }

  private _retry(): void {
    this._teardown();
    const hass = this._hassValue;
    this._setConnection({ kind: "connecting" });
    if (hass !== undefined) {
      void this._subscribe(hass);
    }
  }

  private _teardown(): void {
    const unsub = this._unsub;
    this._unsub = undefined;
    if (unsub !== undefined) {
      void unsub();
    }
  }

  private _setConnection(state: ConnectionState): void {
    this._connection = state;
    this._refreshMemo();
    this.requestUpdate();
  }

  // -- memoisation -----------------------------------------------------------

  /**
   * Cheap signature of everything the template reads from `hass`, plus the
   * payload generation. `last_reported` is deliberately absent: it moves on
   * no-op reports and would re-render the whole card for nothing.
   */
  private _signature(hass: HomeAssistantLike): string {
    const parts: string[] = [String(this._payloadSeq), this._connection.kind];
    for (const plant of this._payload?.plants ?? []) {
      parts.push(this._entitySignature(hass.states[plant.moisture_entity_id]));
      if (plant.battery_entity_id !== null) {
        parts.push(this._entitySignature(hass.states[plant.battery_entity_id]));
      }
      if (plant.temperature_entity_id !== null) {
        parts.push(this._entitySignature(hass.states[plant.temperature_entity_id]));
      }
    }
    return parts.join("|");
  }

  private _entitySignature(state: HassEntityState | undefined): string {
    if (state === undefined) {
      return "-";
    }
    const unit = state.attributes["unit_of_measurement"];
    return `${state.state}/${typeof unit === "string" ? unit : ""}`;
  }

  private _refreshMemo(): void {
    if (this._hassValue !== undefined) {
      this._memo = this._signature(this._hassValue);
    }
  }

  // -- collapse state --------------------------------------------------------

  private _storageKey(): string | undefined {
    // The sidebar panel mounts exactly one card and passes no Lovelace config, so
    // a fixed key is enough to keep the collapse state across reloads. Cards on a
    // dashboard need an explicit `id`: several instances may share a page.
    const id = this._config?.id ?? (this._config === undefined ? "panel" : undefined);
    return id === undefined || id === "" ? undefined : `${STORAGE_PREFIX}${id}:collapsed`;
  }

  private _initCollapseState(): void {
    const next = new Map<SectionKey, boolean>(
      SECTIONS.map((spec) => [spec.key, spec.defaultCollapsed]),
    );
    const key = this._storageKey();
    if (key !== undefined) {
      try {
        const raw = window.localStorage.getItem(key);
        if (raw !== null) {
          const parsed: unknown = JSON.parse(raw);
          if (typeof parsed === "object" && parsed !== null) {
            for (const [section, collapsed] of Object.entries(parsed)) {
              if (next.has(section as SectionKey)) {
                next.set(section as SectionKey, collapsed === true);
              }
            }
          }
        }
      } catch {
        // Private mode / disabled storage: collapse state is a nicety, not a need.
      }
    }
    this._collapsed = next;
  }

  private _persistCollapse(): void {
    const key = this._storageKey();
    if (key === undefined) {
      return;
    }
    try {
      window.localStorage.setItem(key, JSON.stringify(Object.fromEntries(this._collapsed)));
    } catch {
      // Ignore: see _initCollapseState.
    }
  }

  private _toggleSection(spec: SectionSpec): void {
    if (!spec.collapsible) {
      return;
    }
    this._collapsed.set(spec.key, !this._collapsed.get(spec.key));
    this._persistCollapse();
    this.requestUpdate();
  }

  private _togglePlant(plant: PlantRecord): void {
    if (this._expanded.has(plant.plant_id)) {
      this._expanded.delete(plant.plant_id);
    } else {
      this._expanded.add(plant.plant_id);
    }
    this.requestUpdate();
  }

  // -- rendering -------------------------------------------------------------

  private _frame(content: TemplateResult | typeof nothing): TemplateResult {
    return html`<ha-card><div class="content">${content}</div></ha-card>`;
  }

  private _statusRow(title: string, detail: string, retry: boolean): TemplateResult {
    return html`
      <div class="status">
        <p class="status-title">${title}</p>
        ${detail ? html`<p class="status-detail">${detail}</p>` : nothing}
        ${retry
          ? html`<button class="retry" @click=${() => this._retry()}>Retry</button>`
          : nothing}
      </div>
    `;
  }

  private _liveMoisture(plant: PlantRecord): number | null {
    const state = this._hassValue?.states[plant.moisture_entity_id];
    const live = parseNumericState(state);
    return live ?? plant.moisture;
  }

  private _renderSection(spec: SectionSpec, payload: WateringPayload): TemplateResult | typeof nothing {
    const plants = groupPlants(payload.plants, (plant) => this._liveMoisture(plant))[spec.key];
    if (plants.length === 0 && !spec.alwaysVisible) {
      return nothing;
    }

    const collapsed = this._collapsed.get(spec.key) === true;
    const panelId = `${this._uid}-${spec.key}`;

    return html`
      <section class="section section-${spec.key}" data-section=${spec.key}>
        <button
          class="section-header"
          aria-expanded=${collapsed ? "false" : "true"}
          aria-controls=${panelId}
          @click=${() => this._toggleSection(spec)}
        >
          <span class="section-title">${spec.title}</span>
          <span class="count">${plants.length}</span>
          <span class="chevron" aria-hidden="true">${collapsed ? "▸" : "▾"}</span>
        </button>
        <div class="section-body" id=${panelId} ?hidden=${collapsed}>
          ${plants.length === 0
            ? html`<p class="section-empty">No plants.</p>`
            : groupByRoom(plants).map(
                (room) => html`
                  <div class="room">
                    <h3 class="room-title">${room.area}</h3>
                    ${room.plants.map((plant) => this._renderPlant(plant))}
                  </div>
                `,
              )}
        </div>
      </section>
    `;
  }

  private _renderPlant(plant: PlantRecord): TemplateResult {
    const expanded = this._expanded.has(plant.plant_id);
    const states = this._hassValue?.states ?? {};
    const batteryState = plant.battery_entity_id === null
      ? undefined
      : states[plant.battery_entity_id];
    const temperatureState = plant.temperature_entity_id === null
      ? undefined
      : states[plant.temperature_entity_id];

    // Badges only for entities that exist but currently fail to report: a plant
    // without a battery sensor is not "unknown", it just has none.
    const temperatureUnknown =
      plant.temperature_entity_id !== null && isEntityUnavailable(temperatureState);
    const batteryUnknown =
      plant.battery_entity_id !== null &&
      (plant.battery.never_reported || isEntityUnavailable(batteryState));

    const moisture = this._liveMoisture(plant);

    return html`
      <div class="plant" data-plant-id=${plant.plant_id}>
        <button
          class="plant-row"
          aria-expanded=${expanded ? "true" : "false"}
          data-status=${plant.status}
          @click=${() => this._togglePlant(plant)}
        >
          <span class="dot" aria-hidden="true"></span>
          <span class="plant-name">${plant.label}</span>
          ${temperatureUnknown
            ? html`<span class="badge" title="Temperature unknown">temp?</span>`
            : nothing}
          ${batteryUnknown
            ? html`<span class="badge" title="Battery value unknown">batt?</span>`
            : nothing}
          <span class="moisture">${formatMoisture(moisture)}</span>
        </button>
        ${expanded
          ? html`
              <dl class="details">
                <dt>Room</dt>
                <dd>${areaLabel(plant)}</dd>
                <dt>Temperature</dt>
                <dd>${formatStateValue(temperatureState)}</dd>
                <dt>Battery</dt>
                <dd>${formatStateValue(batteryState)}</dd>
                <dt>Last reported</dt>
                <dd>
                  ${formatTimestamp(
                    states[plant.moisture_entity_id]?.last_reported ??
                      states[plant.moisture_entity_id]?.last_updated,
                  )}
                </dd>
                ${plant.zero_days !== null
                  ? html`<dt>Battery flat for</dt>
                      <dd>${plant.zero_days} ${plant.zero_days === 1 ? "day" : "days"}</dd>`
                  : nothing}
              </dl>
            `
          : nothing}
      </div>
    `;
  }

  private _renderExcluded(payload: WateringPayload): TemplateResult | typeof nothing {
    if (payload.excluded.length === 0) {
      return nothing;
    }
    return html`
      <details class="excluded">
        <summary>${payload.excluded.length} device(s) excluded</summary>
        <ul>
          ${payload.excluded.map(
            (item) => html`<li>${item.label} <span class="reason">${item.reason}</span></li>`,
          )}
        </ul>
      </details>
    `;
  }

  static override styles = css`
    :host {
      display: block;
    }

    .content {
      padding: 12px 16px 16px;
    }

    .card-title {
      margin: 4px 0 12px;
      font-size: 1.5rem;
      font-weight: 400;
      color: var(--primary-text-color);
    }

    .section + .section {
      border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
    }

    .section-header {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 10px 0;
      background: none;
      border: none;
      color: var(--primary-text-color);
      font: inherit;
      font-weight: 500;
      text-align: left;
      cursor: pointer;
    }

    .section-header:focus-visible,
    .plant-row:focus-visible,
    .retry:focus-visible {
      outline: 2px solid var(--primary-color, #03a9f4);
      outline-offset: 2px;
    }

    .count {
      padding: 1px 8px;
      border-radius: 10px;
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.08));
      color: var(--secondary-text-color);
      font-size: 0.8rem;
    }

    .chevron {
      margin-left: auto;
      color: var(--secondary-text-color);
    }

    .section-suspect .section-title {
      color: var(--warning-color, #ff9800);
    }

    .section-dry .section-title {
      color: var(--error-color, #db4437);
    }

    .room-title {
      margin: 8px 0 2px;
      font-size: 0.8rem;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--secondary-text-color);
    }

    .plant-row {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 8px 0;
      background: none;
      border: none;
      color: var(--primary-text-color);
      font: inherit;
      text-align: left;
      cursor: pointer;
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success-color, #4caf50);
      flex: none;
    }

    .plant-row[data-status="dry"] .dot {
      background: var(--error-color, #db4437);
    }

    .plant-row[data-status="suspect_battery"] .dot {
      background: var(--warning-color, #ff9800);
    }

    .plant-row[data-status="no_data"] .dot {
      background: var(--disabled-text-color, #9e9e9e);
    }

    .plant-name {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .moisture {
      font-variant-numeric: tabular-nums;
      color: var(--secondary-text-color);
    }

    .badge {
      padding: 0 6px;
      border-radius: 8px;
      border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.2));
      color: var(--secondary-text-color);
      font-size: 0.7rem;
      line-height: 1.5;
      white-space: nowrap;
    }

    .details {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 2px 16px;
      margin: 0 0 8px 16px;
      font-size: 0.85rem;
    }

    .details dt {
      color: var(--secondary-text-color);
    }

    .details dd {
      margin: 0;
    }

    .section-empty,
    .status-detail {
      margin: 4px 0 8px;
      color: var(--secondary-text-color);
      font-size: 0.9rem;
    }

    .status-title {
      margin: 8px 0 4px;
      font-weight: 500;
    }

    .retry {
      margin-top: 4px;
      padding: 6px 14px;
      border-radius: 4px;
      border: 1px solid var(--primary-color, #03a9f4);
      background: none;
      color: var(--primary-color, #03a9f4);
      font: inherit;
      cursor: pointer;
    }

    .excluded {
      margin-top: 12px;
      border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      padding-top: 8px;
      color: var(--secondary-text-color);
      font-size: 0.85rem;
    }

    .excluded summary {
      cursor: pointer;
    }

    .excluded ul {
      margin: 4px 0 0;
      padding-left: 20px;
    }

    .reason {
      opacity: 0.75;
    }

    [hidden] {
      display: none !important;
    }
  `;
}

// -- registration ------------------------------------------------------------

declare global {
  interface Window {
    customCards?: Array<Record<string, unknown>>;
  }
}

if (typeof window !== "undefined" && typeof customElements !== "undefined") {
  if (!customElements.get(CARD_TYPE)) {
    customElements.define(CARD_TYPE, WateringProjectCard);
  }
  if (!customElements.get(PANEL_TYPE)) {
    customElements.define(PANEL_TYPE, WateringProjectPanel);
  }
  window.customCards = window.customCards ?? [];
  if (!window.customCards.some((card) => card["type"] === CARD_TYPE)) {
    window.customCards.push({
      type: CARD_TYPE,
      name: "Watering Project",
      description: "Plant moisture overview grouped by room, ordered by urgency.",
      preview: false,
      documentationURL: "https://github.com/Mixermachine/WateringProject#readme",
    });
  }
}
