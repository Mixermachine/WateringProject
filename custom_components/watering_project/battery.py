"""Durable battery staleness tracking.

Why this exists instead of ``now - state.last_changed``: Home Assistant rebuilds
``hass.states`` on every start, and ``StateMachine.async_set_internal`` keeps
``last_changed`` only when the *same* value repeats inside one run. So
``last_changed`` measures "time since the last restart" and resets on any
``0 -> 100 -> 0`` charging blip. Both are exactly what this hardware does.

This tracker records observations itself, on a per-entity basis:

* finite reading ``<= 1``   -> start the clock (``zero_since``) if not running
* finite reading ``> 1``    -> stop the clock
* implausible / non-numeric -> leave the clock alone (unknown is not recovery)

Only a numeric reading advances ``last_seen``; an entity that went
``unavailable`` is not "seen", otherwise dead records would never be pruned.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from .classification import (
    BatteryFact,
    battery_is_zero,
    battery_out_of_range,
    parse_numeric,
)
from .const import BATTERY_RECORD_TTL
from .store import SECTION_BATTERY, WateringStore, isoformat, parse_datetime

_LOGGER: Final = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ObservationResult:
    """Outcome of observing one battery reading."""

    changed: bool
    zero_since: datetime | None
    value: float | None


class BatteryTracker:
    """Owns the ``battery`` section of the integration store."""

    def __init__(self, store: WateringStore) -> None:
        """Initialise the tracker on an already-loaded store."""
        if not store.loaded:
            raise RuntimeError("WateringStore must be loaded before BatteryTracker")
        self._store = store

    # -- access ------------------------------------------------------------

    @property
    def records(self) -> dict[str, dict[str, Any]]:
        """Raw persisted records, keyed by entity id."""
        return self._store.section(SECTION_BATTERY)

    def tracked_entity_ids(self) -> set[str]:
        """Entity ids with a persisted record."""
        return set(self.records)

    def facts(self, entity_id: str | None) -> BatteryFact | None:
        """Return the fact bundle for one battery entity."""
        if entity_id is None:
            return None
        record = self.records.get(entity_id)
        if record is None:
            return None
        return BatteryFact(
            zero_since=parse_datetime(record.get("zero_since")),
            last_value=_as_float(record.get("last_value")),
            last_seen=parse_datetime(record.get("last_seen")),
        )

    def facts_for(self, entity_ids: Iterable[str]) -> dict[str, BatteryFact]:
        """Return facts for several entities, skipping unknown ids."""
        result: dict[str, BatteryFact] = {}
        for entity_id in entity_ids:
            fact = self.facts(entity_id)
            if fact is not None:
                result[entity_id] = fact
        return result

    # -- mutation ----------------------------------------------------------

    def observe(self, entity_id: str, raw_state: Any, now: datetime) -> ObservationResult:
        """Record one reading.

        Returns whether anything persistent changed, so the caller can decide
        whether to schedule a debounced save.
        """
        value = parse_numeric(raw_state)

        if value is None:
            # ``unavailable``/``unknown``/garbage: unknown is not recovery, and
            # it is not "seen" either.
            record = self.records.get(entity_id)
            return ObservationResult(
                changed=False,
                zero_since=parse_datetime(record.get("zero_since")) if record else None,
                value=_as_float(record.get("last_value")) if record else None,
            )

        record = self.records.setdefault(
            entity_id, {"zero_since": None, "last_value": None, "last_seen": None}
        )
        changed = False

        if battery_out_of_range(value):
            # Implausible (-1, 255): unknown, clock untouched, but the entity
            # did report something.
            if record.get("last_value") != value:
                record["last_value"] = value
                changed = True
        elif battery_is_zero(value):
            if record.get("zero_since") is None:
                record["zero_since"] = isoformat(now)
                changed = True
            if record.get("last_value") != value:
                record["last_value"] = value
                changed = True
        else:
            if record.get("zero_since") is not None:
                record["zero_since"] = None
                changed = True
            if record.get("last_value") != value:
                record["last_value"] = value
                changed = True

        last_seen = isoformat(now)
        if record.get("last_seen") != last_seen:
            record["last_seen"] = last_seen
            changed = True

        if changed:
            self._store.mark_dirty()

        return ObservationResult(
            changed=changed,
            zero_since=parse_datetime(record.get("zero_since")),
            value=value,
        )

    def prune(self, now: datetime, tracked_entity_ids: Iterable[str] | None = None) -> bool:
        """Drop records that have not reported numerically for the TTL."""
        stale: list[str] = []
        for entity_id, record in self.records.items():
            last_seen = parse_datetime(record.get("last_seen"))
            if last_seen is not None and now - last_seen > BATTERY_RECORD_TTL:
                stale.append(entity_id)

        tracked = set(tracked_entity_ids) if tracked_entity_ids is not None else None
        for entity_id in list(self.records):
            if tracked is not None and entity_id not in tracked:
                # Only prune unknown entities when they are also stale, otherwise
                # a temporarily disabled entity would lose its clock.
                last_seen = parse_datetime(self.records[entity_id].get("last_seen"))
                if last_seen is not None and now - last_seen > BATTERY_RECORD_TTL:
                    stale.append(entity_id)

        for entity_id in set(stale):
            _LOGGER.debug("Pruning stale battery record for %s", entity_id)
            self.records.pop(entity_id, None)

        if stale:
            self._store.mark_dirty()
            return True
        return False

    def apply_observations(
        self,
        readings: Mapping[str, Any],
        now: datetime,
        tracked_entity_ids: Iterable[str],
    ) -> bool:
        """Observe a batch of readings, then prune."""
        changed = False
        for entity_id in tracked_entity_ids:
            if entity_id not in readings:
                continue
            if self.observe(entity_id, readings[entity_id], now).changed:
                changed = True
        if self.prune(now):
            changed = True
        return changed


def _as_float(value: Any) -> float | None:
    parsed = parse_numeric(value)
    return parsed
