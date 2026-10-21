"""Watering Project integration.

M1 scope: the decide layer (store, discovery, battery tracker, verdict history,
classification). The evaluation pipeline, entities, notifications and websocket
subscription arrive in M2; until then the config entry loads only its persisted
state, so storage format and migrations can be tested in isolation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from homeassistant.core import HomeAssistant

from .battery import BatteryTracker
from .const import DOMAIN
from .store import WateringStore
from .verdicts import VerdictHistory

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER: Final = logging.getLogger(__name__)

PLATFORMS: Final[tuple[str, ...]] = ()

DATA_STORE: Final = "store"
DATA_BATTERY: Final = "battery"
DATA_VERDICTS: Final = "verdicts"


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration (no YAML configuration in v1)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load persisted state for one config entry."""
    store = WateringStore(hass, entry.entry_id)
    await store.async_load()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_STORE: store,
        DATA_BATTERY: BatteryTracker(store),
        DATA_VERDICTS: VerdictHistory(store),
    }

    _LOGGER.debug("%s loaded for entry %s", DOMAIN, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one config entry, flushing pending storage writes."""
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data is not None:
        store: WateringStore = data[DATA_STORE]
        await store.async_flush()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete persisted state when the entry is removed."""
    store = WateringStore(hass, entry.entry_id)
    await store.async_remove()
