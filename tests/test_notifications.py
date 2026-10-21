"""Tests for the notification matrix and repair issues.

The matrix is the point: one push per drought, no push on a sensor that blinks
offline, no duplicate after a restart, and a repair issue instead of a crash when
the notify service is gone.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from custom_components.watering_project.const import (
    CONF_BATTERY_SUSPECT_DAYS,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_REPEAT_HOURS,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_URL,
    DOMAIN,
)
from custom_components.watering_project.notifications import (
    ISSUE_BATTERY_SUSPECT,
    ISSUE_NOTIFY_SERVICE,
    build_message,
    should_notify,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from tests.helpers import MOISTURE_ATTRS, add_entry, add_plant, setup_entry

NOW = dt_util.utcnow()


class Recorder:
    """Collects notify service calls.

    The registered handler must be a real coroutine function: Home Assistant
    inspects it to decide whether to await, so an object with an async
    ``__call__`` would be treated as synchronous and the call silently dropped.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def handler(self, call) -> None:
        """Record one service call."""
        self.calls.append({"service": call.service, "data": dict(call.data)})


def notify_options(**overrides) -> dict:
    options = {
        CONF_NOTIFY_ENABLED: True,
        CONF_NOTIFY_SERVICE: "test_phone",
        CONF_NOTIFY_REPEAT_HOURS: 24,
        CONF_NOTIFY_URL: "/lovelace/0",
    }
    options.update(overrides)
    return options


async def _setup(hass: HomeAssistant, options: dict, *, moisture: str = "42"):
    entry = add_entry(hass, options)
    plant = add_plant(hass, entry, "ficus", name="Ficus", moisture=moisture)
    recorder = Recorder()
    hass.services.async_register("notify", "test_phone", recorder.handler)
    await setup_entry(hass, entry)
    await hass.async_block_till_done()
    return entry, plant, recorder


# -- pure helpers ------------------------------------------------------------


def test_should_notify_first_time() -> None:
    assert should_notify(None, NOW, 24) is True


def test_should_notify_respects_hard_floor() -> None:
    assert should_notify(NOW - timedelta(hours=23), NOW, 24) is False
    assert should_notify(NOW - timedelta(hours=25), NOW, 24) is True


def test_should_notify_never_repeats_when_repeat_is_zero() -> None:
    assert should_notify(NOW - timedelta(days=10), NOW, 0) is False


def test_build_message_pluralises() -> None:
    assert build_message(["Ficus"]) == ("Plants need water", "1 plant needs water: Ficus")
    assert build_message(["Ficus", "Basil"])[1] == "2 plants need water: Ficus, Basil"


# -- behaviour ---------------------------------------------------------------


async def test_no_dry_plants_sends_nothing(hass: HomeAssistant, enable_custom_integrations) -> None:
    _, _, recorder = await _setup(hass, notify_options(), moisture="95")

    assert recorder.calls == []


async def test_first_drought_notifies_once_with_url(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    _, _, recorder = await _setup(hass, notify_options())

    assert len(recorder.calls) == 1
    data = recorder.calls[0]["data"]
    assert data["title"] == "Plants need water"
    assert "Ficus" in data["message"]
    assert data["data"] == {"url": "/lovelace/0"}


async def test_second_dry_plant_inside_window_does_not_renotify(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry, _, recorder = await _setup(hass, notify_options())
    assert len(recorder.calls) == 1

    add_plant(hass, entry, "basil", name="Basil", moisture="20")
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert len(recorder.calls) == 1


async def test_repeat_after_window(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry, _, recorder = await _setup(hass, notify_options())
    assert len(recorder.calls) == 1

    manager = entry.runtime_data.coordinator.notifications
    await manager._set_last_notified(dt_util.utcnow() - timedelta(hours=25))
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert len(recorder.calls) == 2


async def test_confirmed_recovery_rearms(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry, plant, recorder = await _setup(hass, notify_options())
    assert len(recorder.calls) == 1

    moisture_id = plant["moisture"]
    assert moisture_id is not None
    hass.states.async_set(moisture_id, "95", MOISTURE_ATTRS)
    await entry.runtime_data.coordinator.async_evaluate()
    assert entry.runtime_data.coordinator.notifications.last_notified is None

    hass.states.async_set(moisture_id, "30", MOISTURE_ATTRS)
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert len(recorder.calls) == 2


async def test_unavailable_sensor_does_not_rearm(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """A flapping sensor must not produce an unbounded stream of pushes."""
    entry, plant, recorder = await _setup(hass, notify_options())
    assert len(recorder.calls) == 1
    moisture_id = plant["moisture"]
    assert moisture_id is not None

    hass.states.async_set(moisture_id, "unavailable", MOISTURE_ATTRS)
    await entry.runtime_data.coordinator.async_evaluate()
    assert entry.runtime_data.coordinator.notifications.last_notified is not None

    hass.states.async_set(moisture_id, "30", MOISTURE_ATTRS)
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert len(recorder.calls) == 1


async def test_repeat_zero_sends_once_per_drought(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    options = notify_options(**{CONF_NOTIFY_REPEAT_HOURS: 0})
    entry, plant, recorder = await _setup(hass, options)
    assert len(recorder.calls) == 1

    manager = entry.runtime_data.coordinator.notifications
    await manager._set_last_notified(dt_util.utcnow() - timedelta(days=5))
    await entry.runtime_data.coordinator.async_evaluate()

    assert len(recorder.calls) == 1

    moisture_id = plant["moisture"]
    assert moisture_id is not None
    hass.states.async_set(moisture_id, "95", MOISTURE_ATTRS)
    await entry.runtime_data.coordinator.async_evaluate()
    hass.states.async_set(moisture_id, "30", MOISTURE_ATTRS)
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert len(recorder.calls) == 2


async def test_notifications_disabled_sends_nothing(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    _, _, recorder = await _setup(hass, notify_options(**{CONF_NOTIFY_ENABLED: False}))

    assert recorder.calls == []


async def test_state_survives_restart(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry, _, recorder = await _setup(hass, notify_options())
    assert len(recorder.calls) == 1
    first = entry.runtime_data.coordinator.notifications.last_notified
    assert first is not None

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.coordinator.notifications.last_notified == first
    assert len(recorder.calls) == 1


async def test_missing_service_raises_repair_issue(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(
        hass,
        notify_options(**{CONF_NOTIFY_SERVICE: "gone_phone"}),
    )
    add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)
    await hass.async_block_till_done()

    issue = ir.async_get(hass).issues.get((DOMAIN, ISSUE_NOTIFY_SERVICE))
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False


async def test_successful_send_clears_repair_issue(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass, notify_options(**{CONF_NOTIFY_SERVICE: "late_phone"}))
    add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert (DOMAIN, ISSUE_NOTIFY_SERVICE) in ir.async_get(hass).issues

    late = Recorder()
    hass.services.async_register("notify", "late_phone", late.handler)
    entry.runtime_data.coordinator.notifications._section["last_notified"] = None
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert (DOMAIN, ISSUE_NOTIFY_SERVICE) not in ir.async_get(hass).issues


async def test_battery_suspect_issue_tracks_plants(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = add_entry(hass, {CONF_BATTERY_SUSPECT_DAYS: 1})
    plant = add_plant(hass, entry, "ficus", name="Ficus", battery="0")
    await setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert (DOMAIN, ISSUE_BATTERY_SUSPECT) not in ir.async_get(hass).issues

    battery_entity = plant["battery"]
    assert battery_entity is not None
    record = entry.runtime_data.coordinator.battery.records[battery_entity]
    record["zero_since"] = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    issue = ir.async_get(hass).issues.get((DOMAIN, ISSUE_BATTERY_SUSPECT))
    assert issue is not None
    assert "Ficus" in issue.translation_placeholders["plants"]

    hass.states.async_set(
        battery_entity, "80", {"device_class": "battery", "unit_of_measurement": "%"}
    )
    await entry.runtime_data.coordinator.async_evaluate()
    await hass.async_block_till_done()

    assert (DOMAIN, ISSUE_BATTERY_SUSPECT) not in ir.async_get(hass).issues


@pytest.mark.parametrize("bad_service", ["", "  "])
async def test_enabled_without_service_is_reported(
    hass: HomeAssistant, enable_custom_integrations, bad_service: str
) -> None:
    entry = add_entry(hass, notify_options(**{CONF_NOTIFY_SERVICE: bad_service}))
    add_plant(hass, entry, "ficus")
    await setup_entry(hass, entry)
    await hass.async_block_till_done()

    assert (DOMAIN, ISSUE_NOTIFY_SERVICE) in ir.async_get(hass).issues
