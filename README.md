# Watering Project

Home Assistant custom integration plus Lovelace card for plant moisture monitoring.

Auto-discovers plant moisture sensors, groups them by room, shows them in four
urgency-ordered sections, exposes per-plant status entities for automations, and can notify
a phone when plants need water.

Motivation: existing moisture visualisations are either too generic or too noisy, because
rechargeable-battery Zigbee sensors report `0%` battery for weeks before the reading is
actually meaningful. Plant status must not be polluted by those false alarms.

---

## Goals

- Zero-per-sensor-config discovery of plant moisture sensors.
- Room-grouped, urgency-ordered view.
- Battery quirks of rechargeable cells handled **reliably across HA restarts**.
- Plant status available **to Home Assistant itself** (entities, events), so notifications
  and automations are possible.
- Everything testable without real Zigbee hardware and without a phone.

## Non-goals (v1)

- Irrigation control (valves, pumps).
- Historical charts/sparklines inside the card.
- Overwatering thresholds.
- Per-plant threshold overrides in the UI (field reserved; the classification API accepts it).
- Backfilling battery history from before installation.
- Multiple notification targets, per-plant notification rules, quiet hours.
- Multiple config entries (single instance in v1).
- Auto-registering the Lovelace resource (see Registration).
- Publishing to HACS, auto-update, update notifications (scaffolding is kept, see Deployment).
- Blueprints (built-in notifier covers v1).

---

## Architecture

| Part | Tech | Owns |
| --- | --- | --- |
| `custom_components/watering_project/` | Python, HA **2026.10+** | **Everything that decides**: discovery, battery observation, classification, entities, notifications, config |
| `frontend/` | TypeScript + Lit, Vite build | **Everything that shows**: sections, ordering, badges, collapse, layout |

The verdict is computed **only** on the server, where it becomes first-class HA state
(`binary_sensor.*_needs_water`, `sensor.*_status`). That is what makes notifications,
automations, history and voice possible. The card contains **no rule logic**; it groups,
sorts and renders. Duplicated rules would create two verdicts that drift — the one thing
this design refuses.

### Evaluation pipeline

`evaluate.py::async_evaluate()` — the single entry point, with **single-flight coalescing**:

1. `discovery.discover(hass, options)` → plant records + excluded records.
2. Read live values from `hass.states` for tracked entity ids.
3. Read battery facts and previous verdicts from Stores.
4. `classification.classify(plants, values, battery_facts, previous_statuses, config, now)`
   → verdicts. **Pure function, injected `now`.**
5. Push verdicts into entities; remove entities for plants that stopped qualifying.
6. Notification decision.
7. Persist verdicts + notification state, then push the new payload to subscribers if the
   hashed field set changed.

**Single-flight**: a module-level `asyncio.Task`; if a run is in progress, set `dirty = True`
and re-run exactly once after it completes. Payload push happens inside the guarded section,
so two triggers 50 ms apart produce one notification and one event. Without this, the timer
and a debounced state change can both see `last_notified is None` and double-push.

**Triggers**: state change of a tracked entity (debounced 1 s), registry updates (debounced
1 s), a 60 s interval timer, options save, and `async_setup_entry` completion. All call the
same function, so tests call `async_evaluate()` directly and only one test per trigger wiring
simulates the trigger.

**Timer guard**: the 60 s tick skips the full discovery walk when no plant has a `zero_since`
and no plant sits inside the hysteresis band `[threshold, threshold + dry_hysteresis)` —
nothing time-based can change in that state.

**Failure isolation**: an exception inside evaluation is logged, sets every per-plant status
to `no_data` (so failure is loud, not frozen at a stale verdict), and does not kill the timer
or listeners. Store write failures are logged and retried on the next run; a failed save does
not abort entity updates.

### Teardown

`async_unload_entry` must: cancel the interval timer, shut down both debouncers, unsubscribe
the state and registry listeners, await pending single-flight work, and flush all Stores —
all registered via `entry.async_on_unload` so an options-triggered reload cannot leave
duplicate triggers behind. Because discovery can add plants later, the state-change
subscription is **re-created whenever the plant set changes**; otherwise a newly added plant
reacts only to the 60 s timer.

### Config transport

A **subscription** command, not request/response:

```
{ "type": "watering_project/subscribe" }
```

The server sends `send_result(id)`, then immediately pushes the full payload as an **event**,
and pushes a full payload again whenever the hashed field set changes. Every push is a
complete payload — no diffs. Three reasons:

- `connection.subscribeMessage` auto-resubscribes after reconnect but **discards the fresh
  `result`** (it resolves an internal promise nobody holds). Sending state as the initial
  *event* makes reconnects self-healing instead of waiting for the next change.
- Custom websocket commands, unlike `subscribe_events`, are not admin-gated, so household
  members get live updates. `subscribe_events` would have rejected a custom event type for
  non-admins via `SUBSCRIBE_ALLOWLIST`.
- Full payloads remove the need for a client-side `revision` watermark (the earlier design
  used an in-memory counter that reset on restart and silently dropped every response).

Server-side subscriber bookkeeping: unsubscribe callable stored in
`connection.subscriptions[msg["id"]]`; every push checks the connection is still live;
`async_handle_close` unsubscribes automatically. Per-connection permission filtering is
re-applied on every push, not only at subscribe time.

Payload:

```ts
{
  schema_version: 1,
  config: {
    moisture_default: 70,
    battery_suspect_days: 30,
    include_devices: [],
    exclude_devices: [],
    notify_enabled: false
  },
  plants: [{
    plant_id: "<device_id>",          // fallback: moisture_entity_id
    label: "Ficus",
    area_id: "kitchen" | null,
    area_name: "Kitchen" | null,
    moisture_entity_id: "sensor.ficus_moisture",
    battery_entity_id: "sensor.ficus_battery" | null,
    temperature_entity_id: "sensor.ficus_temperature" | null,
    threshold: null,                  // reserved for per-plant override
    status: "suspect_battery" | "no_data" | "dry" | "healthy",
    needs_water: true,
    moisture: 42.0 | null,
    zero_days: 31 | null,             // integer days, display only
    battery: {
      last_value: 0 | null,
      last_seen: "2025-01-01T09:00:00+00:00" | null,
      never_reported: false
    }
  }],
  summary: {
    total: 12, dry: 3, suspect_battery: 1, no_data: 0, healthy: 8, needs_water: true
  },
  excluded: [{ device_id: "...", label: "Basement leak", reason: "keyword:leak" }]
}
```

- `summary.total == plants.length == sum(statuses)`; `excluded[]` is never counted.
- `summary` is **per-connection** (after permission filtering), while the aggregate sensor is
  global — that difference is intentional and documented.
- `schema_version` is mandatory: HACS version skew (cache-busted URL, cached companion-app JS)
  makes "new integration + old card" routine. The card declares `EXPECTED_SCHEMA` and renders
  a mismatch row instead of cascading `undefined`s.
- No `server_now`: the server decides, so no client clock enters the verdict.

**Hashed field set** (payload pushed only when this changes):
`plant_id, label, area_id, status, needs_water, threshold, battery.never_reported, summary,
excluded, config, schema_version, int(zero_days)`.
Explicitly **not hashed**: `moisture` (changes on every Zigbee report), `battery.last_seen`,
`battery.last_value`, and the fractional part of `zero_days`. `int(zero_days)` gives at most
one push per day per suspect plant. `moisture` is excluded from the internal verdict-change
key as well: the card reads the live value from `hass.states`, so counting it would turn every
Zigbee report into a push.

The card subscribes on mount and renders the latest payload; events arrive in order on a
single connection, so no watermark is needed. `not_loaded` → error row with retry; no
degraded fallback list, because without the payload there are no plants.

---

## Discovery (Python)

`discovery.py::discover(hass, options) -> DiscoveryResult`, transport agnostic, testable
against real registries.

Join: registry entities → device → area.

- **Moisture entity**: domain `sensor`, enabled, `device_class == "moisture"` (from state
  attributes — bulk registry payloads carry no `device_class`), unit `%`.
- **Battery**: same device, **enabled**, `device_class == "battery"`, unit `%`.
- **Temperature**: same device, **enabled**, `device_class == "temperature"`, any unit.
- **Area**: `entity.area_id` → else `device.area_id` → else `null` (`Unassigned`).
- **Label**: device name, else entity friendly name. A device with `name is None` falls back
  to the friendly name so entity ids never become `binary_sensor.none_needs_water`.
- **`plant_id`**: `device_id`, fallback `moisture_entity_id`. Never a label.
- Devices without a qualifying moisture entity are ignored.
- Multiple qualifying moisture entities on one device: lowest `entity_id`, logged once at
  debug.

**No platform filter.** Zigbee is the intended source, but `device_class` matching keeps
MQTT bridges usable and makes fake hardware possible.

**Inclusion precedence**, single implementation, applied on **every** pass, high to low:

1. `exclude_devices` — always wins.
2. explicit `include_devices` entry — overrides keyword auto-exclusion, so users can adopt a
   device whose name merely looks like a leak sensor.
3. keyword auto-exclude on device name/model (leak/flood/aquarium, list in `const.py`, exactly
   one copy).
4. default: include.

Non-matching devices when `include_devices` is non-empty are reported with
`reason: "not_included"`; excluded ones with `reason: "option"` or `reason: "keyword:<kw>"`.

**Per-connection permission filter (mandatory).** `hass.states` is filtered per user for
non-admins, registry responses are not. Records whose moisture entity fails
`connection.user.permissions.check_entity(entity_id, POLICY_READ)` are dropped and reported
as `reason: "permission"`.

**Known limitation (design-invariant):** an entity with no state object carries no
`device_class`, so it cannot be discovered. Invisible, not "no_data".

---

## Battery observation tracker (Python)

`battery.py`, part of the integration's persistent store document (see Persistence), debounced
writes (≥5 s), no write when nothing changed.

Why not `last_changed`: `StateMachine.async_set_internal` sets
`last_changed = old_state.last_changed if same_state else None`, and `hass.states` is rebuilt
empty on start, so `now - last_changed` measures "time since last HA restart" and resets on
every `0 → 100 → 0` charging blip or `"0"` vs `"0.0"` change. Exactly the sensors this
project exists for.

- Observed set is **device-based and independent of discovery**: every enabled battery entity
  (`device_class == "battery"`) on a non-excluded device, plus persisted records. Discovery
  consumes the tracker; the tracker never consumes discovery — otherwise a moisture entity
  blinking out would drop the plant and silently restart the clock.
- Per-entity record: `zero_since`, `last_value`, `last_seen`.
- Rules per state change:
  - finite and `<= 1` → set `zero_since = now` if unset; update `last_value`/`last_seen`.
  - finite and `> 1` → clear `zero_since`.
  - out of range (`<0`, `>100`) or non-numeric → unknown: keep `zero_since`, record the value
    only if it is numeric. **Only a numeric reading advances `last_seen`** — otherwise an
    entity that has been `unavailable` for a year would never be pruned.
  - `never_reported` stays true until the first numeric value — reported truthfully instead
    of conflated with "no such entity".
- Persisted `zero_since` loads **before** the first evaluation, so `0%` keeps accumulating
  across restarts.
- Records with `last_seen` older than 90 days are pruned.

---

## Persistence

One Store document per config entry: `.storage/watering_project.<entry_id>`, versioned, with
three sections and one debounced writer:

- `battery`: per-entity `zero_since` / `last_value` / `last_seen`.
- `verdicts`: `plant_id` → last status, so hysteresis survives a restart.
- `notify`: `last_notified`, persisted **before** dispatch (write-ahead) and saved
  immediately, bypassing the debounce.

---

## Classification (pure Python)

```python
classify(plants, values, battery_facts, previous_statuses, config, now) -> list[Verdict]
```

Pure: no `hass`, no registry, no I/O, injected `now`. First match wins:

1. **`suspect_battery`** — battery fact exists and
   `now - zero_since >= battery_suspect_days`.
2. **`no_data`** — moisture value is `unavailable`/`unknown`, missing, or not finite.
   (Enum value deliberately not named `unavailable`: an available sensor holding the literal
   state `"unavailable"` is indistinguishable from a dead entity.)
3. **`dry`** — moisture `< threshold`, where `threshold = plant.threshold ??
   config.moisture_default`. **Hysteresis:** a plant whose previous status was `dry` stays
   `dry` until moisture `>= threshold + dry_hysteresis` (5, fixed in `const.py`).
4. **`healthy`** — everything else, including overwatered plants.

`previous_statuses` come from the `verdicts` store section, seeded before the first
evaluation. First boot after install has none, so hysteresis is inactive for exactly one
evaluation — stated, tested.

**Hysteresis across `no_data`**: the hysteresis comparison uses the **last non-`no_data`
status**, so a plant that was dry does not become `healthy` merely because it blinked offline
and returned inside the band.

**Suspect wins over dry — accepted consequence.** A plant with a stuck `0%` battery is
classified `suspect_battery` even when its soil is bone dry, so it is **never notified as
thirsty**. This is deliberate: the battery reading is untrustworthy, and the sensor may be
dead. It is mitigated, not hidden: suspect plants raise a **repair issue** (`battery_suspect`)
listing plant names, appear in section 1 of the card, and are reported in
`summary.suspect_battery`. Documented in Known limitations.

`Verdict` carries `status`, `needs_water` (`status == "dry"`), `moisture`, `zero_days`,
battery display facts.

Numeric coercion is explicit: accept number or numeric string, reject `null`, `""`, `"-"`,
`NaN`, `Infinity`.

---

## Entities (Python)

Attached to the **existing source device** when one exists (`DeviceInfo(identifiers=...)` from
the device registry); the integration's config entry is added to that device's
`config_entries`, which is a real co-ownership side effect, tested.

| Entity | Type | Meaning |
| --- | --- | --- |
| `binary_sensor.<plant>_needs_water` | binary_sensor, `on` = needs water | Automation trigger. Icon `mdi:water-alert`. No `device_class` (HA's `moisture` class means leak-detected). `available = False` when status is `no_data` |
| `sensor.<plant>_status` | sensor, `device_class: enum`, `entity_category: diagnostic` | `suspect_battery` / `no_data` / `dry` / `healthy` |
| `sensor.plants_needing_water` | sensor, count | Aggregate |
| `binary_sensor.plants_need_water` | binary_sensor | Aggregate `on/off` trigger |

Naming and identity:
- With a device: `has_entity_name = True` + `translation_key`, so the **friendly name**
  follows device renames. **Entity ids do not** — `suggested_object_id` is computed once at
  creation (there is no entity_id migration on device rename). Automations bind to the id
  created on first setup; this trade-off is documented instead of promised away.
- Without a device (MQTT/template sensor): `device_info = None` and
  `has_entity_name = False` with an explicit name, otherwise every device-less plant collides
  on the same `suggested_object_id`.
- `unique_id = f"{DOMAIN}_{entry_id}_{plant_id}_{kind}"`.
- Aggregates get their own virtual service device
  `DeviceInfo(identifiers={(DOMAIN, entry_id)}, entry_type=DeviceEntryType.SERVICE)`. Because
  `has_entity_name = True` and the device is named *Watering Project*, their entity ids are
  prefixed: `sensor.watering_project_plants_needing_water`,
  `binary_sensor.watering_project_plants_need_water`. Per-plant entities use the source
  device name instead (`binary_sensor.ficus_needs_water`, `sensor.ficus_status`) — these are
  the ids automations should reference.
- v1 is single-instance (`async_abort` on a second entry), and every `unique_id` and the
  store filename are still keyed by `entry_id`.

Lifecycle:
- A plant that stops qualifying: `entity_registry.async_remove(entity_id)` and drop the
  object. Never call `async_write_ha_state()` on a removed entity
  (`_async_verify_state_writable` raises). The live entity's registry-updated hook then
  removes its state; the cleanup is a scheduled task, so a same-tick disappear/reappear is
  possible and covered by a test.
- User customisations (custom name, icon, `disabled_by`) are lost on disappear/reappear —
  accepted, documented.
- Skipped `async_write_ha_state()` when the verdict is unchanged, so `last_reported` stays
  honest.
- No `restore_state` for statuses: recomputed on setup and every evaluation.

---

## Notifications (Python)

State in the `notify` store section. Options: `notify_enabled` (default `false`),
`notify_service` (service selector filtered to the `notify` domain; the leading `notify.` is
stripped on save, so the stored value is a bare service name), `notify_repeat_hours` (default
`24`; `0` = once per drought), `notify_url` (optional deep link).

Decision inside `async_evaluate()`:

- disabled → do nothing.
- **Confirmed recovery** — no plant is `dry` **and** no plant is `no_data`/`suspect_battery`
  → clear `last_notified`. A plant blinking offline does *not* re-arm notifications.
- any plant `dry` → send only when **both**:
  - `last_notified is None` (drought not yet announced), and
  - the hard floor `now - last_notified >= notify_repeat_hours` holds for every send,
  then write `last_notified = now` (write-ahead), persist immediately, and dispatch.
- with `notify_repeat_hours = 0`, sends happen only after a confirmed recovery — never as a
  repeat, so a plant oscillating around the thresholds cannot machine-gun the phone.

Message: title `Plants need water`; message `3 plants need water: Ficus, Monstera, Basil`;
`data.url` = `notify_url` when set.

Dispatch: `hass.async_create_task(hass.services.async_call("notify", service, data,
blocking=True))` wrapped in a try/except that creates/clears the repair issue.
`blocking=False` cannot report success (failures are only logged inside
`_run_service_call_catch_exceptions`), so the wrapper is required. The evaluate loop never
awaits the send.

Failure handling: service missing/misconfigured → log, `ir.async_create_issue(...,
is_fixable=False, severity=IssueSeverity.WARNING,
translation_key="notify_service_missing")`, keep evaluating. Clearing uses
`ir.async_delete_issue` on the next successful dispatch. The issue also covers the case
`notify_enabled = true` with an empty service, and the options flow refuses to enable
notifications without a service.

Suspect batteries produce a second, non-fixable issue (`battery_suspect`) listing affected
plants — the mitigation for "suspect plants are never notified as thirsty".

---

## Card

```yaml
type: custom:watering-project-card
title: Plants        # optional
id: plants-main      # optional, enables collapse persistence
```

Registered in the card picker via `window.customCards.push({type, name, description})`;
implements `getCardSize()` and `getGridOptions()`.

Four sections, driven purely by server `status`:

| # | Section | Status | Behaviour |
| --- | --- | --- | --- |
| 1 | Suspect battery | `suspect_battery` | Collapsible, **hidden** when empty |
| 2 | Too dry | `dry` | Shown whenever at least one plant exists |
| 3 | No data | `no_data` | Collapsible |
| 4 | Well watered | `healthy` | **Collapsed by default** |

- Ordering inside a section: rooms alphabetically, then moisture ascending, `null` last;
  `Unassigned` last.
- Compact row: plant name + moisture %, plus a `temp?`/`batt?` badge when the entity exists
  but does not report. A plant without a battery sensor is not "unknown" — it has none, and
  gets no badge.
- Expanded row: temperature, battery %, absolute **last reported** timestamp
  (`last_reported`, falling back to `last_updated`; never `last_changed`), area, `zero_days`
  when suspect. Absolute timestamps only — relative text would need a render tick.
- Excluded footer: collapsed row listing `excluded[]` with reasons.
- Display values come from `hass.states` for the payload's entity ids; membership comes from
  the payload.
- Update model: the `hass` setter compares a memo signature of payload identity + relevant
  `state`/`attributes` and early-returns when unchanged. `last_reported` is **not** in the
  memo (it changes on no-op reports).
- States: connecting, `not_loaded` (error row + retry), schema mismatch, empty (pointer to
  options). The empty state supersedes "always shown" for section 2.
- Collapse state: `localStorage["watering-project:" + (id || "default") + ":collapsed"]` in
  try/catch; no persistence without `id`.
- Theming: HA CSS variables only. Sections expose `aria-expanded`, keyboard operable.
- English-only strings in v1, hardcoded.

### Registration (manual in v1)

Auto-registration was cut deliberately: it was the most version-fragile code in the project
(Lovelace data shape changes, `ResourceYAMLCollection` lacking `async_create_item`, duplicate
resources on every restart, cache-busting) for a saving of one user click.

- Static path is registered **once in `async_setup`** via
  `hass.http.async_register_static_paths([StaticPathConfig(...)])` (the module-level helper
  was removed in 2026.x), guarded by a `hass.data` flag — per-entry registration raises on the
  duplicate aiohttp route after the first reload.
- Serve with `cache_headers=False` (defaults send `max-age=2678400`), and instruct the user
  once, in README and docs:

```yaml
lovelace:
  resources:
    - url: /watering_project/watering-project-card.js?v=0.1.0
      type: module
```

- Documented consequence: after an upgrade the user must bump `?v=` manually, otherwise the
  cached card persists (companion-app webviews cache JS aggressively).
- `__init__.py` defines `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` because
  `async_setup` exists; hassfest rejects an integration with `async_setup` and no schema.
- `hacs.json` declares the supported floor `2026.10.0`, and `async_setup_entry` enforces it at
  runtime by raising `ConfigEntryError` with a readable message. The manifest schema has no
  minimum-version key, so the floor is not duplicated there.
- `manifest.json`: `"dependencies": ["http", "websocket_api"]`,
  `"documentation": "https://github.com/Mixermachine/WateringProject#readme"`,
  `"issue_tracker": "https://github.com/Mixermachine/WateringProject/issues"`,
  `"iot_class": "local_polling"`, `"integration_type": "hub"`.

---

## Deployment

User-facing instructions live in [`docs/quickstart.md`](docs/quickstart.md); this section is
the maintainer view.

No publishing required. Primary path is a Docker-mounted dev instance; the same folder works
as a manual install on a real HA instance.

**Repository:** <https://github.com/Mixermachine/WateringProject> (private). HACS is not used.

### Docker mount (primary dev / e2e path)

```yaml
volumes:
  - ./custom_components/watering_project:/config/custom_components/watering_project
```

Live-edited, no build step on the HA side: the card JS is committed build output
(`custom_components/watering_project/www/watering-project-card.js`).

### Manual install on a real instance

1. Copy the **whole** `custom_components/watering_project/` folder to
   `/config/custom_components/watering_project/`. The folder name must equal the domain
   `watering_project` — a partial or renamed copy is the usual "integration not found" cause.
   No Node, no npm, no Python install needed on the HA host.
2. Restart Home Assistant.
3. Add the integration (Settings → Devices & services → Add integration → *Watering Project*)
   and pick the plant devices in the options flow.
4. Add the Lovelace resource once (see Registration above), then add the card.

### Upgrade

Replace the folder, restart HA, and bump the `?v=` query on the resource line (for example
`?v=0.1.0` → `?v=0.2.0`). Skipping the `?v=` bump leaves the old card cached — companion-app
webviews cache JS aggressively. Payload compatibility across mismatched versions is handled by
`schema_version` and rendered as a mismatch row rather than a blank card.

### Distribution status

- Ships **without** HACS, without a release workflow, without auto-update and without update
  notifications.
- Publishing scaffolding is kept but inactive: `hacs.json` and the manifest metadata above are
  present so that publishing later is a repository-visibility change plus a tag, not a refactor.
- HACS validation in CI is enabled when the repository becomes public; `hassfest` runs from
  day one because it validates the manifest, strings and translations we rely on.

---

## Configuration

| Option | Default | Range | Meaning |
| --- | --- | --- | --- |
| Moisture default threshold | `70` % | 1–100 | Below this a plant is `dry` |
| Battery suspect duration | `30` days | 1–365 | `0%` persistence to become `suspect_battery` |
| Dry hysteresis | `5` points | fixed (`const.py`) | Recovery requires `threshold + 5` |
| Include devices | `[]` | `DeviceSelector(multiple=True)` | Overrides keyword exclusion |
| Exclude devices | `[]` | `DeviceSelector(multiple=True)` | Always wins |
| Enable notifications | `false` | bool | Master switch |
| Notify service | `""` | service selector, `notify` domain | Stored bare, e.g. `mobile_app_pixel` |
| Notify repeat | `24` h | 0–168 | `0` = once per drought |
| Notify URL | `""` | text | Deep link in the push |

Device ids validated against the device registry on save; unknown ids warn, not fail. Saving
reloads the entry.

---

## Diagnostics

`diagnostics.py` dumps: entry options, `schema_version`, plant and excluded counts, per-plant
`status`/`zero_days`/`never_reported`, tracker record count, `last_notified`, and repair-issue
state. Redacted: entity ids, device ids, labels, area names, `notify_service`, `notify_url`
replaced with stable hashes or `***`, so a diagnostic download does not leak the home layout.

---

## Testing

Hard requirement: no real Zigbee hardware, no phone. Six layers.

### L1 — pure classification (plain pytest, no HA, no fixtures)

- 29 vs 31 days against a 30-day limit; missing `zero_since`; `never_reported`.
- Priority: suspect beats dry; `needs_water` is false for `suspect_battery`; the accepted
  blind spot is asserted explicitly (documented behaviour, not an accident).
- Hysteresis: with previous status `dry`, `69 → 71 → 69` stays `dry` throughout (no
  `healthy` flash); `69 → 76` becomes `healthy`; jitter narrower than the band cannot flip.
- Hysteresis across `no_data`: `dry → no_data → 72` stays `dry`.
- Coercion: `null`, `""`, `"-"`, `"45.0"`, `NaN`, `Infinity`, missing state → `no_data`.
- Per-plant `threshold` override; overwatered → `healthy`.
- Notification counts are **not** asserted here (this layer has no notifier).

### L2 — HA in-process (`pytest-homeassistant-custom-component`)

`tests/test_fake_hardware.py` already runs the whole chain in-process: it loads
`dev/fake_plants` (bypassing the loader, since the dev integration is not installed),
creates its registry entries and `notify.fake_phone`, sets up a real config entry, and
asserts discovery → verdicts → repair issues → one notification per drought.

- Discovery: records, predicate, enabled-only siblings, tie-break, area precedence, label
  fallback (`name is None`), `plant_id` stability across rename; inclusion precedence
  (`exclude > include > keyword > default`) and all `reason` values; restricted non-admin
  filtering.
- Tracker: set/clear/out-of-range; `never_reported`; store round-trip across restart; 90-day
  pruning; survives disappearance of the moisture entity.
- Classification persistence: verdicts survive restart, so a plant inside the hysteresis band
  does **not** re-notify after a restart (the test uses a value in
  `[threshold, threshold + 5)`, otherwise it passes vacuously).
- Entities: status/needs_water values per verdict; `available = False` for `no_data`;
  aggregates; `unique_id` stability; entity removed when a plant stops qualifying and no
  zombie state remains; disappear/reappear in the same tick; a ZHA device update or
  re-creation neither loses nor duplicates our entities; restart recomputes.
- Notifications (`async_mock_service(hass, "notify", "mobile_app_test")`):
  - no dry plants at startup → zero calls;
  - first dry plant → exactly one call; assert `title`, `message`, `data.url`;
  - second plant dries inside the window → still one call;
  - `freezer` past `notify_repeat_hours` → one repeat with the updated list;
  - **hard floor**: two triggers 50 ms apart → one call;
  - **confirmed recovery** clears the re-arm; a plant going `no_data` does **not** clear it
    (the flap scenario: `dry → no_data → dry → no_data` sends no extra pushes);
  - `notify_repeat_hours = 0` → one call per drought, none on oscillation;
  - restart with persisted `last_notified` → no duplicate;
  - unknown/removed service → no exception, repair issue created, entities still correct;
    next success clears the issue;
  - `notify_enabled = false` → zero calls; enabled with empty service → issue, no crash.
- Evaluation: single-flight (concurrent triggers → one notification, one push); one test per
  trigger (state change, `freezer.tick(days=31)` + `async_fire_time_changed`, registry change,
  options reload); timer guard skips a pass when nothing is time-sensitive; an exception in
  evaluation sets statuses to `no_data` and keeps the timer alive.
- Websocket subscription: initial payload arrives as an **event** (not only as `result`);
  push on hashed change; **no push** for `moisture`/`last_seen` churn or fractional
  `zero_days`; `int(zero_days)` change pushes once per day; non-admin user can subscribe and
  receives updates; reconnect re-delivers a full payload; unsubscribed/closed connections are
  skipped; `not_loaded` error shape.
- Diagnostics: redaction verified.
- **Golden fixture**: `test_golden` builds the payload with a **fixed `now` constant** and
  serialises `zero_days` as an integer, so `frontend/test/fixtures/plants.golden.json` is
  byte-stable without freezing the clock. `pytest --update-golden` regenerates it; CI fails
  on drift.

### Harness constraints

There is exactly **one test leg**: `requirements_test.txt` pins
`pytest-homeassistant-custom-component==0.13.373`, which in turn pins
`homeassistant==2026.10.2` and requires **Python ≥ 3.14**. The supported floor is therefore the
release the maintainer runs and CI tests — no compatibility shim for older Home Assistant
releases.

Run it via `docker/test.Dockerfile` (`python:3.14-slim`). The harness is Linux-only in two
respects: it blocks sockets except AF_UNIX, and `aiodns` refuses the Proactor loop Windows
forces on Home Assistant. A native Windows venv on Python 3.13 can no longer run the suite, by
design; that is the cost of the single-leg floor.

### L3 — card (Vitest + jsdom, golden fixture) — implemented

36 tests in `frontend/`: section placement per `status`, ordering (rooms, moisture, `null`
last, `Unassigned` last), collapse round-trip with and without `id`, expanded rows, badges,
excluded footer, loading/`not_loaded`/schema-mismatch/empty states, and the update budget —
**1000 unrelated state updates → zero re-renders**; **200 plants: initial render < 300 ms,
memo hit < 0.1 ms**.

Two traps found here, both worth remembering: Lit's generated accessor for a declared `hass`
property **shadows** a hand-written memoising setter (so `hass` is deliberately not a reactive
property), and this jsdom build hands out a `localStorage` without its prototype methods, so
`frontend/test/setup.ts` installs a minimal in-memory `Storage`.

### L3b — Vitest browser mode

Real DOM for interaction and layout, no Docker. Deferred to M4, where Playwright already
downloads a browser image.

### L4 — end-to-end (Playwright against Docker HA) — implemented, 8 scenarios

`cd tests/e2e && docker compose up -d && npx playwright test` — 8/8 green against
`ghcr.io/home-assistant/home-assistant:2026.10.2`.

Harness (`harness/api.ts`): onboarding automation (`/api/onboarding/users` → `core_config` →
`analytics` → `integration`), token via `/auth/token`, entries created through
`/api/config/config_entries/flow`, **options set through the real options flow**
(`POST /api/config/config_entries/options/flow` with the **entry id** as `handler`), and
`localStorage["hassTokens"]` seeded via `addInitScript`. The dashboard is YAML
(`config/ui-lovelace.yaml`) with the resource declared under `lovelace.resources` in
`configuration.yaml`.

`dev/fake_plants/` (dev-only; mounted into `custom_components/fake_plants`) creates real
registry entries via `er/dr.async_get_or_create` with `device_id`, `suggested_area` and
`config_entry_id`, registers `notify.fake_phone` as a plain
`hass.services.async_register("notify", ...)`, mirrors the last message and a call counter into
`sensor.fake_last_notification` / `sensor.fake_notification_count`, and exposes
`set_value`/`set_moisture`/`set_battery`/`reset_notifications`.

**Deviation from the original plan:** backdated battery ages come from the dev-only
`fake_plants.age_battery` service (which writes `zero_since` on the Watering Project store and
re-evaluates) instead of a pre-seeded `.storage/watering_project.<entry_id>` file. The entry id
is created at runtime, so a static file would have to hard-code it; the service produces the
same state without that coupling.

Readiness probing uses `/auth/providers`, never `/api/*`: unauthenticated `/api/` hits return
401 and Home Assistant bans the runner IP after a handful of them (observed, then fixed).

Scenarios:
1. Mount, resource present, card renders without console errors.
2. Four sections correct; `needs_water` entities match section 2.
3. Section 1 hidden with no suspect sensors; appears with the pre-seeded 31-day `zero_since`.
4. Plant `dry` → `healthy` live, hysteresis respected (`72 %` keeps it dry, `76 %` releases).
5. Collapse/expand survives reload with `id`.
6. Rooms alphabetical, `Unassigned` last.
7. Excluded device disappears after reload and shows in the excluded footer.
8. With `notify.fake_phone` configured, drying a plant calls the service once,
   `sensor.fake_last_notification` matches section 2, and a second dry plant inside the window
   produces no second call.

### L5 — acceptance (manual, real hardware)

HACS install; real ZHA sensors appear; 0%-battery quirk filtered; one real push arrives;
restart with a plant at `0%` keeps `zero_days`; 10-minute soak.

### CI (GitHub Actions)

`.github/workflows/` — all jobs are merge blockers:

- `tests.yml` → **pytest** job: builds `docker/test.Dockerfile` and runs the suite inside it
  (golden fixture is compared, not regenerated), then `ruff check` + `ruff format --check`.
  **card** job: `npm ci`, `tsc --noEmit`, `vitest run`, then `vite build` and
  `git diff --exit-code custom_components/watering_project/www` so a stale committed bundle
  fails the build.
- `e2e.yml` → `npm ci`, Playwright chromium, `docker compose up -d`, 8 scenarios; container
  logs and `test-results/` are uploaded on failure and the stack is torn down with `-v`.
- `hassfest.yml` → manifest, strings and translations. HACS validation is enabled once the
  repository becomes public.
- Dependency bumps are deliberate commits that raise the floor, never a nightly job.

---

## Development

```bash
# integration tests (Linux; the image is built once and then reused)
docker build -f docker/test.Dockerfile -t watering-project-tests .
docker run --rm -v "$PWD":/work -w /work watering-project-tests pytest -q
# Git Bash on Windows mangles the container path; use:
#   MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/work" -w /work watering-project-tests pytest -q

# prove the contract fixture did not drift (same check as CI job A)
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/work" -w /work watering-project-tests \
  sh -c 'pytest tests/test_golden.py --update-golden -q && git diff --exit-code -- frontend/test/fixtures'

# regenerate the contract fixture consumed by Vitest
pytest -q tests/test_golden.py --update-golden

# card
cd frontend && npm install && npm run build   # emits custom_components/watering_project/www/
cd frontend && npm test

# e2e (needs docker)
cd tests/e2e && docker compose up -d --build
npx playwright test
```

Lint/format: `ruff check` + `ruff format` (Python), `eslint` + `prettier` (TS), pre-commit.

Status: 151 Python tests, 36 Vitest tests and 8 Playwright scenarios green on
HA 2026.10.2 / Python 3.14 (classification,
discovery, battery tracker, verdict history, evaluation pipeline, entities, config/options
flow, version gate, notification matrix, websocket subscription, diagnostics, static card
serving, fake-hardware round trip, golden fixture), 36 Vitest tests for the card
(`cd frontend && npm test`) and 8 Playwright scenarios against a real container
(`cd tests/e2e && docker compose up -d && npx playwright test`).

---

## Repository layout

```
custom_components/watering_project/
  __init__.py            # async_setup (static path), async_setup_entry, unload
  evaluate.py            # async_evaluate() single-flight pipeline + triggers + teardown
  payload.py             # payload contract + change signature
  notifications.py       # confirmed recovery, hard floor, repair issues
  websocket_api.py       # watering_project/subscribe + permission filter
  discovery.py           # single discovery authority
  classification.py      # pure verdict function
  battery.py             # battery observation tracker
  verdicts.py            # persisted previous statuses (hysteresis across restart)
  store.py               # one versioned Store document per entry
  entity.py
  binary_sensor.py       # needs_water per plant, plants_need_water aggregate
  sensor.py              # status per plant, plants_needing_water aggregate
  diagnostics.py
  config_flow.py
  const.py
  manifest.json
  strings.json, translations/en.json
  www/watering-project-card.js   # committed build output
frontend/
  src/watering-project-card.ts   # Lit element + card-picker registration
  src/grouping.ts                # sections, ordering, formatting (presentation only)
  src/types.ts                   # payload schema, EXPECTED_SCHEMA
  test/card.test.ts              # render states, collapse, badges, update budget
  test/grouping.test.ts          # ordering + formatting unit tests
  test/setup.ts                  # jsdom localStorage polyfill
  test/fixtures/plants.golden.json
  package.json, package-lock.json, vite.config.ts, tsconfig.json
tests/
  conftest.py, test_classification.py, test_discovery.py, test_battery.py,
  test_verdicts.py, test_evaluate.py, test_entities.py, test_config_flow.py,
  test_notifications.py, test_websocket.py, test_diagnostics.py, test_init.py,
  test_golden.py
docker/test.Dockerfile   # Linux test image (authoritative harness)
docs/quickstart.md          # user-facing install/configure/automation guide
tests/e2e/
  README.md, docker-compose.yml, playwright.config.ts, package.json, tsconfig.json
  config/{configuration.yaml,ui-lovelace.yaml}   # runtime state gitignored
  harness/{api,state,global-setup}.ts
  specs/watering-card.spec.ts                    # 8 scenarios
dev/fake_plants/         # dev-only fake hardware, own config entry
  __init__.py            # devices/areas/entities + set_* services
  config_flow.py         # single-instance UI flow
  manifest.json, strings.json, translations/en.json, services.yaml
.github/workflows/
  tests.yml, e2e.yml, hassfest.yml
hacs.json                # name + HA floor; publish-ready, no HACS install in v1
LICENSE                  # MIT
requirements_test.txt
```

`strings.json` keys are load-bearing: `entity.binary_sensor.needs_water.name`,
`entity.sensor.status.name` + `state.*` for all four enum values, both aggregate names,
`issues.notify_service_missing.*`, `issues.battery_suspect.*`, and the config/options flow
step titles.

---

## Known limitations

1. **Suspect battery wins over dry.** Such plants are never notified as thirsty; they appear
   in section 1 and raise a `battery_suspect` repair issue instead.
2. **No backfill.** The battery clock starts at installation.
3. **Entity ids do not follow device renames** — they are fixed at first creation, because HA
   computes `suggested_object_id` once. Friendly names do follow.
4. **Entities with no state object are invisible** (`device_class` lives in state attributes).
5. **The integration co-owns the plant's source device** (`config_entries` gains our entry),
   which is what makes the entities group under it.
6. **Restricted non-admin users** see only plants they may read; others are reported as
   `reason: "permission"`, and `summary` is per-connection.
7. **Resource registration is manual**; after an upgrade the user must bump `?v=`.
8. **Single notification target**, English-only message, no quiet hours.
9. **Notifications are best-effort**: a failing service raises a repair issue, not a retry
   queue.
10. **`last_changed` is not used for staleness anywhere.**
11. **A frozen sensor looks healthy**: a moisture sensor that stops reporting while holding
    `78 %` is `healthy` forever — `no_data` only covers literal `unavailable`/`unknown`.
    `last_reported` is displayed but never thresholded.
12. **No fallback discovery in the card**: backend failure renders an error row, loudly.
13. **`0%` is a heuristic**: `<= 1%` counts as zero.

---

## Milestones

0. **M0 — repo**: local git, private remote, `.gitignore` covering Python/Node/e2e artifacts
   while committing the card build output. **Done.**
1. **M1 — decide**: `discovery.py`, `battery.py`, `verdicts.py`, `store.py`,
   `classification.py`, pytest + golden fixture. **Done.**
2. **M2 — expose** (split):
   - **M2a — pipeline + entities + config**: `evaluate.py` (single-flight, debounced state and
     registry triggers, 60 s timer with skip guard, teardown), `binary_sensor.py`,
     `sensor.py`, `config_flow.py` (single instance + options flow with validation and
     `notify.` normalisation), `strings.json` / `translations/en.json`. **Done.**
   - **M2b — notifications + transport**: notification decision (confirmed recovery + hard
     floor, write-ahead state), repair issues, `watering_project/subscribe` with
     per-connection permission filtering, payload builder + signature, static path,
     diagnostics. **Done.**
3. **M3 — show**: card (sections, ordering, badges, collapse, states), Vitest + browser mode.
   Card and Vitest done (36 tests); browser mode moved next to Playwright in M4.
4. **M4 — prove**: `dev/fake_plants` + notify stub (done, exercised in-process by
   `tests/test_fake_hardware.py`), docker compose + Playwright (done, 8/8 scenarios)
   harness, pre-seeded storage fixture, all 8 Playwright scenarios.
5. **M5 — package**: `hacs.json` (inactive), strings/translations, three CI workflows
   (`tests`, `e2e`, `hassfest`), README install + upgrade instructions. `hassfest` clean.
   Tagged `v0.1.0`. Release workflow and HACS publication stay deferred.

## Definition of done (v1)

- A plant with an expired `zero_since` never renders "Well watered"; proven by an L1 test and
  an L2 entity assertion sharing one fixture.
- Notification matrix green: one push per drought, repeat after the window, none on restart,
  none on `no_data` flapping, repair issue when the service is broken.
- Hysteresis proven across restarts: a plant inside the band does not re-notify.
- Non-admin subscription delivers live updates.
- No push for state churn: a suspect plant generates at most one push per day.
- Zero console errors, keyboard operable, no hardcoded colors, zero re-renders on unrelated
  state churn.
- CI green on all five jobs; HACS + hassfest validation passing.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Aaron Dietz.

---

## Status

M0–M5 implemented: v1 is feature-complete and tagged `v0.1.0`. Repository:
<https://github.com/Mixermachine/WateringProject> (private, branch `main`).

Implemented:

- **M1** — decide layer: `store.py`, `discovery.py`, `battery.py`, `verdicts.py`,
  `classification.py`, golden contract fixture.
- **M2a** — `evaluate.py` (single-flight pipeline, debounced state/registry triggers, 60 s
  timer with skip guard, teardown), `binary_sensor.py` + `sensor.py` (per-plant
  `needs_water`/`status`, aggregates on a service device), `config_flow.py` (single instance,
  options flow with device selectors and notify validation), `strings.json` +
  `translations/en.json`.
- **M2b** — `notifications.py` (confirmed recovery, hard floor, write-ahead state, repair
  issues), `payload.py` (single payload contract + change signature), `websocket_api.py`
  (`watering_project/subscribe` with per-connection permission filtering, initial payload
  as an event), static path registration, `diagnostics.py` with redaction.
- **M3** — Lit card in `frontend/` (four sections, room/moisture ordering, compact rows with
  expand, badges, excluded footer, collapse persistence, loading/`not_loaded`/
  schema-mismatch/empty states), built to `custom_components/watering_project/www/` and
  served by the integration's static path.
- **M4** — `dev/fake_plants` + `notify.fake_phone`, docker-compose Home Assistant 2026.10.2,
  Playwright harness (API onboarding, config/options flows, token seeding) with the 8
  scenarios from L4.
- **M5** — CI (`tests`, `e2e`, `hassfest`), hassfest clean, install/upgrade docs, tag `v0.1.0`.

151 Python tests in the Linux image (HA 2026.10.2 / Python 3.14) + 36 Vitest tests + 8
Playwright scenarios against a real Home Assistant container. `hassfest` reports zero invalid
integrations. Tags: `v0.1.0`.

Assumed defaults unless revised: MIT license, `manifest.json` version `0.1.0`, plant label
from device name, English only, single notify target, single config entry, no overwatering
threshold, manual resource registration, no HACS publishing.
