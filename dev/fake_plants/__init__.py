"""Dev-only fake hardware for the Watering Project.

Not published: this integration exists so the card and the end-to-end suite have
plants to look at without Zigbee radios. It creates *real* registry entries —
devices, areas, entity registry rows and state objects with proper
``device_class`` attributes — because the Watering Project discovers plants
through the registries and deliberately does not filter on ``platform``.

This is a real integration with its own config entry, because the device
registry requires one; it is mounted into ``custom_components/fake_plants`` by
``docker-compose`` and added through the normal UI flow (or a test entry).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

DOMAIN = "fake_plants"
PLATFORM = "fake_plants"

SERVICE_SET_VALUE = "set_value"
SERVICE_SET_MOISTURE = "set_moisture"
SERVICE_SET_BATTERY = "set_battery"
SERVICE_AGE_BATTERY = "age_battery"
SERVICE_RESET_NOTIFICATIONS = "reset_notifications"

LAST_NOTIFICATION_ENTITY = "sensor.fake_last_notification"
NOTIFICATION_COUNT_ENTITY = "sensor.fake_notification_count"
NOTIFY_SERVICE = "fake_phone"

MOISTURE_ATTRS: dict[str, Any] = {"device_class": "moisture", "unit_of_measurement": "%"}
BATTERY_ATTRS: dict[str, Any] = {"device_class": "battery", "unit_of_measurement": "%"}
TEMPERATURE_ATTRS: dict[str, Any] = {
    "device_class": "temperature",
    "unit_of_measurement": "°C",
}

# The fixture set covers every status the card can render:
#   Ficus      dry, healthy-looking battery
#   Orchid     dry (65 %), second room (ordering)
#   Monstera   low moisture with a flat battery (suspect once zero_since ages)
#   Basil      moisture entity present but unavailable (no_data)
#   Cactus     healthy, no area (Unassigned must sort last)
#   Basement   leak-looking name, expected to be auto-excluded by keyword
PLANTS: tuple[dict[str, Any], ...] = (
    {
        "unique": "ficus",
        "name": "Ficus",
        "area": "Kitchen",
        "moisture": "42",
        "battery": "80",
        "temperature": "21.5",
    },
    {
        "unique": "orchid",
        "name": "Orchid",
        "area": "Bedroom",
        "moisture": "65",
        "battery": "55",
        "temperature": "19.0",
    },
    {
        "unique": "monstera",
        "name": "Monstera",
        "area": "Kitchen",
        "moisture": "12.5",
        "battery": "0",
        "temperature": None,
    },
    {
        "unique": "basil",
        "name": "Basil",
        "area": "Bedroom",
        "moisture": None,
        "battery": "64",
        "temperature": "20.0",
    },
    {
        "unique": "cactus",
        "name": "Cactus",
        "area": None,
        "moisture": "91",
        "battery": "40",
        "temperature": None,
    },
    {
        "unique": "leak_sensor",
        "name": "Basement leak sensor",
        "area": "Basement",
        "moisture": "10",
        "battery": "90",
        "temperature": None,
    },
)

SET_VALUE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): str,
        vol.Required("value"): vol.Coerce(str),
    }
)

AGE_BATTERY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): str,
        vol.Required("days"): vol.Coerce(float),
    }
)


def _entity_attributes(unique: str) -> dict[str, Any]:
    if unique.endswith("_battery"):
        return BATTERY_ATTRS
    if unique.endswith("_temperature"):
        return TEMPERATURE_ATTRS
    return MOISTURE_ATTRS


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Nothing to do without a config entry."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create the fake hardware and register the notifier."""
    hass.data.setdefault(DOMAIN, {})
    state = hass.data[DOMAIN]
    state["entry_id"] = entry.entry_id

    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    entity_ids: dict[str, str] = {}

    for spec in PLANTS:
        unique: str = spec["unique"]
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(PLATFORM, unique)},
            name=spec["name"],
            # Creates the area on first use and leaves it alone afterwards.
            suggested_area=spec["area"],
        )

        for suffix, key in (
            ("_moisture", "moisture"),
            ("_battery", "battery"),
            ("_temperature", "temperature"),
        ):
            value: str | None = spec[key]
            if value is None and key != "moisture":
                # No entity at all: a plant without a temperature sensor.
                continue
            registry_entry = entities.async_get_or_create(
                "sensor",
                PLATFORM,
                f"{unique}{suffix}",
                suggested_object_id=f"{unique}{suffix}",
                device_id=device.id,
            )
            entity_ids[f"{unique}{suffix}"] = registry_entry.entity_id
            hass.states.async_set(
                registry_entry.entity_id,
                STATE_UNAVAILABLE if value is None else value,
                _entity_attributes(f"{unique}{suffix}"),
            )

    state["entity_ids"] = entity_ids
    state.setdefault("notifications", [])
    hass.states.async_set(
        NOTIFICATION_COUNT_ENTITY, "0", {"friendly_name": "Fake notification count"}
    )

    async def _set_value(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        hass.states.async_set(entity_id, call.data["value"], _entity_attributes(entity_id))

    async def _set_moisture(call: ServiceCall) -> None:
        await _set_value(call)

    async def _set_battery(call: ServiceCall) -> None:
        await _set_value(call)

    hass.services.async_register(DOMAIN, SERVICE_SET_VALUE, _set_value, SET_VALUE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_MOISTURE, _set_moisture, SET_VALUE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_BATTERY, _set_battery, SET_VALUE_SCHEMA)

    async def _age_battery(call: ServiceCall) -> None:
        """Backdate a battery's zero clock on the Watering Project store.

        A live container cannot wait 31 days, and a pre-seeded `.storage` file
        would have to know the config entry id in advance. This dev-only shortcut
        writes the same field the tracker would have written.
        """
        entity_id: str = call.data["entity_id"]
        zero_since = (dt_util.utcnow() - timedelta(days=call.data["days"])).isoformat()
        for entry in hass.config_entries.async_entries("watering_project"):
            runtime = getattr(entry, "runtime_data", None)
            coordinator = getattr(runtime, "coordinator", None)
            if coordinator is None or entity_id not in coordinator.battery.records:
                continue
            coordinator.battery.records[entity_id]["zero_since"] = zero_since
            await coordinator.async_evaluate()
            return
        _LOGGER.warning("age_battery: %s is not tracked yet", entity_id)

    hass.services.async_register(DOMAIN, SERVICE_AGE_BATTERY, _age_battery, AGE_BATTERY_SCHEMA)

    async def _reset_notifications(_call: ServiceCall) -> None:
        state["notifications"].clear()
        hass.states.async_set(
            NOTIFICATION_COUNT_ENTITY, "0", {"friendly_name": "Fake notification count"}
        )
        hass.states.async_set(
            LAST_NOTIFICATION_ENTITY, "", {"friendly_name": "Fake last notification"}
        )

    hass.services.async_register(DOMAIN, SERVICE_RESET_NOTIFICATIONS, _reset_notifications)

    async def _fake_phone(call: ServiceCall) -> None:
        record = dict(call.data)
        state["notifications"].append(record)
        hass.states.async_set(
            NOTIFICATION_COUNT_ENTITY,
            str(len(state["notifications"])),
            {"friendly_name": "Fake notification count"},
        )
        hass.states.async_set(
            LAST_NOTIFICATION_ENTITY,
            record.get("message", ""),
            {
                "title": record.get("title", ""),
                "data": record.get("data", {}),
                "friendly_name": "Fake last notification",
            },
        )
        _LOGGER.debug("fake_phone received %s", record)

    # A plain service registration is enough: the integration only checks
    # ``hass.services.has_service("notify", service)`` and calls it.
    if not hass.services.has_service("notify", NOTIFY_SERVICE):
        hass.services.async_register("notify", NOTIFY_SERVICE, _fake_phone)

    _LOGGER.info("fake_plants created %s plants", len(PLANTS))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to unload: the fake hardware is meant to stay put."""
    return True
