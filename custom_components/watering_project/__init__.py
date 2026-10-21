"""Watering Project integration.

Server-side authority for plant status: discovery, battery clock, classification,
entities, notification decisions, the payload contract and its websocket
subscription. The Lovelace card only presents what this code decided.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from awesomeversion import AwesomeVersion
from homeassistant.const import Platform
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv

from . import websocket_api
from .battery import BatteryTracker
from .const import DOMAIN, MIN_HOMEASSISTANT_VERSION
from .evaluate import WateringCoordinator, WateringRuntime
from .store import WateringStore
from .verdicts import VerdictHistory

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER: Final = logging.getLogger(__name__)

PLATFORMS: Final[tuple[Platform, ...]] = (Platform.BINARY_SENSOR, Platform.SENSOR)

# Configured only through a config entry; a YAML block is a mistake, not a feature.
CONFIG_SCHEMA: Final = cv.config_entry_only_config_schema(DOMAIN)


def homeassistant_version_supported(version: str) -> bool:
    """Whether the running Home Assistant meets the supported floor."""
    try:
        return AwesomeVersion(version) >= AwesomeVersion(MIN_HOMEASSISTANT_VERSION)
    except Exception:
        return False


WWW_PATH: Final = Path(__file__).parent / "www"
STATIC_URL_PATH: Final = f"/{DOMAIN}"


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register process-wide resources exactly once.

    Both the websocket command and the static path are process-wide, while config
    entries can reload. Registering them per entry would double-register the
    aiohttp route and silently overwrite the command handler.
    """
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("websocket_registered"):
        websocket_api.async_register(hass)
        data["websocket_registered"] = True

    if not data.get("static_registered"):
        data["static_registered"] = True
        if WWW_PATH.is_dir():
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        STATIC_URL_PATH,
                        str(WWW_PATH),
                        # 31-day default caching would pin a stale card.
                        cache_headers=False,
                    )
                ]
            )
        else:
            _LOGGER.debug("No card bundle at %s yet; static path not registered", WWW_PATH)

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
