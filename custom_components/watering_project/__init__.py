"""Watering Project integration.

M2a: evaluation pipeline, entities and config/options flow. Notifications and
the websocket subscription are M2b; the pipeline already records the payload
signature they will use.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from awesomeversion import AwesomeVersion
from homeassistant.const import Platform
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .battery import BatteryTracker
from .const import DOMAIN, MIN_HOMEASSISTANT_VERSION
from .evaluate import WateringCoordinator, WateringRuntime
from .store import WateringStore
from .verdicts import VerdictHistory

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER: Final = logging.getLogger(__name__)

PLATFORMS: Final[tuple[Platform, ...]] = (Platform.BINARY_SENSOR, Platform.SENSOR)


def homeassistant_version_supported(version: str) -> bool:
    """Whether the running Home Assistant meets the supported floor."""
    try:
        return AwesomeVersion(version) >= AwesomeVersion(MIN_HOMEASSISTANT_VERSION)
    except Exception:
        return False


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration (no YAML configuration in v1)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one config entry: load state, evaluate, start triggers."""
    if not homeassistant_version_supported(HA_VERSION):
        raise ConfigEntryError(
            f"Watering Project requires Home Assistant {MIN_HOMEASSISTANT_VERSION} "
            f"or newer (running {HA_VERSION})"
        )

    store = WateringStore(hass, entry.entry_id)
    await store.async_load()

    battery = BatteryTracker(store)
    history = VerdictHistory(store)
    coordinator = WateringCoordinator(hass, entry, store, battery, history)

    entry.runtime_data = WateringRuntime(
        store=store,
        battery=battery,
        history=history,
        coordinator=coordinator,
    )

    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    _LOGGER.debug("%s set up for entry %s", DOMAIN, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload platforms and cancel every trigger."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        runtime: WateringRuntime | None = getattr(entry, "runtime_data", None)
        if runtime is not None:
            await runtime.coordinator.async_stop()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete persisted state when the entry is removed."""
    store = WateringStore(hass, entry.entry_id)
    await store.async_remove()


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so new options take effect immediately."""
    await hass.config_entries.async_reload(entry.entry_id)
