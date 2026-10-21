"""Unit tests for the pure classification rules (no Home Assistant instance)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from custom_components.watering_project.classification import (
    BatteryFact,
    ClassificationConfig,
    PlantRecord,
    classify,
    next_status_history,
    parse_numeric,
)
from custom_components.watering_project.const import (
    STATUS_DRY,
    STATUS_HEALTHY,
    STATUS_NO_DATA,
    STATUS_SUSPECT_BATTERY,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
CONFIG = ClassificationConfig(moisture_default=70, battery_suspect_days=30, dry_hysteresis=5)


def plant(**overrides: object) -> PlantRecord:
    defaults: dict[str, object] = {
        "plant_id": "ficus",
        "label": "Ficus",
        "moisture_entity_id": "sensor.ficus_moisture",
        "area_id": "kitchen",
        "area_name": "Kitchen",
        "battery_entity_id": "sensor.ficus_battery",
        "temperature_entity_id": "sensor.ficus_temperature",
        "threshold": None,
    }
    defaults.update(overrides)
    return PlantRecord(**defaults)  # type: ignore[arg-type]


def run(
    *,
    moisture: object = 42,
    battery: BatteryFact | None = None,
    previous: str | None = None,
    record: PlantRecord | None = None,
    config: ClassificationConfig = CONFIG,
    now: datetime = NOW,
):
    record = record or plant()
    return classify(
        [record],
        {record.moisture_entity_id: moisture} if moisture is not _MISSING else {},
        {record.battery_entity_id: battery}
        if battery is not None and record.battery_entity_id
        else {},
        {record.plant_id: previous} if previous is not None else {},
        config,
        now,
    )[0]


class _Missing:
    pass


_MISSING = _Missing()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (42, 42.0),
        (42.5, 42.5),
        ("42", 42.0),
        (" 42.5 ", 42.5),
        ("-3", -3.0),
        (None, None),
        ("", None),
        ("   ", None),
        ("-", None),
        ("unknown", None),
        ("unavailable", None),
        ("none", None),
        ("abc", None),
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        (True, None),
        (False, None),
        ([], None),
        ({}, None),
    ],
)
def test_parse_numeric(raw: object, expected: float | None) -> None:
    assert parse_numeric(raw) == expected


def test_suspect_boundary_below_threshold() -> None:
    verdict = run(moisture=42, battery=BatteryFact(zero_since=NOW - timedelta(days=29)))
    assert verdict.status == STATUS_DRY
    assert verdict.zero_days == 29


def test_suspect_boundary_at_threshold() -> None:
    verdict = run(moisture=42, battery=BatteryFact(zero_since=NOW - timedelta(days=30)))
    assert verdict.status == STATUS_SUSPECT_BATTERY
    assert verdict.zero_days == 30


def test_suspect_wins_over_dry_and_does_not_request_water() -> None:
    """Documented trade-off: an untrustworthy sensor is not "thirsty"."""
    verdict = run(moisture=10, battery=BatteryFact(zero_since=NOW - timedelta(days=31)))
    assert verdict.status == STATUS_SUSPECT_BATTERY
    assert verdict.needs_water is False


def test_zero_days_is_floor_of_elapsed_and_never_negative() -> None:
    assert run(battery=BatteryFact(zero_since=NOW - timedelta(days=31, hours=20))).zero_days == 31
    assert run(battery=BatteryFact(zero_since=NOW + timedelta(days=1))).zero_days == 0


@pytest.mark.parametrize("moisture", [None, "unavailable", "unknown", "", "-", float("nan")])
def test_unusable_reading_is_no_data(moisture: object) -> None:
    assert run(moisture=moisture).status == STATUS_NO_DATA


def test_missing_entity_is_no_data() -> None:
    assert run(moisture=_MISSING).status == STATUS_NO_DATA


def test_dry_when_below_threshold() -> None:
    assert run(moisture=69.9).status == STATUS_DRY


def test_healthy_at_threshold() -> None:
    assert run(moisture=70).status == STATUS_HEALTHY


def test_hysteresis_holds_plant_dry_inside_band() -> None:
    for moisture in (70, 71, 72, 74.9):
        verdict = run(moisture=moisture, previous=STATUS_DRY)
        assert verdict.status == STATUS_DRY, moisture


def test_hysteresis_releases_at_upper_boundary() -> None:
    assert run(moisture=75, previous=STATUS_DRY).status == STATUS_HEALTHY
    assert run(moisture=76, previous=STATUS_DRY).status == STATUS_HEALTHY


def test_hysteresis_does_not_apply_without_previous_dry() -> None:
    assert run(moisture=72, previous=None).status == STATUS_HEALTHY
    assert run(moisture=72, previous=STATUS_HEALTHY).status == STATUS_HEALTHY


def test_hysteresis_survives_outage_because_history_skips_no_data() -> None:
    """``no_data`` must not erase the last informative status."""
    history = next_status_history(
        classify(
            [plant()],
            {"sensor.ficus_moisture": "unavailable"},
            {},
            {"ficus": STATUS_DRY},
            CONFIG,
            NOW,
        ),
        {"ficus": STATUS_DRY},
    )
    assert history["ficus"] == STATUS_DRY

    verdict = run(moisture=72, previous=history["ficus"])
    assert verdict.status == STATUS_DRY


def test_jitter_narrower_than_band_keeps_status_stable() -> None:
    """69 -> 71 -> 69 must never flash healthy."""
    status = run(moisture=69).status
    assert status == STATUS_DRY
    status = run(moisture=71, previous=status).status
    assert status == STATUS_DRY
    status = run(moisture=69, previous=status).status
    assert status == STATUS_DRY


def test_overwatered_is_healthy() -> None:
    assert run(moisture=99).status == STATUS_HEALTHY


def test_per_plant_threshold_override_wins() -> None:
    record = plant(threshold=40)
    assert run(moisture=45, record=record).status == STATUS_HEALTHY
    assert run(moisture=39, record=record).status == STATUS_DRY


def test_battery_fact_display_rules() -> None:
    assert BatteryFact().never_reported is True
    assert BatteryFact().display_value is None
    assert BatteryFact(last_value=0).display_value == 0
    assert BatteryFact(last_value=100).display_value == 100
    assert BatteryFact(last_value=255).display_value is None
    assert BatteryFact(last_value=-1).display_value is None
    assert BatteryFact(last_value=255).never_reported is False


def test_verdict_exposes_previous_status_and_threshold() -> None:
    verdict = run(moisture=71, previous=STATUS_DRY)
    assert verdict.previous_status == STATUS_DRY
    assert verdict.threshold == 70


def test_plant_without_battery_entity_is_never_suspect() -> None:
    record = plant(battery_entity_id=None)
    verdict = classify([record], {record.moisture_entity_id: 10}, {}, {}, CONFIG, NOW)[0]
    assert verdict.status == STATUS_DRY
    assert verdict.battery_never_reported is True


def test_next_status_history_records_and_prunes() -> None:
    verdicts = classify(
        [plant(), plant(plant_id="basil", moisture_entity_id="sensor.basil_moisture")],
        {"sensor.ficus_moisture": 40, "sensor.basil_moisture": "unavailable"},
        {},
        {},
        CONFIG,
        NOW,
    )
    history = next_status_history(verdicts, {"gone": STATUS_DRY})
    assert history["ficus"] == STATUS_DRY
    assert "basil" not in history
    # A vanished plant is pruned by the store layer, not by the pure helper.
    assert history["gone"] == STATUS_DRY


def test_classify_preserves_input_order() -> None:
    records = [
        plant(plant_id="b", moisture_entity_id="sensor.b_moisture"),
        plant(plant_id="a", moisture_entity_id="sensor.a_moisture"),
    ]
    verdicts = classify(records, {}, {}, {}, CONFIG, NOW)
    assert [verdict.plant_id for verdict in verdicts] == ["b", "a"]
