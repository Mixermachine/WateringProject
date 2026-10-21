"""Diagnostics download: useful for support, redacted by default.

Nothing here is a secret, but entity ids, device ids, labels and area names
describe the layout of the user's home, and ``notify_service``/``notify_url``
identify the phone. They are replaced with stable hashes before download.
"""

from __future__ import annotations

import hashlib
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_NOTIFY_SERVICE, CONF_NOTIFY_URL, DOMAIN, SCHEMA_VERSION
from .evaluate import WateringRuntime


def _redact(value: str | None) -> str | None:
    """Replace a value with a short stable hash."""
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:12]}"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[WateringRuntime]
) -> dict[str, Any]:
    """Return a redacted snapshot of the integration state."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator

    plants = []
    for plant_id, plant in sorted(coordinator.plants.items()):
        verdict = coordinator.verdict(plant_id)
        fact = runtime.battery.facts(plant.battery_entity_id)
        plants.append(
            {
                "plant_id": _redact(plant_id),
                "label": _redact(plant.label),
                "area": _redact(plant.area_name),
                "moisture_entity": _redact(plant.moisture_entity_id),
                "has_battery_entity": plant.battery_entity_id is not None,
                "has_temperature_entity": plant.temperature_entity_id is not None,
                "status": verdict.status if verdict else None,
                "zero_days": verdict.zero_days if verdict else None,
                "battery_never_reported": fact.never_reported if fact else None,
            }
        )

    options = dict(entry.options)
    for key in (CONF_NOTIFY_SERVICE, CONF_NOTIFY_URL):
        if options.get(key):
            options[key] = _redact(str(options[key]))

    return {
        "domain": DOMAIN,
        "entry_id": _redact(entry.entry_id),
        "options": options,
        "schema_version": SCHEMA_VERSION,
        "counts": {
            "plants": len(coordinator.plants),
            "excluded": len(coordinator.excluded),
            "needs_water": coordinator.needs_water_count,
            "payload_version": coordinator.payload_version,
        },
        "battery_records": len(runtime.battery.records),
        "last_notified": (
            runtime.coordinator.notifications.last_notified.isoformat()
            if runtime.coordinator.notifications.last_notified
            else None
        ),
        "plants": plants,
        "excluded": [
            {"device_id": _redact(record.device_id), "reason": record.reason}
            for record in coordinator.excluded
        ],
    }
