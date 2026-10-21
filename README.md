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
- Blueprints (built-in notifier covers v1).

---

## Architecture

| Part | Tech | Owns |
| --- | --- | --- |
| `custom_components/watering_project/` | Python, HA **2025.2+** | **Everything that decides**: discovery, battery observation, classification, entities, notifications, config |
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
one push per day per suspect plant.

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
  - out of range (`<0`, `>100`) or non-numeric → unknown: keep `zero_since`, update
    `last_seen`.
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
  `DeviceInfo(identifiers={(DOMAIN, entry_id)}, entry_type=DeviceEntryType.SERVICE)`.
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
- Compact row: plant name + moisture %, plus a badge when temperature/battery is unknown.
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
  `async_register_static_paths([StaticPathConfig(...)])`, guarded by a `hass.data` flag —
  per-entry registration raises on the duplicate aiohttp route after the first reload.
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
- `manifest.json`: `"homeassistant": "2025.2.0"`, `"dependencies": ["http", "websocket_api"]`,
  `"documentation"`, `"issue_tracker"`, `"iot_class": "local_polling"`,
  `"integration_type": "hub"`.

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
- **Golden fixture**: `test_golden` freezes time (`freezer.move_to(fixed instant)`) before
  seeding and evaluating, so the committed `frontend/test/fixtures/plants.golden.json` is
  byte-stable.

### L3 — card (Vitest + jsdom, golden fixture)

Section placement per `status`, ordering (rooms, moisture, `null` last, `Unassigned` last),
collapse round-trip with and without `id`, expanded rows, excluded footer, connecting/
`not_loaded`/schema-mismatch/empty states, event handling, reconnect re-render. Budgets:
**1000 unrelated state updates → zero re-renders**; **200 plants: initial render < 300 ms,
memo hit < 0.1 ms in jsdom**.

### L3b — Vitest browser mode

Real DOM for interaction and layout, no Docker.

### L4 — end-to-end (Playwright against Docker HA) — 8 scenarios

Harness: onboarding automation (`/api/onboarding/users` → `core_config` → `analytics` →
`integration`), token via `auth/login_flow` + `/auth/token`,
`localStorage["hassTokens"]` via `addInitScript`, component mounted, config entry created,
**options set via the options flow** (`harness/options.ts`), resource registered before first
page load, polling assertions.

`dev/fake_plants/` (dev-only; mounted into `custom_components/fake_plants` by the compose file)
creates real registry entries via `er/dr.async_get_or_create` with `device_id` and areas,
registers `notify.fake_phone` as a plain `hass.services.async_register("notify", "fake_phone",
...)` before options are saved, and records the last message into
`sensor.fake_last_notification`. Backdated battery ages come from a **pre-seeded**
`.storage/watering_project.<entry_id>` file mounted into the container — a live container
cannot fake 31 days.

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

- **Job A (min)**: pinned HA 2025.2 + `requirements_test_min.txt`; runs pytest **including the
  golden staleness check** (`--update-golden` then `git diff --exit-code`). Merge blocker.
- **Job B (latest)**: `requirements_test_latest.txt`, nightly, `continue-on-error: true`,
  failure opens a bump PR.
- **Job C**: `vitest` (jsdom + browser mode) + `vite build`.
- **Job D**: docker compose + Playwright, artifacts on failure.
- **Job E**: `hassfest` + HACS validation.

---

## Development

```bash
# integration
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test_min.txt
pytest -q

# regenerate the contract fixture (must run with frozen time)
pytest -q tests/test_golden.py --update-golden

# card
cd frontend && npm install && npm run build   # emits custom_components/watering_project/www/
cd frontend && npm test

# e2e (needs docker)
cd tests/e2e && docker compose up -d --build
npx playwright test
```

Lint/format: `ruff` (Python), `eslint` + `prettier` (TS), pre-commit.

---

## Repository layout

```
custom_components/watering_project/
  __init__.py            # async_setup (static path), async_setup_entry, unload
  evaluate.py            # async_evaluate() single-flight pipeline + triggers + teardown
  discovery.py           # single discovery authority
  classification.py      # pure verdict function
  battery.py             # battery observation tracker
  verdicts.py            # persisted previous statuses (hysteresis across restart)
  notifications.py       # confirmed recovery, hard floor, repair issues
  store.py               # one versioned Store document per entry
  entity.py
  binary_sensor.py       # needs_water per plant, plants_need_water aggregate
  sensor.py              # status per plant, plants_needing_water aggregate
  websocket_api.py       # watering_project/subscribe + permission filter
  diagnostics.py
  config_flow.py
  const.py
  manifest.json
  strings.json, translations/en.json
  www/watering-project-card.js   # committed build output
frontend/
  src/watering-project-card.ts
  src/sections.ts        # presentation only
  src/types.ts           # payload schema, EXPECTED_SCHEMA
  test/fixtures/plants.golden.json
  package.json, vite.config.ts, tsconfig.json
tests/
  conftest.py, test_classification.py, test_discovery.py, test_battery.py,
  test_verdicts.py, test_entities.py, test_notifications.py, test_websocket.py,
  test_evaluate.py, test_diagnostics.py, test_golden.py
tests/e2e/
  docker-compose.yml, playwright.config.ts
  harness/{onboarding,token,options,dashboard}.ts
  fixtures/watering_project.storage.json
  specs/*.spec.ts
dev/fake_plants/         # dev-only fake hardware + notify.fake_phone
.github/workflows/
  tests.yml, e2e.yml, hassfest.yml
hacs.json
requirements_test_min.txt, requirements_test_latest.txt
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

1. **M1 — decide**: `discovery.py`, `battery.py`, `verdicts.py`, `store.py`,
   `classification.py`, pytest + golden fixture.
2. **M2 — expose**: `evaluate.py` (single-flight, triggers, teardown), entities,
   notifications + repair issues, `watering_project/subscribe` with permission filtering,
   static path.
3. **M3 — show**: card (sections, ordering, badges, collapse, states), Vitest + browser mode.
4. **M4 — prove**: `dev/fake_plants` + notify stub, docker compose, onboarding/options
   harness, pre-seeded storage fixture, all 8 Playwright scenarios.
5. **M5 — package**: `hacs.json`, strings/translations, hassfest/HACS jobs, release workflow,
   README resource instructions.

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

## Status

Specification complete, implementation not started.

Assumed defaults unless revised: MIT license, `manifest.json` version `0.1.0`, plant label
from device name, English only, single notify target, single config entry, no overwatering
threshold, manual resource registration.
