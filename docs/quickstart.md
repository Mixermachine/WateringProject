# Watering Project — quickstart

Plant moisture overview for Home Assistant. The integration decides everything
(discovery, battery clock, verdicts, notifications); the card only draws it.

## 1. Install

Copy the **whole** folder `custom_components/watering_project/` to
`/config/custom_components/watering_project/` on your Home Assistant host. The
folder name must be exactly `watering_project`.

No Node, no npm, no Python packages: the card bundle is committed build output.

### Home Assistant OS / Supervised

Build the zip once on your computer (`python scripts/package_integration.py` →
`dist/watering_project.zip`, one top-level `watering_project/` folder), then pick
one route:

- **Samba share** add-on (easiest): configure a user, open
  `\homeassistant\config\custom_components` in Explorer/Finder, drop the
  unzipped `watering_project` folder there.
- **Advanced SSH & Web Terminal** add-on: upload the zip to `/config` (SFTP or
  `scp`), then

  ```bash
  cd /config/custom_components
  unzip -o /config/watering_project.zip
  ha core restart
  ```

- **File editor** add-on: can create files but not upload folders — only usable if
  you paste every file by hand. Not recommended.

Verify the nesting: `/config/custom_components/watering_project/manifest.json` must
exist. A double folder (`watering_project/watering_project/`) is the usual "integration
not found" cause.

Restart Home Assistant (`ha core restart` or Settings → System → Restart).

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
| `notify_url` | empty | Opened when the notification is tapped; set it to `/watering-project` so taps land on the plant tab |

Hysteresis is fixed: a plant that is already dry only counts as watered again at
`moisture_default + 5`.

## 4. Add the sidebar tab

The intended surface is its **own tab in the sidebar**, not a card on the overview.

### Storage mode (default, no YAML)

1. Register the card resource once: **Settings → Dashboards → ⋮ → Resources → Add**
   and paste only the URL `/watering_project/watering-project-card.js?v=0.1.0`.
   Current Home Assistant asks for **no type** — resources are always ES modules
   now (older versions had a "JavaScript Module" dropdown; if yours does, pick it).
   In YAML the `type: module` line is still required.
2. **Settings → Dashboards → Add dashboard** → title `Watering Project`, icon
   `mdi:sprout`, **Show in sidebar** on.
3. Open the new tab → **Add card** → search *Watering Project*.

### YAML mode

```yaml
lovelace:
  mode: yaml
  resources:
    - url: /watering_project/watering-project-card.js?v=0.1.0
      type: module
  dashboards:
    watering-project:
      mode: yaml
      title: Watering Project
      icon: mdi:sprout
      show_in_sidebar: true
      filename: watering-dashboard.yaml
```

```yaml
# watering-dashboard.yaml — the card is the whole view
views:
  - title: Watering Project
    type: panel
    cards:
      - type: custom:watering-project-card
        id: plants-main
        title: Watering Project
```

`id` is optional but enables collapse persistence. On a storage-mode dashboard the
card can also be added to any view; `type: panel` simply gives it the full width.

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
  is `custom:watering-project-card`. Also check the tab exists under
  **Settings → Dashboards** and is set to show in the sidebar.
- **Diagnostics** — Settings → Devices & services → Watering Project → ⋮ →
  Download diagnostics. Identifiers and labels are hashed.
