"""Tests for the diagnostics download and its redaction."""

from __future__ import annotations

from custom_components.watering_project.const import (
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_URL,
    SCHEMA_VERSION,
)
from custom_components.watering_project.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant
from tests.helpers import add_entry, add_plant, setup_entry


async def test_diagnostics_structure_and_redaction(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(
        hass,
        {CONF_NOTIFY_SERVICE: "mobile_app_secret_phone", CONF_NOTIFY_URL: "/lovelace/0"},
    )
    plant = add_plant(hass, entry, "ficus", name="Ficus", moisture="42")
    await setup_entry(hass, entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["domain"] == "watering_project"
    assert diagnostics["schema_version"] == SCHEMA_VERSION
    assert diagnostics["counts"]["plants"] == 1
    assert diagnostics["counts"]["needs_water"] == 1

    # Redaction: no raw identifiers, labels, entity ids or notify target.
    blob = str(diagnostics)
    assert "Ficus" not in blob
    assert "sensor.ficus_moisture" not in blob
    assert "mobile_app_secret_phone" not in blob
    assert plant["device_id"] not in blob

    assert diagnostics["options"][CONF_NOTIFY_SERVICE].startswith("sha256:")
    assert diagnostics["options"][CONF_NOTIFY_URL].startswith("sha256:")
    assert diagnostics["plants"][0]["plant_id"].startswith("sha256:")
    assert diagnostics["plants"][0]["status"] == "dry"


async def test_diagnostics_without_plants(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = add_entry(hass)
    await setup_entry(hass, entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["counts"]["plants"] == 0
    assert diagnostics["plants"] == []
