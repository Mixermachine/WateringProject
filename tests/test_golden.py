"""Golden contract fixture shared between pytest and Vitest.

The card consumes exactly one fixture: the payload shape the websocket
subscription will emit. Generating it here means the Python->TypeScript contract
is a real artifact instead of two hand-written handshakes, and the card tests
never have to build fake registries in JavaScript.

Determinism: ``classify()`` takes ``now`` as an argument and ``zero_days`` is
serialised as an integer, so the fixture is byte-stable without freezing the
clock. M2 extends the payload with the fields the real pipeline adds; the
assertion below is the tripwire for that change (regenerate with
``pytest --update-golden``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from custom_components.watering_project.classification import (
    BatteryFact,
    ClassificationConfig,
    PlantRecord,
    classify,
)
from custom_components.watering_project.const import SCHEMA_VERSION

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "frontend" / "test" / "fixtures" / "plants.golden.json"
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
CONFIG = ClassificationConfig(moisture_default=70, battery_suspect_days=30, dry_hysteresis=5)

PLANTS: tuple[PlantRecord, ...] = (
    PlantRecord(
        plant_id="dev_ficus",
        label="Ficus",
        moisture_entity_id="sensor.ficus_moisture",
        area_id="kitchen",
        area_name="Kitchen",
        battery_entity_id="sensor.ficus_battery",
        temperature_entity_id="sensor.ficus_temperature",
    ),
    PlantRecord(
        plant_id="dev_monstera",
        label="Monstera",
        moisture_entity_id="sensor.monstera_moisture",
        area_id="kitchen",
        area_name="Kitchen",
        battery_entity_id="sensor.monstera_battery",
    ),
    PlantRecord(
        plant_id="dev_basil",
        label="Basil",
        moisture_entity_id="sensor.basil_moisture",
        area_id="bedroom",
        area_name="Bedroom",
        battery_entity_id="sensor.basil_battery",
        temperature_entity_id="sensor.basil_temperature",
    ),
    PlantRecord(
        plant_id="dev_cactus",
        label="Cactus",
        moisture_entity_id="sensor.cactus_moisture",
        area_id=None,
        area_name=None,
        battery_entity_id=None,
    ),
    PlantRecord(
        plant_id="dev_orchid",
        label="Orchid",
        moisture_entity_id="sensor.orchid_moisture",
        area_id="bedroom",
        area_name="Bedroom",
        battery_entity_id="sensor.orchid_battery",
    ),
)

VALUES: dict[str, Any] = {
    "sensor.ficus_moisture": "42",
    "sensor.monstera_moisture": 12.5,
    "sensor.basil_moisture": "unavailable",
    "sensor.cactus_moisture": 91,
    "sensor.orchid_moisture": "72.0",
}

BATTERY: dict[str, BatteryFact] = {
    "sensor.ficus_battery": BatteryFact(
        zero_since=None, last_value=80, last_seen=NOW - timedelta(hours=2)
    ),
    "sensor.monstera_battery": BatteryFact(
        zero_since=NOW - timedelta(days=31), last_value=0, last_seen=NOW - timedelta(hours=5)
    ),
    "sensor.basil_battery": BatteryFact(zero_since=None, last_value=None, last_seen=None),
    "sensor.orchid_battery": BatteryFact(
        zero_since=None, last_value=255, last_seen=NOW - timedelta(minutes=30)
    ),
}

PREVIOUS: dict[str, str] = {"dev_orchid": "dry"}

EXCLUDED = (
    {
        "device_id": "dev_leak",
        "label": "Basement leak sensor",
        "reason": "keyword:leak",
    },
    {
        "device_id": "dev_garage",
        "label": "Garage sensor",
        "reason": "not_included",
    },
)


def build_payload() -> dict[str, Any]:
    """Build the deterministic payload consumed by the card tests."""
    verdicts = classify(PLANTS, VALUES, BATTERY, PREVIOUS, CONFIG, NOW)

    plants: list[dict[str, Any]] = []
    for plant, verdict in zip(PLANTS, verdicts, strict=True):
        battery = BATTERY.get(plant.battery_entity_id or "")
        plants.append(
            {
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
                "battery": {
                    "last_value": battery.last_value if battery else None,
                    "last_seen": (
                        battery.last_seen.isoformat() if battery and battery.last_seen else None
                    ),
                    "never_reported": battery.never_reported if battery else True,
                },
            }
        )

    summary = {
        "total": len(plants),
        "suspect_battery": sum(1 for item in plants if item["status"] == "suspect_battery"),
        "dry": sum(1 for item in plants if item["status"] == "dry"),
        "no_data": sum(1 for item in plants if item["status"] == "no_data"),
        "healthy": sum(1 for item in plants if item["status"] == "healthy"),
        "needs_water": any(item["needs_water"] for item in plants),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "config": {
            "moisture_default": CONFIG.moisture_default,
            "battery_suspect_days": CONFIG.battery_suspect_days,
            "include_devices": [],
            "exclude_devices": [],
            "notify_enabled": False,
        },
        "plants": plants,
        "summary": summary,
        "excluded": list(EXCLUDED),
    }


def test_golden_fixture_is_stable(update_golden: bool) -> None:
    text = json.dumps(build_payload(), indent=2, ensure_ascii=False) + "\n"

    if update_golden or not FIXTURE_PATH.exists():
        FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FIXTURE_PATH.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    assert FIXTURE_PATH.read_text(encoding="utf-8") == text, (
        "Golden fixture drifted. If the payload shape changed on purpose, run "
        "`pytest --update-golden` and commit the new fixture with the card changes."
    )


def test_golden_payload_has_consistent_counts() -> None:
    payload = build_payload()

    assert payload["summary"]["total"] == len(payload["plants"])
    assert payload["summary"]["total"] == sum(
        payload["summary"][key] for key in ("suspect_battery", "dry", "no_data", "healthy")
    )
    assert payload["summary"]["needs_water"] is any(
        plant["needs_water"] for plant in payload["plants"]
    )


def test_golden_payload_covers_every_status() -> None:
    statuses = {plant["status"] for plant in build_payload()["plants"]}

    assert statuses == {"suspect_battery", "dry", "no_data", "healthy"}
