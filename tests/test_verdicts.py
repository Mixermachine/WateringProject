"""Tests for persisted verdict history (hysteresis across restarts)."""

from __future__ import annotations

from custom_components.watering_project.classification import Verdict
from custom_components.watering_project.const import (
    STATUS_DRY,
    STATUS_HEALTHY,
    STATUS_NO_DATA,
    STATUS_SUSPECT_BATTERY,
)
from custom_components.watering_project.store import WateringStore
from custom_components.watering_project.verdicts import VerdictHistory
from homeassistant.core import HomeAssistant


def verdict(plant_id: str, status: str) -> Verdict:
    return Verdict(plant_id=plant_id, status=status, threshold=70)


async def _history(hass: HomeAssistant) -> tuple[VerdictHistory, WateringStore]:
    store = WateringStore(hass, "test")
    await store.async_load()
    return VerdictHistory(store), store


async def test_update_persists_statuses(hass: HomeAssistant) -> None:
    history, store = await _history(hass)

    changed = history.update([verdict("ficus", STATUS_DRY)])

    assert changed is True
    assert history.statuses() == {"ficus": STATUS_DRY}
    await store.async_save_now()

    reloaded = WateringStore(hass, "test")
    await reloaded.async_load()
    assert VerdictHistory(reloaded).statuses() == {"ficus": STATUS_DRY}


async def test_no_data_never_overwrites_known_status(hass: HomeAssistant) -> None:
    history, _ = await _history(hass)
    history.update([verdict("ficus", STATUS_DRY)])

    history.update([verdict("ficus", STATUS_NO_DATA)])

    assert history.statuses()["ficus"] == STATUS_DRY


async def test_no_data_is_not_stored_when_nothing_known(hass: HomeAssistant) -> None:
    history, _ = await _history(hass)

    history.update([verdict("ficus", STATUS_NO_DATA)])

    assert history.statuses() == {}


async def test_unchanged_update_reports_no_change(hass: HomeAssistant) -> None:
    history, _ = await _history(hass)
    history.update([verdict("ficus", STATUS_DRY)])

    assert history.update([verdict("ficus", STATUS_DRY)]) is False


async def test_disappeared_plant_is_pruned(hass: HomeAssistant) -> None:
    history, _ = await _history(hass)
    history.update([verdict("ficus", STATUS_DRY), verdict("basil", STATUS_HEALTHY)])

    history.update([verdict("ficus", STATUS_DRY)])

    assert history.statuses() == {"ficus": STATUS_DRY}


async def test_suspect_status_is_persisted(hass: HomeAssistant) -> None:
    history, _ = await _history(hass)

    history.update([verdict("ficus", STATUS_SUSPECT_BATTERY)])

    assert history.previous_status("ficus") == STATUS_SUSPECT_BATTERY


async def test_invalid_stored_values_are_ignored(hass: HomeAssistant) -> None:
    history, store = await _history(hass)
    store.section("verdicts")["ficus"] = "bogus"

    assert history.statuses() == {}
