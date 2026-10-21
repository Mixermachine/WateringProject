"""The payload contract shared by the websocket API and the card.

One function builds the payload, so the permission filter, the summary
invariants and the field set cannot drift between callers. ``schema_version`` is
part of the contract: HACS-style upgrades can pair a new integration with a
cached old card, and the card renders an explicit mismatch row instead of
cascading ``undefined``s.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .classification import BatteryFact, PlantRecord, Verdict
from .const import (
    CONF_BATTERY_SUSPECT_DAYS,
    CONF_EXCLUDE_DEVICES,
    CONF_INCLUDE_DEVICES,
    CONF_MOISTURE_DEFAULT,
    CONF_NOTIFY_ENABLED,
    DEFAULT_BATTERY_SUSPECT_DAYS,
    DEFAULT_MOISTURE_THRESHOLD,
    EXCLUDE_REASON_PERMISSION,
    SCHEMA_VERSION,
    STATUS_DRY,
    STATUS_HEALTHY,
    STATUS_NO_DATA,
    STATUS_SUSPECT_BATTERY,
)
from .discovery import ExcludedRecord


def _option(entry: ConfigEntry, key: str, default: Any) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


def payload_config(entry: ConfigEntry) -> dict[str, Any]:
    """The subset of options the card needs."""
    return {
        CONF_MOISTURE_DEFAULT: _option(entry, CONF_MOISTURE_DEFAULT, DEFAULT_MOISTURE_THRESHOLD),
        CONF_BATTERY_SUSPECT_DAYS: _option(
            entry, CONF_BATTERY_SUSPECT_DAYS, DEFAULT_BATTERY_SUSPECT_DAYS
        ),
        CONF_INCLUDE_DEVICES: list(_option(entry, CONF_INCLUDE_DEVICES, [])),
        CONF_EXCLUDE_DEVICES: list(_option(entry, CONF_EXCLUDE_DEVICES, [])),
        CONF_NOTIFY_ENABLED: bool(_option(entry, CONF_NOTIFY_ENABLED, False)),
    }


def _battery_block(fact: BatteryFact | None) -> dict[str, Any]:
    if fact is None:
        return {"last_value": None, "last_seen": None, "never_reported": True}
    return {
        "last_value": fact.display_value,
        "last_seen": fact.last_seen.isoformat() if fact.last_seen else None,
        "never_reported": fact.never_reported,
    }


def build_plant(
    plant: PlantRecord,
    verdict: Verdict,
    fact: BatteryFact | None,
) -> dict[str, Any]:
    """One plant record as the card consumes it."""
    return {
        "plant_id": plant.plant_id,
        "label": plant.label,
        "area_id": plant.area_id,
        "area_name": plant.area_name,
        "moisture_entity_id": plant.moisture_entity_id,
        "battery_entity_id": plant.battery_entity_id,
        "temperature_entity_id": plant.temperature_entity_id,
        "threshold": plant.threshold,
        "status": verdict.status,
        "needs_water": verdict.needs_water,
        "moisture": verdict.moisture,
        "zero_days": verdict.zero_days,
        "battery": _battery_block(fact),
    }


def build_summary(plants: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Counts per status.

    Invariant: ``total == len(plants) == sum(status counts)``. ``excluded``
    records are never counted.
    """
    counts = {
        STATUS_SUSPECT_BATTERY: 0,
        STATUS_DRY: 0,
        STATUS_NO_DATA: 0,
        STATUS_HEALTHY: 0,
    }
    total = 0
    for plant in plants:
        total += 1
        status = plant.get("status")
        if status in counts:
            counts[status] += 1
    return {
        "total": total,
        "suspect_battery": counts[STATUS_SUSPECT_BATTERY],
        "dry": counts[STATUS_DRY],
        "no_data": counts[STATUS_NO_DATA],
        "healthy": counts[STATUS_HEALTHY],
        "needs_water": counts[STATUS_DRY] > 0,
    }


def build_payload(
    entry: ConfigEntry,
    plants: Mapping[str, PlantRecord],
    verdicts: Mapping[str, Verdict],
    excluded: Iterable[ExcludedRecord],
    facts: Mapping[str, BatteryFact],
    *,
    entity_allowed: Any | None = None,
) -> dict[str, Any]:
    """Build the full payload, optionally filtered per connection user.

    ``entity_allowed`` is a predicate taking an entity id. It exists because
    ``hass.states`` is permission-filtered for non-admins while registry
    responses are not: without the filter, a restricted user would receive
    records for entities they cannot read and see phantom rows.
    """
    plant_payloads: list[dict[str, Any]] = []
    excluded_payloads: list[dict[str, Any]] = []

    for plant in plants.values():
        verdict = verdicts.get(plant.plant_id)
        if verdict is None:
            continue
        if entity_allowed is not None and not entity_allowed(plant.moisture_entity_id):
            excluded_payloads.append(
                {
                    "device_id": plant.plant_id,
                    "label": plant.label,
                    "reason": EXCLUDE_REASON_PERMISSION,
                }
            )
            continue
        plant_payloads.append(
            build_plant(
                plant,
                verdict,
                facts.get(plant.battery_entity_id) if plant.battery_entity_id else None,
            )
        )

    for record in excluded:
        excluded_payloads.append(
            {
                "device_id": record.device_id,
                "label": record.label,
                "reason": record.reason,
            }
        )

    plant_payloads.sort(key=lambda item: item["plant_id"])

    return {
        "schema_version": SCHEMA_VERSION,
        "config": payload_config(entry),
        "plants": plant_payloads,
        "summary": build_summary(plant_payloads),
        "excluded": excluded_payloads,
    }


def payload_signature(payload: Mapping[str, Any]) -> tuple[Any, ...]:
    """Fields whose change makes a push worth sending.

    ``moisture`` changes on every Zigbee report and must not trigger a push;
    ``zero_days`` is therefore reduced to whole days, which caps suspect-plant
    traffic at one push per day.
    """
    plants = tuple(
        (
            plant["plant_id"],
            plant["label"],
            plant["area_id"],
            plant["status"],
            plant["needs_water"],
            plant["threshold"],
            plant["battery"]["never_reported"],
            plant["zero_days"],
        )
        for plant in payload["plants"]
    )
    excluded = tuple((item["device_id"], item["reason"]) for item in payload["excluded"])
    return (
        payload["schema_version"],
        tuple(sorted(payload["config"].items(), key=lambda item: item[0])),
        plants,
        payload["summary"]["total"],
        payload["summary"]["needs_water"],
        excluded,
    )
