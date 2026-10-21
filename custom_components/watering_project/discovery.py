"""Discovery: the single authority for "which devices are plants".

The card, the battery tracker and the options flow all consume this module
instead of re-implementing the predicate. Two implementations would drift, and
the dangerous direction is silent: a plant shown in the card but never tracked
has no staleness record, so a battery stuck at 0% for weeks would render as
"well watered".

``device_class`` and ``unit_of_measurement`` are read from **state attributes**,
not from the registry: the bulk registry payloads do not carry them. A
consequence, documented in the README: an entity with no state object at all
cannot be discovered.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .classification import PlantRecord
from .const import (
    EXCLUDE_REASON_KEYWORD_PREFIX,
    EXCLUDE_REASON_NOT_INCLUDED,
    EXCLUDE_REASON_OPTION,
    LEAK_KEYWORDS,
)

_LOGGER: Final = logging.getLogger(__name__)

MOISTURE_DEVICE_CLASS: Final = "moisture"
BATTERY_DEVICE_CLASS: Final = "battery"
TEMPERATURE_DEVICE_CLASS: Final = "temperature"
PERCENT_UNIT: Final = "%"

#: Group key prefix for entities that belong to no device. Each such entity is
#: its own plant, so they must not share one group.
DEVICE_LESS_PREFIX: Final = "__entity__"


@dataclass(frozen=True, slots=True)
class ExcludedRecord:
    """A device that looked like a plant but was filtered out."""

    device_id: str
    label: str
    reason: str


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Result of one discovery pass."""

    plants: tuple[PlantRecord, ...] = ()
    excluded: tuple[ExcludedRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One registry entity plus the attributes discovery cares about."""

    entity_id: str
    device_id: str | None
    area_id: str | None
    device_class: str | None
    unit: str | None
    friendly_name: str | None


def _attributes(hass: HomeAssistant, entity_id: str) -> dict[str, object]:
    state = hass.states.get(entity_id)
    return dict(state.attributes) if state is not None else {}


def _collect_candidates(hass: HomeAssistant) -> dict[str, list[_Candidate]]:
    """Group enabled sensor entities by device id (or by entity when device-less)."""
    registry = er.async_get(hass)
    grouped: dict[str, list[_Candidate]] = {}

    for entry in registry.entities.values():
        if entry.disabled_by is not None:
            continue
        if not entry.entity_id.startswith("sensor."):
            continue
        attributes = _attributes(hass, entry.entity_id)
        raw_class = attributes.get("device_class")
        raw_unit = attributes.get("unit_of_measurement")
        candidate = _Candidate(
            entity_id=entry.entity_id,
            device_id=entry.device_id,
            area_id=entry.area_id,
            device_class=raw_class if isinstance(raw_class, str) else None,
            unit=raw_unit if isinstance(raw_unit, str) else None,
            friendly_name=(
                attributes.get("friendly_name")
                if isinstance(attributes.get("friendly_name"), str)
                else None
            ),
        )
        group_key = entry.device_id or f"{DEVICE_LESS_PREFIX}{entry.entity_id}"
        grouped.setdefault(group_key, []).append(candidate)

    return grouped


def _lowest_entity_id(candidates: Iterable[_Candidate]) -> _Candidate | None:
    ordered = sorted(candidates, key=lambda candidate: candidate.entity_id)
    return ordered[0] if ordered else None


def _is_moisture(candidate: _Candidate) -> bool:
    return candidate.device_class == MOISTURE_DEVICE_CLASS and candidate.unit == PERCENT_UNIT


def _is_battery(candidate: _Candidate) -> bool:
    return candidate.device_class == BATTERY_DEVICE_CLASS and candidate.unit == PERCENT_UNIT


def _is_temperature(candidate: _Candidate) -> bool:
    return candidate.device_class == TEMPERATURE_DEVICE_CLASS


def _keyword_match(label: str) -> str | None:
    lowered = label.casefold()
    for keyword in LEAK_KEYWORDS:
        if keyword in lowered:
            return keyword
    return None


def _device_label(device: dr.DeviceEntry | None, moisture: _Candidate) -> str:
    if device is not None:
        if device.name_by_user:
            return device.name_by_user
        if device.name:
            return device.name
        if device.model:
            return device.model
    return moisture.friendly_name or moisture.entity_id


def _resolve_area_name(areas: ar.AreaRegistry, area_id: str | None) -> str | None:
    if area_id is None:
        return None
    area = areas.async_get_area(area_id)
    return area.name if area is not None else None


def discover(
    hass: HomeAssistant,
    *,
    include_devices: Sequence[str] = (),
    exclude_devices: Sequence[str] = (),
) -> DiscoveryResult:
    """Run one discovery pass.

    Inclusion precedence, highest first:

    1. ``exclude_devices`` — always wins.
    2. explicit ``include_devices`` entry — overrides keyword auto-exclusion, so
       a user can adopt a device whose name merely looks like a leak sensor.
    3. keyword auto-exclusion on the label (leak/flood/aquarium).
    4. default: include.
    """
    grouped = _collect_candidates(hass)
    devices = dr.async_get(hass)
    areas = ar.async_get(hass)

    include = set(include_devices)
    exclude = set(exclude_devices)

    plants: list[PlantRecord] = []
    excluded: list[ExcludedRecord] = []

    for group_key, candidates in grouped.items():
        device_id = None if group_key.startswith(DEVICE_LESS_PREFIX) else group_key
        moisture_candidates = [item for item in candidates if _is_moisture(item)]
        if not moisture_candidates:
            continue

        moisture = _lowest_entity_id(moisture_candidates)
        assert moisture is not None  # narrowed by the check above

        device = devices.devices.get(device_id) if device_id else None
        label = _device_label(device, moisture)

        area_id = moisture.area_id or (device.area_id if device is not None else None)
        plant_id = device_id or moisture.entity_id

        if device_id is not None:
            if device_id in exclude:
                excluded.append(
                    ExcludedRecord(device_id=device_id, label=label, reason=EXCLUDE_REASON_OPTION)
                )
                continue
            if include and device_id not in include:
                excluded.append(
                    ExcludedRecord(
                        device_id=device_id,
                        label=label,
                        reason=EXCLUDE_REASON_NOT_INCLUDED,
                    )
                )
                continue
            if device_id not in include:
                keyword = _keyword_match(label)
                if keyword is not None:
                    excluded.append(
                        ExcludedRecord(
                            device_id=device_id,
                            label=label,
                            reason=f"{EXCLUDE_REASON_KEYWORD_PREFIX}{keyword}",
                        )
                    )
                    continue
        else:
            keyword = _keyword_match(label)
            if keyword is not None:
                excluded.append(
                    ExcludedRecord(
                        device_id=plant_id,
                        label=label,
                        reason=f"{EXCLUDE_REASON_KEYWORD_PREFIX}{keyword}",
                    )
                )
                continue

        battery = _lowest_entity_id(item for item in candidates if _is_battery(item))
        temperature = _lowest_entity_id(item for item in candidates if _is_temperature(item))

        if len(moisture_candidates) > 1:
            _LOGGER.debug(
                "Device %s exposes %d moisture sensors; using %s",
                device_id or "without device",
                len(moisture_candidates),
                moisture.entity_id,
            )

        plants.append(
            PlantRecord(
                plant_id=plant_id,
                label=label,
                moisture_entity_id=moisture.entity_id,
                area_id=area_id,
                area_name=_resolve_area_name(areas, area_id),
                battery_entity_id=battery.entity_id if battery is not None else None,
                temperature_entity_id=temperature.entity_id if temperature is not None else None,
            )
        )

    plants.sort(key=lambda plant: plant.plant_id)
    excluded.sort(key=lambda record: record.device_id)
    return DiscoveryResult(plants=tuple(plants), excluded=tuple(excluded))
