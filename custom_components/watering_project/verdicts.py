"""Persisted verdict history.

Hysteresis needs to know whether a plant was dry *before* this evaluation.
Keeping that only in memory means a restart inside the hysteresis band
(``threshold .. threshold + 5``) promotes the plant to healthy, which re-arms
notifications and produces a duplicate push for the same drought.

``no_data`` is never stored: the map holds the last status that carried
information, so a sensor blinking offline does not erase the fact that its plant
was dry.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any, Final

from .classification import Verdict, next_status_history
from .const import STATUS_ORDER
from .store import SECTION_VERDICTS, WateringStore

_LOGGER: Final = logging.getLogger(__name__)

_VALID_STATUSES: Final[frozenset[str]] = frozenset(STATUS_ORDER)


class VerdictHistory:
    """Owns the ``verdicts`` section of the integration store."""

    def __init__(self, store: WateringStore) -> None:
        """Initialise the history on an already-loaded store."""
        if not store.loaded:
            raise RuntimeError("WateringStore must be loaded before VerdictHistory")
        self._store = store

    @property
    def _section(self) -> dict[str, Any]:
        return self._store.section(SECTION_VERDICTS)

    def statuses(self) -> dict[str, str]:
        """Return ``plant_id -> last informative status``."""
        return {
            plant_id: status
            for plant_id, status in self._section.items()
            if isinstance(status, str) and status in _VALID_STATUSES
        }

    def previous_status(self, plant_id: str) -> str | None:
        """Return the last informative status for one plant."""
        return self.statuses().get(plant_id)

    def update(self, verdicts: Iterable[Verdict], now_iso: str | None = None) -> bool:
        """Merge verdicts into the history. Returns whether it changed."""
        materialised = list(verdicts)
        before = self.statuses()
        after = next_status_history(materialised, before)

        changed = False
        for plant_id, status in after.items():
            if self._section.get(plant_id) != status:
                self._section[plant_id] = status
                changed = True

        if changed:
            self._store.mark_dirty()

        previous_plant_ids = set(before)
        current_plant_ids = {verdict.plant_id for verdict in materialised}
        for plant_id in previous_plant_ids - current_plant_ids:
            # Plant disappeared (device removed or excluded): drop the record so
            # the store cannot grow without bound.
            _LOGGER.debug("Dropping verdict history for %s", plant_id)
            self._section.pop(plant_id, None)
            changed = True

        return changed

    def as_dict(self) -> Mapping[str, str]:
        """Read-only view for diagnostics."""
        return dict(self._section)
