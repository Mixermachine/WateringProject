"""Shared test helpers: fake registry hardware and entry setup."""

from __future__ import annotations

from typing import Any

from custom_components.watering_project.const import DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

MOISTURE_ATTRS = {"device_class": "moisture", "unit_of_measurement": "%"}
BATTERY_ATTRS = {"device_class": "battery", "unit_of_measurement": "%"}
TEMP_ATTRS = {"device_class": "temperature", "unit_of_measurement": "°C"}


def add_entry(hass: HomeAssistant, options: dict[str, Any] | None = None) -> MockConfigEntry:
    """Add a config entry without setting it up."""
    entry = MockConfigEntry(domain=DOMAIN, options=options or {}, entry_id="entry1")
    entry.add_to_hass(hass)
    return entry


def add_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    unique: str,
    name: str | None = "Ficus",
) -> str:
    """Create a device linked to the given config entry."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("zha", unique)},
        name=name,
    )
    return device.id


def add_entity(
    hass: HomeAssistant,
    object_id: str,
    state: str | None,
    attrs: dict[str, Any],
    *,
    device_id: str | None = None,
    friendly_name: str | None = None,
    disabled: bool = False,
) -> str:
    """Create a registry entry plus (optionally) a state object."""
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor",
        "zha",
        object_id,
        suggested_object_id=object_id,
        device_id=device_id,
        disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
    )
    if state is not None:
        attributes = dict(attrs)
        if friendly_name is not None:
            attributes["friendly_name"] = friendly_name
        hass.states.async_set(entry.entity_id, state, attributes)
    return entry.entity_id


def add_area(hass: HomeAssistant, name: str) -> str:
    """Create an area and return its id."""
    return ar.async_get(hass).async_create(name).id


def add_plant(
    hass: HomeAssistant,
    entry: ConfigEntry,
    unique: str,
    *,
    name: str = "Ficus",
    moisture: str = "42",
    battery: str | None = "80",
    temperature: str | None = "21.5",
) -> dict[str, str | None]:
    """Create a full fake plant device with moisture/battery/temperature."""
    device_id = add_device(hass, entry, unique, name)
    moisture_id = add_entity(
        hass, f"{unique}_moisture", moisture, MOISTURE_ATTRS, device_id=device_id
    )
    battery_id = (
        add_entity(hass, f"{unique}_battery", battery, BATTERY_ATTRS, device_id=device_id)
        if battery is not None
        else None
    )
    temperature_id = (
        add_entity(
            hass,
            f"{unique}_temperature",
            temperature,
            TEMP_ATTRS,
            device_id=device_id,
        )
        if temperature is not None
        else None
    )
    return {
        "device_id": device_id,
        "moisture": moisture_id,
        "battery": battery_id,
        "temperature": temperature_id,
    }


async def setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the integration for an existing mock entry."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
