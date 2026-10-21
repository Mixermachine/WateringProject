"""Tests for discovery: the single authority for "which devices are plants"."""

from __future__ import annotations

from custom_components.watering_project.const import (
    EXCLUDE_REASON_NOT_INCLUDED,
    EXCLUDE_REASON_OPTION,
)
from custom_components.watering_project.discovery import discover
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

MOISTURE_ATTRS = {"device_class": "moisture", "unit_of_measurement": "%"}
BATTERY_ATTRS = {"device_class": "battery", "unit_of_measurement": "%"}
TEMP_ATTRS = {"device_class": "temperature", "unit_of_measurement": "°C"}


def ensure_config_entry(hass: HomeAssistant) -> str:
    """Register a config entry (once per test) so devices can be linked to it."""
    for existing in hass.config_entries.async_entries("watering_project"):
        return existing.entry_id
    entry = MockConfigEntry(domain="watering_project", entry_id="test_entry")
    entry.add_to_hass(hass)
    return entry.entry_id


def add_device(hass: HomeAssistant, unique: str, name: str | None = "Ficus") -> str:
    entry = dr.async_get(hass).async_get_or_create(
        config_entry_id=ensure_config_entry(hass),
        identifiers={("zha", unique)},
        name=name,
    )
    return entry.id


def add_entity(
    hass: HomeAssistant,
    object_id: str,
    state: str | None,
    attrs: dict[str, object],
    *,
    device_id: str | None = None,
    unique: str | None = None,
    area_id: str | None = None,
    disabled: bool = False,
    friendly_name: str | None = None,
) -> str:
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor",
        "zha",
        unique or object_id,
        suggested_object_id=object_id,
        device_id=device_id,
        disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
    )
    if area_id is not None:
        registry.async_update_entity(entry.entity_id, area_id=area_id)
        entry = registry.async_get(entry.entity_id) or entry
    if state is not None:
        attributes = dict(attrs)
        if friendly_name is not None:
            attributes["friendly_name"] = friendly_name
        hass.states.async_set(entry.entity_id, state, attributes)
    return entry.entity_id


def add_area(hass: HomeAssistant, name: str) -> str:
    return ar.async_get(hass).async_create(name).id


async def test_discovers_plant_with_siblings_and_area(hass: HomeAssistant) -> None:
    area_id = add_area(hass, "Kitchen")
    device_id = add_device(hass, "ficus", "Ficus")
    dr.async_get(hass).async_update_device(device_id, area_id=area_id)
    moisture = add_entity(hass, "ficus_moisture", "42", MOISTURE_ATTRS, device_id=device_id)
    battery = add_entity(hass, "ficus_battery", "80", BATTERY_ATTRS, device_id=device_id)
    temperature = add_entity(hass, "ficus_temperature", "21.5", TEMP_ATTRS, device_id=device_id)

    result = discover(hass)

    assert len(result.plants) == 1
    plant = result.plants[0]
    assert plant.plant_id == device_id
    assert plant.label == "Ficus"
    assert plant.moisture_entity_id == moisture
    assert plant.battery_entity_id == battery
    assert plant.temperature_entity_id == temperature
    assert plant.area_id == area_id
    assert plant.area_name == "Kitchen"


async def test_device_name_by_user_takes_precedence(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "ficus", "Device Name")
    dr.async_get(hass).async_update_device(device_id, name_by_user="Living room fig")
    add_entity(hass, "ficus_moisture", "42", MOISTURE_ATTRS, device_id=device_id)

    assert discover(hass).plants[0].label == "Living room fig"


async def test_device_without_name_falls_back_to_friendly_name(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "nameless", None)
    # DeviceRegistry seeds an unnamed device with the config entry title; clear it
    # so the friendly-name fallback is actually exercised.
    dr.async_get(hass).async_update_device(device_id, name=None)
    add_entity(
        hass,
        "nameless_moisture",
        "42",
        MOISTURE_ATTRS,
        device_id=device_id,
        friendly_name="Basil soil",
    )

    assert discover(hass).plants[0].label == "Basil soil"


async def test_entity_area_overrides_device_area(hass: HomeAssistant) -> None:
    device_area = add_area(hass, "Kitchen")
    entity_area = add_area(hass, "Bedroom")
    device_id = add_device(hass, "ficus", "Ficus")
    dr.async_get(hass).async_update_device(device_id, area_id=device_area)
    add_entity(
        hass, "ficus_moisture", "42", MOISTURE_ATTRS, device_id=device_id, area_id=entity_area
    )

    plant = discover(hass).plants[0]
    assert plant.area_id == entity_area
    assert plant.area_name == "Bedroom"


async def test_non_percent_moisture_is_ignored(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "raw", "Raw sensor")
    add_entity(
        hass,
        "raw_moisture",
        "0.42",
        {"device_class": "moisture", "unit_of_measurement": "raw"},
        device_id=device_id,
    )

    result = discover(hass)

    assert result.plants == ()
    assert result.excluded == ()


async def test_entity_without_state_is_ignored(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "stateless", "Stateless")
    add_entity(hass, "stateless_moisture", None, MOISTURE_ATTRS, device_id=device_id)

    assert discover(hass).plants == ()


async def test_disabled_moisture_is_ignored(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "disabled", "Disabled")
    add_entity(hass, "disabled_moisture", "42", MOISTURE_ATTRS, device_id=device_id, disabled=True)

    assert discover(hass).plants == ()


async def test_disabled_battery_is_not_selected(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "ficus", "Ficus")
    add_entity(hass, "ficus_moisture", "42", MOISTURE_ATTRS, device_id=device_id)
    add_entity(hass, "ficus_battery", "80", BATTERY_ATTRS, device_id=device_id, disabled=True)

    plant = discover(hass).plants[0]
    assert plant.battery_entity_id is None


async def test_lowest_entity_id_wins_with_multiple_moisture_sensors(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "multi", "Multi")
    add_entity(hass, "multi_moisture_b", "42", MOISTURE_ATTRS, device_id=device_id, unique="mb")
    add_entity(hass, "multi_moisture_a", "42", MOISTURE_ATTRS, device_id=device_id, unique="ma")

    plant = discover(hass).plants[0]
    assert plant.moisture_entity_id == "sensor.multi_moisture_a"


async def test_temperature_any_unit_is_accepted(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "ficus", "Ficus")
    add_entity(hass, "ficus_moisture", "42", MOISTURE_ATTRS, device_id=device_id)
    add_entity(
        hass,
        "ficus_temperature",
        "70.4",
        {"device_class": "temperature", "unit_of_measurement": "°F"},
        device_id=device_id,
    )

    assert discover(hass).plants[0].temperature_entity_id == "sensor.ficus_temperature"


async def test_device_less_entity_becomes_its_own_plant(hass: HomeAssistant) -> None:
    area_id = add_area(hass, "Bath")
    entity_id = add_entity(
        hass,
        "template_moisture",
        "42",
        MOISTURE_ATTRS,
        area_id=area_id,
        friendly_name="Template soil",
    )

    plant = discover(hass).plants[0]
    assert plant.plant_id == entity_id
    assert plant.label == "Template soil"
    assert plant.area_name == "Bath"


async def test_exclude_wins_over_include(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "ficus", "Ficus")
    add_entity(hass, "ficus_moisture", "42", MOISTURE_ATTRS, device_id=device_id)

    result = discover(hass, include_devices=[device_id], exclude_devices=[device_id])

    assert result.plants == ()
    assert result.excluded[0].reason == EXCLUDE_REASON_OPTION


async def test_include_list_restricts_discovery(hass: HomeAssistant) -> None:
    wanted = add_device(hass, "wanted", "Wanted")
    other = add_device(hass, "other", "Other")
    add_entity(hass, "wanted_moisture", "42", MOISTURE_ATTRS, device_id=wanted)
    add_entity(hass, "other_moisture", "42", MOISTURE_ATTRS, device_id=other)

    result = discover(hass, include_devices=[wanted])

    assert [plant.plant_id for plant in result.plants] == [wanted]
    assert result.excluded[0].reason == EXCLUDE_REASON_NOT_INCLUDED


async def test_keyword_auto_exclusion(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "leak", "Basement leak sensor")
    add_entity(hass, "leak_moisture", "42", MOISTURE_ATTRS, device_id=device_id)

    result = discover(hass)

    assert result.plants == ()
    assert result.excluded[0].reason == "keyword:leak"


async def test_explicit_include_overrides_keyword_exclusion(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "leak", "Basement leak sensor")
    add_entity(hass, "leak_moisture", "42", MOISTURE_ATTRS, device_id=device_id)

    result = discover(hass, include_devices=[device_id])

    assert [plant.plant_id for plant in result.plants] == [device_id]
    assert result.excluded == ()


async def test_keyword_matching_is_case_insensitive_and_umlaut_aware(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "w", "Wasser-Alarm Keller")
    add_entity(hass, "w_moisture", "42", MOISTURE_ATTRS, device_id=device_id)

    assert discover(hass).excluded[0].reason == "keyword:wasser"


async def test_plant_without_battery_or_temperature(hass: HomeAssistant) -> None:
    device_id = add_device(hass, "plain", "Plain")
    add_entity(hass, "plain_moisture", "42", MOISTURE_ATTRS, device_id=device_id)

    plant = discover(hass).plants[0]
    assert plant.battery_entity_id is None
    assert plant.temperature_entity_id is None


async def test_results_are_sorted_for_determinism(hass: HomeAssistant) -> None:
    first = add_device(hass, "b", "Bravo")
    second = add_device(hass, "a", "Alpha")
    add_entity(hass, "b_moisture", "42", MOISTURE_ATTRS, device_id=first, unique="b")
    add_entity(hass, "a_moisture", "42", MOISTURE_ATTRS, device_id=second, unique="a")

    ids = [plant.plant_id for plant in discover(hass).plants]
    assert ids == sorted([first, second])
