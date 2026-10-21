"""Tests for the durable battery observation tracker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.watering_project.battery import BatteryTracker
from custom_components.watering_project.store import WateringStore
from homeassistant.core import HomeAssistant

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
ENTITY = "sensor.ficus_battery"


async def _tracker(
    hass: HomeAssistant, entry_id: str = "test"
) -> tuple[BatteryTracker, WateringStore]:
    store = WateringStore(hass, entry_id)
    await store.async_load()
    return BatteryTracker(store), store


async def test_zero_reading_starts_clock(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)

    result = tracker.observe(ENTITY, "0", NOW)

    assert result.changed is True
    assert result.zero_since == NOW
    assert tracker.facts(ENTITY).zero_since == NOW


async def test_repeated_zero_does_not_move_clock(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)
    tracker.observe(ENTITY, "0", NOW)

    later = NOW + timedelta(hours=6)
    result = tracker.observe(ENTITY, "0", later)

    assert result.zero_since == NOW
    fact = tracker.facts(ENTITY)
    assert fact.zero_since == NOW
    assert fact.last_seen == later


async def test_recovery_clears_clock(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)
    tracker.observe(ENTITY, "0", NOW)

    result = tracker.observe(ENTITY, "55", NOW + timedelta(days=3))

    assert result.zero_since is None
    assert tracker.facts(ENTITY).zero_since is None


async def test_one_percent_counts_as_zero(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)
    assert tracker.observe(ENTITY, "1", NOW).zero_since == NOW
    assert tracker.observe("sensor.other_battery", "1.4", NOW).zero_since is None


async def test_out_of_range_keeps_clock_and_is_unknown_for_display(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)
    tracker.observe(ENTITY, "0", NOW)

    result = tracker.observe(ENTITY, "255", NOW + timedelta(days=1))

    fact = tracker.facts(ENTITY)
    assert fact.zero_since == NOW
    assert fact.last_value == 255
    assert fact.display_value is None
    assert result.zero_since == NOW


async def test_unavailable_is_neither_recovery_nor_seen(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)
    tracker.observe(ENTITY, "0", NOW)

    result = tracker.observe(ENTITY, "unavailable", NOW + timedelta(days=10))

    fact = tracker.facts(ENTITY)
    assert result.changed is False
    assert fact.zero_since == NOW
    # last_seen still reflects the last numeric reading (pruning stays honest)
    assert fact.last_seen == NOW


async def test_non_numeric_for_unknown_entity_creates_no_record(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)

    assert tracker.observe("sensor.ghost", "unknown", NOW).changed is False
    assert "sensor.ghost" not in tracker.records


async def test_never_reported_flag(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)
    tracker.observe(ENTITY, "unknown", NOW)
    assert tracker.facts(ENTITY) is None

    tracker.observe(ENTITY, "42", NOW)
    assert tracker.facts(ENTITY).never_reported is False


async def test_clock_survives_reload(hass: HomeAssistant) -> None:
    tracker, store = await _tracker(hass)
    tracker.observe(ENTITY, "0", NOW)
    await store.async_save_now()

    reloaded = WateringStore(hass, "test")
    await reloaded.async_load()
    fact = BatteryTracker(reloaded).facts(ENTITY)

    assert fact is not None
    assert fact.zero_since == NOW


async def test_prune_drops_only_stale_records(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)
    tracker.observe("sensor.old", "0", NOW - timedelta(days=100))
    tracker.observe("sensor.fresh", "50", NOW - timedelta(days=2))

    changed = tracker.prune(NOW)

    assert changed is True
    assert "sensor.old" not in tracker.records
    assert "sensor.fresh" in tracker.records


async def test_apply_observations_batches_and_prunes(hass: HomeAssistant) -> None:
    tracker, _ = await _tracker(hass)

    changed = tracker.apply_observations(
        {"sensor.a": "0", "sensor.b": "unknown"}, NOW, tracked_entity_ids=["sensor.a", "sensor.b"]
    )

    assert changed is True
    assert tracker.facts("sensor.a").zero_since == NOW
    assert tracker.facts("sensor.b") is None
