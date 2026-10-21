"""Persistence for the Watering Project integration.

One versioned Home Assistant ``Store`` document per config entry, holding three
independent sections:

``battery``
    per-entity battery observation records (``zero_since``, ``last_value``,
    ``last_seen``) that make the staleness clock survive restarts and value
    blips.

``verdicts``
    ``plant_id -> last non-``no_data`` status``, so hysteresis survives a
    restart instead of silently resetting inside the band.

``notify``
    notification state (``last_notified``), written ahead of dispatch.

Writes are debounced (>= ``STORAGE_SAVE_DELAY`` seconds) because battery
reports trickle in continuously. Notification state bypasses the debounce via
:meth:`WateringStore.async_save_now`, because a crash between "decided to
notify" and "persisted that we notified" produces a duplicate push.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from typing import Any, Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_SAVE_DELAY, STORAGE_VERSION

_LOGGER: Final = logging.getLogger(__name__)

SECTION_BATTERY: Final = "battery"
SECTION_VERDICTS: Final = "verdicts"
SECTION_NOTIFY: Final = "notify"

SECTIONS: Final[tuple[str, ...]] = (
    SECTION_BATTERY,
    SECTION_VERDICTS,
    SECTION_NOTIFY,
)


def _empty_data() -> dict[str, dict[str, Any]]:
    """Return a fresh, empty store payload."""
    return {section: {} for section in SECTIONS}


def _clean_section(name: str, raw: Any) -> dict[str, Any]:
    """Coerce a stored section into a dict, dropping anything unusable."""
    if not isinstance(raw, dict):
        return {}
    if name == SECTION_VERDICTS:
        # plant_id -> status string
        return {str(key): value for key, value in raw.items() if isinstance(value, str)}
    if name == SECTION_NOTIFY:
        return {str(key): value for key, value in raw.items()}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


class WateringStore:
    """Wrapper around one :class:`~homeassistant.helpers.storage.Store`."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise the store for a config entry."""
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
        )
        self._data: dict[str, dict[str, Any]] = _empty_data()
        self._loaded = False
        self._dirty = False
        self._unsub_delay: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []

    # -- lifecycle ---------------------------------------------------------

    async def async_load(self) -> None:
        """Load persisted data. Safe to call multiple times."""
        if self._loaded:
            return
        raw = await self._store.async_load()
        data = _empty_data()
        if isinstance(raw, dict):
            for section in SECTIONS:
                data[section] = _clean_section(section, raw.get(section))
        else:
            # Unknown shape (e.g. downgrade): start clean rather than crash.
            _LOGGER.warning("Discarding unreadable %s storage payload", DOMAIN)
        self._data = data
        self._loaded = True
        self._dirty = False

    async def async_flush(self) -> None:
        """Cancel a pending debounced write and persist immediately."""
        self._cancel_delay()
        if not self._dirty:
            return
        await self._async_write()

    async def async_remove(self) -> None:
        """Remove the backing storage when the config entry is deleted."""
        self._cancel_delay()
        self._dirty = False
        await self._store.async_remove()

    @property
    def loaded(self) -> bool:
        """Whether :meth:`async_load` has completed."""
        return self._loaded

    # -- access ------------------------------------------------------------

    def section(self, name: str) -> dict[str, Any]:
        """Return a live reference to one section.

        Callers mutate the returned dict and then call :meth:`async_schedule_save`
        or :meth:`async_save_now`. Sections are plain dicts on purpose: the
        payload is JSON-shaped and must round-trip unchanged.
        """
        if name not in self._data:
            raise KeyError(name)
        return self._data[name]

    def as_dict(self) -> dict[str, dict[str, Any]]:
        """Return a deep copy of the whole payload (diagnostics/tests)."""
        return deepcopy(self._data)

    def mark_dirty(self) -> None:
        """Flag a mutation made directly on a section reference."""
        self._dirty = True

    # -- saving ------------------------------------------------------------

    def async_schedule_save(self) -> None:
        """Mark dirty and save after the debounce window."""
        self._dirty = True
        if self._unsub_delay is not None:
            return
        self._unsub_delay = self._store.async_delay_save(
            self._async_delay_callback, STORAGE_SAVE_DELAY
        )

    async def async_save_now(self) -> None:
        """Persist immediately, bypassing the debounce (notification state)."""
        self._cancel_delay()
        self._dirty = True
        await self._async_write()

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired after a successful write."""
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    # -- internals ---------------------------------------------------------

    def _async_delay_callback(self) -> dict[str, Any]:
        """Return the payload for the debounced writer."""
        self._unsub_delay = None
        return self._data

    async def _async_write(self) -> None:
        self._dirty = False
        try:
            await self._store.async_save(self._data)
        except Exception:
            self._dirty = True
            _LOGGER.exception("Failed to save %s storage; retrying on next change", DOMAIN)
            return
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("Storage listener failed")

    def _cancel_delay(self) -> None:
        if self._unsub_delay is not None:
            self._unsub_delay()
            self._unsub_delay = None


def isoformat(value: datetime | None) -> str | None:
    """Serialise a datetime as an ISO-8601 UTC string."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.UTC)
    return value.astimezone(dt_util.UTC).isoformat()


def parse_datetime(value: Any) -> datetime | None:
    """Parse a stored ISO-8601 string, returning ``None`` when unusable."""
    if not isinstance(value, str) or not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed
