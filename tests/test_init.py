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
