"""Pure classification rules for the Watering Project integration.

This module is the single place where a plant's status is decided. It is a pure
function: no ``hass``, no registries, no I/O, and ``now`` is injected. That is
what makes the important cases (29 vs 31 days, hysteresis, bad numeric states)
testable in milliseconds without a Home Assistant instance.

Rule order, first match wins:

1. ``suspect_battery``  — battery has reported <= 1% for the configured window.
2. ``no_data``          — the moisture reading is missing or not a finite number.
3. ``dry``              — below threshold, with hysteresis on the way back up.
4. ``healthy``          — everything else, including overwatered plants.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from .const import (
    DRY_HYSTERESIS,
    STATUS_DRY,
    STATUS_HEALTHY,
    STATUS_NO_DATA,
    STATUS_SUSPECT_BATTERY,
)

#: States that mean "the entity exists but has no usable value".
NON_NUMERIC_STATES: Final[frozenset[str]] = frozenset(
    {"", "-", "unknown", "unavailable", "none", "null", "nan"}
)

MAX_BATTERY_PERCENT: Final = 100.0
MIN_BATTERY_PERCENT: Final = 0.0


@dataclass(frozen=True, slots=True)
class PlantRecord:
    """A discovered plant and the entity ids that describe it."""

    plant_id: str
    label: str
    moisture_entity_id: str
    area_id: str | None = None
    area_name: str | None = None
    battery_entity_id: str | None = None
    temperature_entity_id: str | None = None
    threshold: float | None = None


@dataclass(frozen=True, slots=True)
class BatteryFact:
    """Durable battery observation, owned by the tracker."""

    zero_since: datetime | None = None
    last_value: float | None = None
    last_seen: datetime | None = None

    @property
    def never_reported(self) -> bool:
        """Whether no numeric reading has ever been observed."""
        return self.last_value is None

    @property
    def display_value(self) -> float | None:
        """Battery percentage, or ``None`` when the value is not plausible."""
        if self.last_value is None:
            return None
        if not MIN_BATTERY_PERCENT <= self.last_value <= MAX_BATTERY_PERCENT:
            return None
        return self.last_value


@dataclass(frozen=True, slots=True)
class ClassificationConfig:
    """Thresholds used by :func:`classify`."""

    moisture_default: float = 70
    battery_suspect_days: int = 30
    dry_hysteresis: float = DRY_HYSTERESIS


@dataclass(frozen=True, slots=True)
class Verdict:
    """The decision for one plant."""

    plant_id: str
    status: str
    threshold: float
    moisture: float | None = None
    zero_days: int | None = None
    needs_water: bool = False
    battery_value: float | None = None
    battery_never_reported: bool = False
    previous_status: str | None = None


def parse_numeric(raw: Any) -> float | None:
    """Coerce a raw entity state into a finite float.

    Accepts numbers and numeric strings (MQTT and template sensors report
    strings). Rejects booleans, empty/placeholder strings and non-finite values,
    so a stateless sensor can never be silently treated as a number.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if math.isfinite(value) else None
    if isinstance(raw, str):
        text = raw.strip()
        if text.lower() in NON_NUMERIC_STATES:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        return value if math.isfinite(value) else None
    return None


def _elapsed_days(zero_since: datetime, now: datetime) -> float:
    """Return days between ``zero_since`` and ``now``, never negative."""
    seconds = (now - zero_since).total_seconds()
    return max(seconds, 0.0) / 86400


def _classify_one(
    plant: PlantRecord,
    raw_moisture: Any,
    battery: BatteryFact | None,
    previous_status: str | None,
    config: ClassificationConfig,
    now: datetime,
) -> Verdict:
    threshold = plant.threshold if plant.threshold is not None else config.moisture_default

    zero_days: int | None = None
    suspect = False
    if battery is not None and battery.zero_since is not None:
        elapsed = _elapsed_days(battery.zero_since, now)
        zero_days = int(elapsed)
        suspect = elapsed >= config.battery_suspect_days

    moisture = parse_numeric(raw_moisture)

    if suspect:
        status = STATUS_SUSPECT_BATTERY
    elif moisture is None:
        status = STATUS_NO_DATA
    elif moisture < threshold:
        status = STATUS_DRY
    elif previous_status == STATUS_DRY and moisture < threshold + config.dry_hysteresis:
        # Sensor jitter must not release a plant it just flagged.
        status = STATUS_DRY
    else:
        status = STATUS_HEALTHY

    return Verdict(
        plant_id=plant.plant_id,
        status=status,
        threshold=threshold,
        moisture=moisture,
        zero_days=zero_days,
        needs_water=status == STATUS_DRY,
        battery_value=battery.display_value if battery is not None else None,
        battery_never_reported=battery.never_reported if battery is not None else True,
        previous_status=previous_status,
    )


def classify(
    plants: Iterable[PlantRecord],
    values: Mapping[str, Any],
    battery_facts: Mapping[str, BatteryFact],
    previous_statuses: Mapping[str, str],
    config: ClassificationConfig,
    now: datetime,
) -> list[Verdict]:
    """Classify every plant.

    ``values`` maps a moisture entity id to its raw state (missing key and
    ``None`` both mean "no state object"). ``previous_statuses`` must contain
    the last **non-``no_data``** status per ``plant_id``; keeping ``no_data``
    out of that map is what stops a sensor that blinked offline from being
    promoted to healthy on its first reading after an outage.
    """
    verdicts: list[Verdict] = []
    for plant in plants:
        verdicts.append(
            _classify_one(
                plant,
                values.get(plant.moisture_entity_id),
                battery_facts.get(plant.battery_entity_id) if plant.battery_entity_id else None,
                previous_statuses.get(plant.plant_id),
                config,
                now,
            )
        )
    return verdicts


def next_status_history(
    verdicts: Iterable[Verdict], previous_statuses: Mapping[str, str]
) -> dict[str, str]:
    """Build the ``plant_id -> last non-``no_data`` status`` map to persist.

    ``no_data`` never overwrites a known status, so hysteresis keeps working
    across outages and restarts.
    """
    history = dict(previous_statuses)
    for verdict in verdicts:
        if verdict.status == STATUS_NO_DATA:
            continue
        history[verdict.plant_id] = verdict.status
    return history


def battery_is_zero(value: float | None) -> bool:
    """Whether a reading counts as "0%" for staleness tracking."""
    return value is not None and value <= 1.0


def battery_in_range(value: float | None) -> bool:
    """Whether a reading is a plausible battery percentage."""
    return value is not None and MIN_BATTERY_PERCENT <= value <= MAX_BATTERY_PERCENT


def battery_out_of_range(value: float | None) -> bool:
    """Whether a numeric reading is implausible (``-1``, ``255``, ...)."""
    return value is not None and not MIN_BATTERY_PERCENT <= value <= MAX_BATTERY_PERCENT


def suspect_window(config: ClassificationConfig) -> timedelta:
    """Return the configured suspicion window as a timedelta."""
    return timedelta(days=config.battery_suspect_days)
