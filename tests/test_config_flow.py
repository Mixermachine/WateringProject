"""Tests for the config flow and the options flow."""

from __future__ import annotations

from typing import Any

from custom_components.watering_project.const import (
    CONF_BATTERY_SUSPECT_DAYS,
    CONF_INCLUDE_DEVICES,
    CONF_MOISTURE_DEFAULT,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_SERVICE,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from tests.helpers import add_device, add_entry, add_plant


async def test_user_flow_creates_single_entry(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Watering Project"
    assert result["data"] == {}


async def test_user_flow_aborts_when_configured(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    add_entry(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def _option_defaults(result: dict[str, Any]) -> dict[str, Any]:
    schema = result["data_schema"]
    assert schema is not None
    return {
        str(key): key.default() if callable(key.default) else key.default
        for key in schema.schema
        if getattr(key, "default", None) is not None
    }


async def test_options_flow_shows_defaults(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    defaults = _option_defaults(result)
    assert defaults[CONF_MOISTURE_DEFAULT] == 70
    assert defaults[CONF_BATTERY_SUSPECT_DAYS] == 30
    assert defaults[CONF_NOTIFY_ENABLED] is False


async def test_options_flow_saves_values(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    device_id = add_device(hass, entry, "ficus")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_MOISTURE_DEFAULT: 60,
            CONF_BATTERY_SUSPECT_DAYS: 14,
            CONF_INCLUDE_DEVICES: [device_id],
            CONF_NOTIFY_ENABLED: False,
            CONF_NOTIFY_SERVICE: "",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_MOISTURE_DEFAULT] == 60
    assert entry.options[CONF_BATTERY_SUSPECT_DAYS] == 14
    assert entry.options[CONF_INCLUDE_DEVICES] == [device_id]


async def test_options_flow_requires_service_when_notifications_enabled(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    await setup_entry_for_entry(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_MOISTURE_DEFAULT: 70,
            CONF_BATTERY_SUSPECT_DAYS: 30,
            CONF_NOTIFY_ENABLED: True,
            CONF_NOTIFY_SERVICE: "",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NOTIFY_SERVICE: "notify_service_required"}


async def test_options_flow_rejects_unknown_service(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    await setup_entry_for_entry(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_MOISTURE_DEFAULT: 70,
            CONF_BATTERY_SUSPECT_DAYS: 30,
            CONF_NOTIFY_ENABLED: True,
            CONF_NOTIFY_SERVICE: "mobile_app_missing",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NOTIFY_SERVICE: "notify_service_not_found"}


async def test_options_flow_normalises_notify_prefix(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    await setup_entry_for_entry(hass, entry)
    hass.services.async_register("notify", "mobile_app_test", lambda call: None)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_MOISTURE_DEFAULT: 70,
            CONF_BATTERY_SUSPECT_DAYS: 30,
            CONF_NOTIFY_ENABLED: True,
            CONF_NOTIFY_SERVICE: "notify.mobile_app_test",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_NOTIFY_SERVICE] == "mobile_app_test"


async def test_options_update_reloads_entry(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus", moisture="42")
    await setup_entry_for_entry(hass, entry)
    assert hass.states.get("sensor.ficus_status").state == "dry"

    hass.config_entries.async_update_entry(entry, options={CONF_MOISTURE_DEFAULT: 30})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.ficus_status").state == "healthy"


async def setup_entry_for_entry(hass: HomeAssistant, entry) -> None:
    """Small alias so tests read clearly."""
    from tests.helpers import setup_entry as _setup

    await _setup(hass, entry)
