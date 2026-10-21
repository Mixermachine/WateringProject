"""Evaluation pipeline: the single place where the integration decides.

``async_evaluate()`` is the only entry point. State changes, registry changes,
the 60 s timer, options reloads and setup all call it, which is why tests call it
directly instead of simulating triggers.

Two properties this module exists for:

**Single-flight.** The timer and a debounced state change must not both see
``last_notified is None`` and push twice, and they must not emit payloads out of
order. A run in progress sets ``dirty`` and the pipeline re-runs exactly once
afterwards.

**Failure isolation.** An exception during evaluation logs, marks every plant
``no_data`` (loud, not frozen at a stale verdict) and leaves the timer and
listeners alive.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .battery import BatteryTracker
from .classification import (
    ClassificationConfig,
    PlantRecord,
    Verdict,
    classify,
)
from .const import (
    CONF_BATTERY_SUSPECT_DAYS,
    CONF_EXCLUDE_DEVICES,
    CONF_INCLUDE_DEVICES,
    CONF_MOISTURE_DEFAULT,
    DEFAULT_BATTERY_SUSPECT_DAYS,
    DEFAULT_MOISTURE_THRESHOLD,
    EVALUATE_DEBOUNCE_SECONDS,
    EVALUATE_INTERVAL,
    STATUS_NO_DATA,
)
from .discovery import ExcludedRecord, discover
from .store import WateringStore
from .verdicts import VerdictHistory

_LOGGER: Final = logging.getLogger(__name__)

BATTERY_DEVICE_CLASS: Final = "battery"


def _verdict_key(verdict: Verdict) -> tuple[Any, ...]:
    """The externally observable parts of a verdict.

    ``previous_status`` and ``battery_never_reported`` are diagnostics. Counting
    them would make every evaluation look like a status flip (``previous_status``
    fills in after the first run) and push the payload on every tick.
    """
    return (
        verdict.status,
        verdict.needs_water,
        verdict.moisture,
        verdict.zero_days,
        verdict.battery_value,
        verdict.threshold,
    )


@dataclass
class WateringRuntime:
    """Runtime data attached to the config entry (``entry.runtime_data``)."""

    store: WateringStore
    battery: BatteryTracker
    history: VerdictHistory
    coordinator: WateringCoordinator


def _option(entry: ConfigEntry, key: str, default: Any) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


def classification_config(entry: ConfigEntry) -> ClassificationConfig:
    """Build the classification config from entry options."""
    return ClassificationConfig(
        moisture_default=float(_option(entry, CONF_MOISTURE_DEFAULT, DEFAULT_MOISTURE_THRESHOLD)),
        battery_suspect_days=int(
            _option(entry, CONF_BATTERY_SUSPECT_DAYS, DEFAULT_BATTERY_SUSPECT_DAYS)
        ),
    )


class WateringCoordinator:
    """Holds the current plants and verdicts for one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: WateringStore,
        battery: BatteryTracker,
        history: VerdictHistory,
    ) -> None:
        """Initialise the coordinator (nothing is scheduled yet)."""
        self.hass = hass
        self.entry = entry
        self.store = store
        self.battery = battery
        self.history = history

        self.plants: dict[str, PlantRecord] = {}
        self.excluded: tuple[ExcludedRecord, ...] = ()
        self.verdicts: dict[str, Verdict] = {}
        self.payload_version: int = 0
        self.verdict_version: int = 0

        self._running = False
        self._pending = False
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._state_unsub: Callable[[], None] | None = None
        self._tracked_state_ids: tuple[str, ...] = ()
        self._payload_signature: tuple[Any, ...] | None = None
        self._debouncer: Debouncer[None] | None = None
        self._started = False
        self.evaluation_count = 0

    # -- lifecycle ---------------------------------------------------------

    async def async_start(self) -> None:
        """Run the first evaluation and install every trigger."""
        if self._started:
            return
        self._started = True

        self._debouncer = Debouncer(
            self.hass,
            _LOGGER,
            cooldown=EVALUATE_DEBOUNCE_SECONDS,
            immediate=False,
            function=self._async_debounced_evaluate,
        )

        await self.async_evaluate(trigger="setup")

        self._unsubs.append(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_registry_event
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                dr.EVENT_DEVICE_REGISTRY_UPDATED, self._handle_registry_event
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, self._handle_registry_event)
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._async_tick, EVALUATE_INTERVAL)
        )

    async def async_stop(self) -> None:
        """Cancel every trigger and flush persisted state."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._state_unsub is not None:
            self._state_unsub()
            self._state_unsub = None
        if self._debouncer is not None:
            shutdown = getattr(self._debouncer, "async_shutdown", None)
            if shutdown is not None:
                result = shutdown()
                if inspect.isawaitable(result):
                    await result
            self._debouncer = None
        await self.store.async_flush()
        self._started = False

    # -- listeners ---------------------------------------------------------

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity callback, fired after each evaluation."""
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    # -- triggers ----------------------------------------------------------

    @callback
    def _handle_registry_event(self, _event: Event[Any]) -> None:
        self._schedule()

    @callback
    def _handle_state_event(self, _event: Event[Any]) -> None:
        self._schedule()

    @callback
    def _schedule(self) -> None:
        # ``Debouncer.async_call`` is a coroutine: calling it without awaiting it
        # silently does nothing except emit a "never awaited" warning.
        if self._debouncer is not None:
            self.hass.async_create_task(self._debouncer.async_call())

    async def _async_debounced_evaluate(self) -> None:
        await self.async_evaluate(trigger="debounced")

    async def _async_tick(self, _now: datetime) -> None:
        """Timer trigger, skipped when nothing time-dependent can change."""
        if not self._has_pending_battery_clock():
            return
        await self.async_evaluate(trigger="timer")

    def _has_pending_battery_clock(self) -> bool:
        for plant in self.plants.values():
            if plant.battery_entity_id is None:
                continue
            fact = self.battery.facts(plant.battery_entity_id)
            if fact is not None and fact.zero_since is not None:
                return True
        return False

    # -- evaluation --------------------------------------------------------

    async def async_evaluate(self, *, trigger: str = "manual") -> None:
        """Run the pipeline, coalescing concurrent calls."""
        if self._running:
            self._pending = True
            return
        self._running = True
        try:
            await self._async_evaluate_once(trigger)
            if self._pending:
                self._pending = False
                await self._async_evaluate_once("coalesced")
        finally:
            self._running = False

    async def _async_evaluate_once(self, trigger: str) -> None:
        self.evaluation_count += 1
        try:
            await self._async_build(trigger)
        except Exception:
            _LOGGER.exception("Evaluation failed (%s); marking all plants no_data", trigger)
            self._mark_no_data()
            self._notify_listeners()

    async def _async_build(self, trigger: str) -> None:
        now = dt_util.utcnow()
        include = _option(self.entry, CONF_INCLUDE_DEVICES, [])
        exclude = _option(self.entry, CONF_EXCLUDE_DEVICES, [])

        result = discover(
            self.hass,
            include_devices=tuple(include),
            exclude_devices=tuple(exclude),
        )

        battery_ids = self._battery_entity_ids(result.plants, exclude)
        readings = {
            entity_id: (
                state.state if (state := self.hass.states.get(entity_id)) is not None else None
            )
            for entity_id in battery_ids
        }
        if self.battery.apply_observations(readings, now, battery_ids):
            self.store.async_schedule_save()

        facts = {
            plant.battery_entity_id: fact
            for plant in result.plants
            if plant.battery_entity_id
            and (fact := self.battery.facts(plant.battery_entity_id)) is not None
        }

        values: dict[str, Any] = {}
        for plant in result.plants:
            state = self.hass.states.get(plant.moisture_entity_id)
            values[plant.moisture_entity_id] = state.state if state is not None else None

        previous = self.history.statuses()
        verdicts = classify(
            result.plants,
            values,
            facts,
            previous,
            classification_config(self.entry),
            now,
        )

        self.plants = {plant.plant_id: plant for plant in result.plants}
        self.excluded = result.excluded
        new_verdicts = {verdict.plant_id: verdict for verdict in verdicts}

        changed = self._verdicts_changed(self.verdicts, new_verdicts)
        self.verdicts = new_verdicts
        if changed:
            self.verdict_version += 1

        if self.history.update(verdicts):
            self.store.async_schedule_save()

        self._sync_state_listeners()
        self._update_payload_version(trigger)
        self._notify_listeners()

    # -- helpers -----------------------------------------------------------

    def _battery_entity_ids(
        self, plants: Sequence[PlantRecord], exclude: Iterable[str]
    ) -> set[str]:
        """Battery entities to observe: device-based, independent of discovery."""
        excluded = set(exclude)
        registry = er.async_get(self.hass)
        ids = {
            entity_id
            for entity_id in self.battery.tracked_entity_ids()
            if entity_id not in excluded
        }
        for entity in registry.entities.values():
            if entity.disabled_by is not None:
                continue
            if entity.device_id is not None and entity.device_id in excluded:
                continue
            state = self.hass.states.get(entity.entity_id)
            if state is None:
                continue
            if state.attributes.get("device_class") != BATTERY_DEVICE_CLASS:
                continue
            ids.add(entity.entity_id)
        for plant in plants:
            if plant.battery_entity_id:
                ids.add(plant.battery_entity_id)
        return ids

    def _sync_state_listeners(self) -> None:
        tracked = tuple(
            sorted(
                {
                    entity_id
                    for plant in self.plants.values()
                    for entity_id in (
                        plant.moisture_entity_id,
                        plant.battery_entity_id,
                        plant.temperature_entity_id,
                    )
                    if entity_id
                }
            )
        )
        if tracked == self._tracked_state_ids and self._state_unsub is not None:
            return
        if self._state_unsub is not None:
            self._state_unsub()
            self._state_unsub = None
        self._tracked_state_ids = tracked
        if tracked:
            self._state_unsub = async_track_state_change_event(
                self.hass, list(tracked), self._handle_state_event
            )

    def _verdicts_changed(self, old: dict[str, Verdict], new: dict[str, Verdict]) -> bool:
        if old.keys() != new.keys():
            return True
        return any(_verdict_key(old[plant_id]) != _verdict_key(new[plant_id]) for plant_id in new)

    def _update_payload_version(self, trigger: str) -> None:
        signature = self._payload_signature_of()
        if signature != self._payload_signature:
            self._payload_signature = signature
            self.payload_version += 1

    def _payload_signature_of(self) -> tuple[Any, ...]:
        """Fields whose change makes the payload worth pushing."""
        parts: list[Any] = [
            self.entry.options.get(CONF_MOISTURE_DEFAULT),
            self.entry.options.get(CONF_BATTERY_SUSPECT_DAYS),
            self.verdict_version,
        ]
        for plant_id in sorted(self.plants):
            plant = self.plants[plant_id]
            verdict = self.verdicts.get(plant_id)
            parts.append(
                (
                    plant_id,
                    plant.label,
                    plant.area_id,
                    plant.battery_entity_id,
                    plant.temperature_entity_id,
                    verdict.status if verdict else None,
                    verdict.zero_days if verdict else None,
                )
            )
        parts.append(tuple((item.device_id, item.reason) for item in self.excluded))
        return tuple(parts)

    def _mark_no_data(self) -> None:
        from .classification import Verdict as _Verdict

        marked: dict[str, Verdict] = {}
        for plant_id in self.plants:
            previous = self.verdicts.get(plant_id)
            marked[plant_id] = _Verdict(
                plant_id=plant_id,
                status=STATUS_NO_DATA,
                threshold=previous.threshold if previous else 70,
                previous_status=previous.status if previous else None,
            )
        self.verdicts = marked
        self.verdict_version += 1

    @callback
    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("Entity listener failed")

    # -- accessors ---------------------------------------------------------

    def plant(self, plant_id: str) -> PlantRecord | None:
        """Return the current record for one plant."""
        return self.plants.get(plant_id)

    def verdict(self, plant_id: str) -> Verdict | None:
        """Return the current verdict for one plant."""
        return self.verdicts.get(plant_id)

    @property
    def needs_water_count(self) -> int:
        """Number of plants currently requesting water."""
        return sum(1 for verdict in self.verdicts.values() if verdict.needs_water)

    @property
    def any_needs_water(self) -> bool:
        """Whether any plant currently requests water."""
        return any(verdict.needs_water for verdict in self.verdicts.values())
