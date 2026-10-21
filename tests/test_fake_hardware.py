"""End-to-end-in-process test with the dev fake hardware.

No Zigbee, no phone, no browser: `dev/fake_plants` creates real registry entries,
the integration discovers them, decides verdicts, and calls `notify.fake_phone`.
This is the closest thing to M4 that can run in the single pytest leg, and it is
the regression net for "does discovery see fake hardware at all".
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path
from types import ModuleType

import pytest
from custom_components.watering_project.const import (
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_SERVICE,
    DOMAIN,
)
from custom_components.watering_project.notifications import ISSUE_BATTERY_SUSPECT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests.helpers import add_entry, setup_entry

DEV_DIR = Path(__file__).resolve().parent.parent / "dev"


def load_fake_plants() -> ModuleType:
    """Import the dev integration from `dev/` without installing it."""
    if "fake_plants" in sys.modules:
        return sys.modules["fake_plants"]

    spec = importlib.util.spec_from_file_location(
        "fake_plants", DEV_DIR / "fake_plants" / "__init__.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fake_plants"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def fake_setup(hass: HomeAssistant, enable_custom_integrations) -> ModuleType:
    """Start the fake hardware and the real integration on the same instance."""
    fake = load_fake_plants()
    # Call the entry hook directly: the dev integration lives in `dev/`, not in
    # `custom_components/`, so Home Assistant's loader cannot resolve it here.
    # The loader path is what the docker-compose e2e run exercises.
    fake_entry = MockConfigEntry(domain="fake_plants", title="Fake Plants")
    fake_entry.add_to_hass(hass)
    assert await fake.async_setup_entry(hass, fake_entry)
    await hass.async_block_till_done()
    assert hass.services.has_service("notify", fake.NOTIFY_SERVICE)

    entry = add_entry(hass, {CONF_NOTIFY_ENABLED: True, CONF_NOTIFY_SERVICE: "fake_phone"})
    await setup_entry(hass, entry)
    await hass.async_block_till_done()
    return fake


def _coordinator(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data.coordinator


def _statuses(hass: HomeAssistant) -> dict[str, str]:
    coordinator = _coordinator(hass)
    return {
        plant.label: verdict.status
        for plant_id, verdict in coordinator.verdicts.items()
        if (plant := coordinator.plants.get(plant_id)) is not None
    }


async def test_fake_hardware_is_discovered_with_verdicts(
    hass: HomeAssistant, fake_setup: ModuleType
) -> None:
    assert _statuses(hass) == {
        "Ficus": "dry",
        "Orchid": "dry",
        "Monstera": "dry",
        "Basil": "no_data",
        "Cactus": "healthy",
    }


async def test_leak_looking_device_is_auto_excluded(
    hass: HomeAssistant, fake_setup: ModuleType
) -> None:
    excluded = {item.label: item.reason for item in _coordinator(hass).excluded}

    assert excluded["Basement leak sensor"].startswith("keyword:")
    assert "Basement leak sensor" not in _statuses(hass)


async def test_fake_phone_receives_one_notification(
    hass: HomeAssistant, fake_setup: ModuleType
) -> None:
    notifications = hass.data["fake_plants"]["notifications"]

    assert len(notifications) == 1
    assert notifications[0]["title"] == "Plants need water"
    assert "Ficus" in notifications[0]["message"]
    assert hass.states.get("sensor.fake_last_notification").state.startswith("3 plants need water")


async def test_live_service_call_moves_a_plant(hass: HomeAssistant, fake_setup: ModuleType) -> None:
    await hass.services.async_call(
        "fake_plants",
        "set_moisture",
        {"entity_id": "sensor.ficus_moisture", "value": "95"},
        blocking=True,
    )
    await _coordinator(hass).async_evaluate()

    assert _statuses(hass)["Ficus"] == "healthy"


async def test_second_dry_plant_inside_window_does_not_renotify(
    hass: HomeAssistant, fake_setup: ModuleType
) -> None:
    notifications = hass.data["fake_plants"]["notifications"]
    assert len(notifications) == 1

    await hass.services.async_call(
        "fake_plants",
        "set_moisture",
        {"entity_id": "sensor.cactus_moisture", "value": "20"},
        blocking=True,
    )
    await _coordinator(hass).async_evaluate()
    await hass.async_block_till_done()

    assert _statuses(hass)["Cactus"] == "dry"
    assert len(notifications) == 1


async def test_aged_flat_battery_becomes_suspect_and_raises_issue(
    hass: HomeAssistant, fake_setup: ModuleType
) -> None:
    coordinator = _coordinator(hass)
    record = coordinator.battery.records["sensor.monstera_battery"]
    assert record["last_value"] == 0

    record["zero_since"] = (dt_util.utcnow() - timedelta(days=31)).isoformat()
    await coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert _statuses(hass)["Monstera"] == "suspect_battery"
    issue = ir.async_get(hass).issues.get((DOMAIN, ISSUE_BATTERY_SUSPECT))
    assert issue is not None
    assert "Monstera" in issue.translation_placeholders["plants"]


async def test_unavailable_moisture_reports_no_data(
    hass: HomeAssistant, fake_setup: ModuleType
) -> None:
    assert _statuses(hass)["Basil"] == "no_data"

    await hass.services.async_call(
        "fake_plants",
        "set_moisture",
        {"entity_id": "sensor.basil_moisture", "value": "50"},
        blocking=True,
    )
    await _coordinator(hass).async_evaluate()

    assert _statuses(hass)["Basil"] == "dry"
