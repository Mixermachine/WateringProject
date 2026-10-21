"""Entity plumbing shared by the binary_sensor and sensor platforms."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .evaluate import WateringCoordinator

_LOGGER: Final = logging.getLogger(__name__)


def aggregate_device_info(entry_id: str) -> DeviceInfo:
    """Virtual service device that owns the aggregate entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Watering Project",
        manufacturer="Watering Project",
        model="Plant monitor",
        entry_type=DeviceEntryType.SERVICE,
    )


class WateringPlantEntity(Entity):
    """Base class for per-plant entities.

    Entities attach to the plant's **source device** when one exists, so they
    group under it in the UI and inherit its area. Device-less plants (MQTT or
    template sensors) fall back to a flat name, because ``DeviceInfo`` requires
    at least one identifier and every device-less plant would otherwise collide
    on the same suggested object id.

    State writes are skipped unless the verdict changed, so ``last_reported``
    keeps meaning "something happened" instead of "a minute passed".
    """

    _attr_should_poll = False
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator: WateringCoordinator,
        plant_id: str,
        entity_key: str,
    ) -> None:
        """Initialise one entity for one plant."""
        self.coordinator = coordinator
        self.plant_id = plant_id
        self.entity_key = entity_key

        hass = coordinator.hass
        device = dr.async_get(hass).async_get(plant_id)
        self._device_exists = device is not None
        self._device_identifiers = set(device.identifiers) if device is not None else None

        plant = coordinator.plant(plant_id)
        label = plant.label if plant is not None else plant_id
        if self._device_exists:
            self._attr_has_entity_name = True
        else:
            self._attr_has_entity_name = False
            self._attr_name = f"{label} {self.fallback_name}"

        self._last_verdict_version = -1

    @property
    def fallback_name(self) -> str:
        """Name suffix used for device-less plants."""
        return self.entity_key.replace("_", " ")

    @property
    def unique_id(self) -> str:
        """Stable across renames: keyed by entry, device-based plant id and kind."""
        return f"{DOMAIN}_{self.coordinator.entry.entry_id}_{self.plant_id}_{self.entity_key}"

    @property
    def _plant(self):
        return self.coordinator.plant(self.plant_id)

    @property
    def _verdict(self):
        return self.coordinator.verdict(self.plant_id)

    @property
    def available(self) -> bool:
        """Whether a verdict exists for this plant."""
        return self._verdict is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Attach to the source device when there is one."""
        if not self._device_exists or self._device_identifiers is None:
            return None
        plant = self._plant
        return DeviceInfo(
            identifiers=self._device_identifiers,
            name=plant.label if plant is not None else None,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))
        await super().async_added_to_hass()

    def _handle_update(self) -> None:
        if self._last_verdict_version == self.coordinator.verdict_version:
            return
        self._last_verdict_version = self.coordinator.verdict_version
        self.async_write_ha_state()


class WateringAggregateEntity(Entity):
    """Base class for the two aggregate entities."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: WateringCoordinator, entity_key: str) -> None:
        """Initialise an aggregate entity."""
        self.coordinator = coordinator
        self.entity_key = entity_key
        self._last_version = -1

    @property
    def unique_id(self) -> str:
        """Aggregate unique id, keyed by entry (single instance in v1)."""
        return f"{DOMAIN}_{self.coordinator.entry.entry_id}_aggregate_{self.entity_key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Aggregates live on their own service device."""
        return aggregate_device_info(self.coordinator.entry.entry_id)

    @property
    def available(self) -> bool:
        """Aggregates are always available once an evaluation ran."""
        return True

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))
        await super().async_added_to_hass()

    def _handle_update(self) -> None:
        if self._last_version == self.coordinator.verdict_version:
            return
        self._last_version = self.coordinator.verdict_version
        self.async_write_ha_state()


class WateringPlatformManager:
    """Create and remove entities as the discovered plant set changes."""

    def __init__(self, coordinator: WateringCoordinator, add_entities) -> None:
        """Initialise the manager for one platform."""
        self.coordinator = coordinator
        self._add_entities = add_entities
        self._known: dict[str, list[Entity]] = {}

    def build(self, plant_id: str) -> list[Entity]:
        """Create the platform's entities for one plant (overridden)."""
        raise NotImplementedError

    def async_setup(self) -> Callable[[], None]:
        """Register the sync callback and run it once."""
        self.sync()
        return self.coordinator.async_add_listener(self.sync)

    def sync(self) -> None:
        """Add entities for new plants, remove entities for vanished plants."""
        wanted = self.coordinator.plants

        for plant_id in list(self._known):
            if plant_id not in wanted:
                for entity in self._known.pop(plant_id):
                    self._remove_entity(entity)

        new_entities: list[Entity] = []
        for plant_id in wanted:
            if plant_id in self._known:
                continue
            entities = self.build(plant_id)
            self._known[plant_id] = entities
            new_entities.extend(entities)

        if new_entities:
            self._add_entities(new_entities)

    def _remove_entity(self, entity: Entity) -> None:
        """Remove one entity; ``Entity.async_remove`` is a coroutine."""
        self.coordinator.hass.async_create_task(entity.async_remove(force_remove=True))

    async def async_remove_all(self) -> None:
        """Remove every entity this manager created."""
        for entities in self._known.values():
            for entity in entities:
                await entity.async_remove(force_remove=True)
        self._known.clear()
