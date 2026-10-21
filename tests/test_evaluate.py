"""Tests for the evaluation pipeline: triggers, coalescing, timer, isolation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from custom_components.watering_project import evaluate as evaluate_module
from custom_components.watering_project.store import WateringStore
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from tests.helpers import add_entry, add_plant, setup_entry

START = dt_util.parse_datetime("2026-01-15T12:00:00+00:00")
assert START is not None


async def test_setup_evaluates_once(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)

    assert entry.runtime_data.coordinator.evaluation_count == 1
    assert (
        entry.runtime_data.coordinator.verdicts[
            f"{next(iter(entry.runtime_data.coordinator.plants))}"
        ].status
        == "dry"
    )


async def test_state_change_triggers_evaluation(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus", moisture="42")
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    before = coordinator.evaluation_count

    hass.states.async_set(
        plant["moisture"], "95", {"device_class": "moisture", "unit_of_measurement": "%"}
    )
    await hass.async_block_till_done()
    # Debounced: advance past the debounce window.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()

    assert coordinator.evaluation_count > before
    assert hass.states.get("sensor.ficus_status").state == "healthy"


async def test_concurrent_evaluations_are_coalesced(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    coordinator.evaluation_count = 0

    # Both calls target a running pipeline: one runs, one is coalesced.
    await coordinator.async_evaluate()
    coordinator._running = True  # simulate in-flight work deterministically
    try:
        await coordinator.async_evaluate()
        assert coordinator._pending is True
    finally:
        coordinator._running = False
        coordinator._pending = False

    assert coordinator.evaluation_count == 1


async def test_timer_flips_battery_suspect_at_boundary(
    hass: HomeAssistant, enable_custom_integrations, freezer
) -> None:
    freezer.move_to(START)
    entry = add_entry(hass, {"battery_suspect_days": 30})
    plant = add_plant(hass, entry, "ficus", moisture="10", battery="0")
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    assert hass.states.get("sensor.ficus_status").state == "dry"

    battery_entity = plant["battery"]
    assert battery_entity is not None
    # Backdate the persisted clock instead of waiting 30 days.
    record = coordinator.battery.records[battery_entity]
    record["zero_since"] = (START - timedelta(days=31)).isoformat()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.ficus_status").state == "suspect_battery"
    assert hass.states.get("binary_sensor.ficus_needs_water").state == "off"


async def test_timer_is_skipped_without_pending_battery_clock(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", moisture="42", battery="80")
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    coordinator.evaluation_count = 0

    # Call the timer trigger directly: registry churn from platform setup may
    # legitimately leave a debounced evaluation pending, which would make this
    # assertion flaky if it went through the event loop.
    await coordinator._async_tick(dt_util.utcnow())
    await hass.async_block_till_done()

    assert coordinator.evaluation_count == 0


async def test_timer_runs_when_a_battery_clock_is_pending(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus", moisture="42", battery="0")
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    assert plant["battery"] in coordinator.battery.records
    coordinator.evaluation_count = 0

    await coordinator._async_tick(dt_util.utcnow())

    assert coordinator.evaluation_count == 1


async def test_hysteresis_survives_setup(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus", moisture="72")
    device_id = plant["device_id"]
    assert device_id is not None

    # A previous run left the plant dry at 68%; 72% is inside the band.
    store = WateringStore(hass, entry.entry_id)
    await store.async_load()
    store.section("verdicts")[device_id] = "dry"
    await store.async_save_now()

    await setup_entry(hass, entry)

    assert hass.states.get("sensor.ficus_status").state == "dry"


async def test_evaluation_failure_marks_no_data_and_keeps_running(
    hass: HomeAssistant, enable_custom_integrations, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", moisture="42")
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator

    def _boom(*args, **kwargs):
        raise RuntimeError("discovery exploded")

    monkeypatch.setattr(evaluate_module, "discover", _boom)
    await coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.ficus_status").state == "no_data"
    assert hass.states.get("binary_sensor.ficus_needs_water").state == "unavailable"

    monkeypatch.undo()
    await coordinator.async_evaluate()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ficus_status").state == "dry"


async def test_unload_cancels_triggers(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    before = coordinator.evaluation_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()
    assert coordinator.evaluation_count == before


async def test_payload_version_increments_only_on_change(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus", moisture="42")
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    version = coordinator.payload_version

    await coordinator.async_evaluate()
    assert coordinator.payload_version == version

    hass.states.async_set(
        plant["moisture"],
        "90",
        {"device_class": "moisture", "unit_of_measurement": "%"},
    )
    await coordinator.async_evaluate()
    assert coordinator.payload_version == version + 1
