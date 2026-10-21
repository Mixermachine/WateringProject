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
