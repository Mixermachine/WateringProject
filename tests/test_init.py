"""Tests for the supported-version gate."""

from __future__ import annotations

import pytest
from custom_components.watering_project import async_setup_entry
from custom_components.watering_project.const import MIN_HOMEASSISTANT_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from tests.helpers import add_entry, add_plant


def test_supported_version_accepts_floor() -> None:
    from custom_components.watering_project import homeassistant_version_supported

    assert homeassistant_version_supported(MIN_HOMEASSISTANT_VERSION) is True
    assert homeassistant_version_supported("2099.1.0") is True


def test_supported_version_rejects_older() -> None:
    from custom_components.watering_project import homeassistant_version_supported

    assert homeassistant_version_supported("2026.9.4") is False
    assert homeassistant_version_supported("2025.2.5") is False


def test_supported_version_handles_garbage() -> None:
    from custom_components.watering_project import homeassistant_version_supported

    assert homeassistant_version_supported("not-a-version") is False


async def test_setup_refuses_older_home_assistant(
    hass: HomeAssistant, enable_custom_integrations, monkeypatch: pytest.MonkeyPatch
) -> None:
    import custom_components.watering_project as integration

    monkeypatch.setattr(integration, "HA_VERSION", "2026.9.0")
    entry = add_entry(hass)
    add_plant(hass, entry, "ficus")

    with pytest.raises(ConfigEntryError, match="requires Home Assistant"):
        await async_setup_entry(hass, entry)


async def test_card_bundle_is_served(
    hass: HomeAssistant, enable_custom_integrations, hass_client
) -> None:
    """The built card must be reachable at the URL the README tells users to add."""
    from custom_components.watering_project.const import DOMAIN

    entry = add_entry(hass)
    add_plant(hass, entry, "ficus")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()
    response = await client.get(f"/{DOMAIN}/watering-project-card.js")

    assert response.status == 200
    assert "watering-project-card" in await response.text()
    # Cache-busting is the user's job; the server must not pin the bundle.
    assert "max-age=2678400" not in response.headers.get("cache-control", "")


async def test_sidebar_panel_is_registered_and_removed(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """Adding the integration must create the sidebar tab; removing it must clean up.

    The card has no Lovelace resource and no dashboard: a custom panel is the only
    registration, and Home Assistant waits for its module before mounting it.
    """
    from custom_components.watering_project.const import (
        PANEL_ELEMENT,
        PANEL_ICON,
        PANEL_TITLE,
        PANEL_URL_PATH,
        VERSION,
    )
    from homeassistant.components import frontend

    entry = add_entry(hass)
    add_plant(hass, entry, "ficus")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    panel = hass.data[frontend.DATA_PANELS][PANEL_URL_PATH]
    assert panel.sidebar_title == PANEL_TITLE
    assert panel.sidebar_icon == PANEL_ICON
    assert panel.require_admin is False
    custom = panel.config["_panel_custom"]
    assert custom["name"] == PANEL_ELEMENT
    assert custom["module_url"] == (f"/watering_project/watering-project-card.js?v={VERSION}")

    # A reload must not raise "panel already registered" or drop the tab.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert PANEL_URL_PATH in hass.data[frontend.DATA_PANELS]

    # The tab actively survives an unload: the card shows `not_loaded`, and a
    # remove/re-add cycle would make the frontend bounce to the default dashboard.
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert PANEL_URL_PATH in hass.data[frontend.DATA_PANELS]

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert PANEL_URL_PATH not in hass.data[frontend.DATA_PANELS]


def test_yaml_configuration_is_refused(caplog: pytest.LogCaptureFixture) -> None:
    """The integration is config-entry only; a YAML block must be dropped loudly."""
    from custom_components.watering_project import CONFIG_SCHEMA
    from custom_components.watering_project.const import DOMAIN

    # `config_entry_only_config_schema` logs an error instead of raising, so the
    # log line is the contract that matters: the user gets told to remove the block.
    CONFIG_SCHEMA({DOMAIN: {"notify_service": "x"}})
    assert "does not support YAML setup" in caplog.text

    assert CONFIG_SCHEMA({}) == {}
