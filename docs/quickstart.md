# Watering Project — quickstart

Plant moisture overview for Home Assistant. The integration decides everything
(discovery, battery clock, verdicts, notifications); the card only draws it.

## 1. Install

Copy the **whole** folder `custom_components/watering_project/` to
`/config/custom_components/watering_project/` on your Home Assistant host. The
folder name must be exactly `watering_project`.

No Node, no npm, no Python packages: the card bundle is committed build output.

Restart Home Assistant.

## 2. Add the integration

**Settings → Devices & services → Add integration → Watering Project.**

Requirements for a plant to be discovered:

- a `sensor` with `device_class: moisture` and unit `%`
- it must have a state object (an entity that never reported cannot be classified)
- the device must not look like a leak sensor (name/model containing `leak`,
  `flood`, `aquarium`, …) unless you add it explicitly

Battery (`device_class: battery`) and temperature sensors on the same device are
picked up automatically when present.

## 3. Configure

Open the integration's **Configure** dialog:

| Option | Default | Meaning |
| --- | --- | --- |
| `moisture_default` | 70 | Below this (%), a plant is too dry |
| `battery_suspect_days` | 30 | Flat battery for this long makes the reading untrustworthy |
| `include_devices` / `exclude_devices` | empty | Overrides the automatic keyword exclusion |
| `notify_enabled` + `notify_service` | off | Phone push when plants need water |
| `notify_repeat_hours` | 24 | Repeat interval while a drought continues (0 = never repeat) |
| `notify_url` | `/lovelace/0` | Opened when the notification is tapped |

Hysteresis is fixed: a plant that is already dry only counts as watered again at
`moisture_default + 5`.

## 4. Add the card

```yaml
lovelace:
  resources:
    - url: /watering_project/watering-project-card.js?v=0.1.0
      type: module
```

Then add a card:

```yaml
type: custom:watering-project-card
title: Plants      # optional
id: plants-main    # optional, needed for collapse persistence
```

After an upgrade, bump `?v=` (for example `?v=0.1.0` → `?v=0.2.0`). Without the
bump, phones and browsers keep the cached card. A stale card shows a version
mismatch row instead of breaking silently.

## 5. Automations

Everything the card shows is also a real entity:

- `binary_sensor.<plant>_needs_water` — `on` when that plant is too dry
- `sensor.<plant>_status` — `dry`, `healthy`, `no_data`, `suspect_battery`
- `binary_sensor.watering_project_plants_need_water` — any plant thirsty
- `sensor.watering_project_plants_needing_water` — count

Example:

```yaml
automation:
  - alias: Water the plants
    triggers:
      - trigger: state
        entity_id: binary_sensor.watering_project_plants_need_water
        to: "on"
    actions:
      - action: notify.mobile_app_my_phone
        data:
          title: Plants need water
          message: "{{ states('sensor.watering_project_plants_needing_water') }} plant(s) are thirsty"
```

## Troubleshooting

- **No plants found** — check `device_class: moisture` and unit `%` on the sensor,
  and that the device is not excluded. **Settings → Devices & services → Watering
  Project → Configure** lists excluded devices in the card footer.
- **Battery shows 0 % for weeks** — expected for rechargeable sensors. The plant is
  moved to section 1 and a repair issue appears; it will not be reported as thirsty
  while the battery is suspect.
- **Nothing in the card** — check the resource URL version and that the card element
  is `custom:watering-project-card`.
- **Diagnostics** — Settings → Devices & services → Watering Project → ⋮ →
  Download diagnostics. Identifiers and labels are hashed.
