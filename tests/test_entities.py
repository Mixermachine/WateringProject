"""Tests for entity creation, values and lifecycle."""

from __future__ import annotations

from custom_components.watering_project.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from tests.helpers import (
    BATTERY_ATTRS,
    MOISTURE_ATTRS,
    add_entity,
    add_entry,
    add_plant,
    setup_entry,
)


async def test_dry_plant_entities(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus", moisture="42")
    await setup_entry(hass, entry)

    needs_water = hass.states.get("binary_sensor.ficus_needs_water")
    status = hass.states.get("sensor.ficus_status")

    assert needs_water is not None
    assert needs_water.state == "on"
    assert status is not None
    assert status.state == "dry"
    assert plant["device_id"] in {device.id for device in dr.async_get(hass).devices.values()}


async def test_healthy_plant_entities(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", moisture="90")
    await setup_entry(hass, entry)

    assert hass.states.get("binary_sensor.ficus_needs_water").state == "off"
    assert hass.states.get("sensor.ficus_status").state == "healthy"


async def test_aggregates(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", name="Ficus", moisture="42")
    add_plant(hass, entry, "basil", name="Basil", moisture="20")
    add_plant(hass, entry, "cactus", name="Cactus", moisture="90")
    await setup_entry(hass, entry)

    assert hass.states.get("sensor.watering_project_plants_needing_water").state == "2"
    assert hass.states.get("binary_sensor.watering_project_plants_need_water").state == "on"


async def test_no_data_does_not_read_as_not_thirsty(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", moisture="unavailable")
    await setup_entry(hass, entry)

    needs_water = hass.states.get("binary_sensor.ficus_needs_water")
    status = hass.states.get("sensor.ficus_status")

    assert status.state == "no_data"
    assert needs_water.state == "unavailable"


async def test_suspect_battery_plant(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass, {"battery_suspect_days": 1})
    plant = add_plant(hass, entry, "ficus", moisture="10", battery="0")
    await setup_entry(hass, entry)

    # First evaluation starts the clock; it cannot be suspect yet.
    assert hass.states.get("sensor.ficus_status").state == "dry"

    assert plant["battery"] is not None


async def test_entities_appear_for_newly_discovered_plant(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)
    assert hass.states.get("sensor.ficus_status") is not None

    add_plant(hass, entry, "basil", name="Basil", moisture="90")
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.basil_status") is not None


async def test_entities_removed_when_device_disappears(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)
    assert hass.states.get("sensor.ficus_status") is not None

    device_id = plant["device_id"]
    assert device_id is not None
    dr.async_get(hass).async_remove_device(device_id)
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.ficus_status") is None
    assert hass.states.get("binary_sensor.ficus_needs_water") is None


async def test_entity_unique_ids_are_entry_scoped(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    status = registry.async_get("sensor.ficus_status")
    assert status is not None
    assert status.unique_id == f"{DOMAIN}_{entry.entry_id}_{plant['device_id']}_status"


async def test_entity_ids_do_not_follow_device_rename(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """Documented limitation: entity ids are fixed at creation time."""
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus", name="Ficus")
    await setup_entry(hass, entry)
    device_id = plant["device_id"]
    assert device_id is not None

    dr.async_get(hass).async_update_device(device_id, name_by_user="Living room fig")
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.ficus_status") is not None


async def test_unknown_temperature_is_a_badge_not_a_section(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", moisture="90", temperature=None)
    add_entity(
        hass,
        "ficus_orphan_temperature",
        "unknown",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    await setup_entry(hass, entry)

    assert hass.states.get("sensor.ficus_status").state == "healthy"


async def test_disabled_moisture_does_not_create_entities(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus")
    from homeassistant.helpers import entity_registry as er

    moisture_id = plant["moisture"]
    assert moisture_id is not None
    er.async_get(hass).async_update_entity(moisture_id, disabled_by=er.RegistryEntryDisabler.USER)
    await setup_entry(hass, entry)

    assert hass.states.get("sensor.watering_project_plants_needing_water").state == "0"


async def test_battery_entity_selection(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    plant = add_plant(hass, entry, "ficus")
    device_id = plant["device_id"]
    assert device_id is not None
    add_entity(
        hass,
        "ficus_second_battery",
        "42",
        BATTERY_ATTRS,
        device_id=device_id,
    )
    add_entity(hass, "ficus_extra_moisture", "10", MOISTURE_ATTRS, device_id=device_id)
    await setup_entry(hass, entry)

    # Lowest entity id wins deterministically: ficus_moisture < ficus_second...
    assert hass.states.get("sensor.ficus_status").state == "dry"
