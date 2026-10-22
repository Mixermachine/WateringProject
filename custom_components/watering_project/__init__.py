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
from homeassistant.components import frontend, panel_custom
from homeassistant.const import Platform
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv

from . import websocket_api
from .battery import BatteryTracker
from .const import (
    DOMAIN,
    MIN_HOMEASSISTANT_VERSION,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    VERSION,
)
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
CARD_FILENAME: Final = "watering-project-card.js"
CARD_URL: Final = f"{STATIC_URL_PATH}/{CARD_FILENAME}?v={VERSION}"


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Add the sidebar entry that hosts the card.

    A custom panel instead of a Lovelace dashboard: the integration owns the tab,
    so the user does not create a dashboard and does not register a Lovelace
    resource. Home Assistant loads ``module_url`` and waits for the element
    before mounting it, which a Lovelace resource cannot guarantee.
    """
    if not WWW_PATH.is_dir():
        _LOGGER.warning("Card bundle missing at %s; sidebar panel not registered", WWW_PATH)
        return
    if PANEL_URL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        return
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=CARD_URL,
        require_admin=False,
        config={},
    )
    hass.data.setdefault(DOMAIN, {})["panel_registered"] = True


def _async_remove_panel(hass: HomeAssistant) -> None:
    """Drop the sidebar entry when the integration is removed."""
    if not hass.data.get(DOMAIN, {}).pop("panel_registered", False):
        return
    frontend.async_remove_panel(hass, PANEL_URL_PATH)


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
    await _async_register_panel(hass)

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
    """Delete persisted state and the sidebar entry when the integration is removed.

    The panel deliberately survives a plain unload/reload (options change): adding
    and removing it in quick succession makes the frontend treat the route as
    unknown and bounce the next visit to the default dashboard. Cards show the
    `not_loaded` state while the entry is unloaded.
    """
    store = WateringStore(hass, entry.entry_id)
    await store.async_remove()
    _async_remove_panel(hass)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so new options take effect immediately."""
    await hass.config_entries.async_reload(entry.entry_id)
