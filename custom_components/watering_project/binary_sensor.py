"""Binary sensors: per-plant "needs water" plus an aggregate."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENTITY_NEEDS_WATER, ENTITY_PLANTS_NEED_WATER, STATUS_NO_DATA
from .entity import WateringAggregateEntity, WateringPlantEntity, WateringPlatformManager
from .evaluate import WateringCoordinator, WateringRuntime

WATER_ALERT_ICON = "mdi:water-alert"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[WateringRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up plant and aggregate binary sensors."""
    coordinator = entry.runtime_data.coordinator

    manager = _NeedsWaterManager(coordinator, async_add_entities)
    entry.async_on_unload(manager.async_setup())

    async_add_entities([PlantsNeedWaterBinarySensor(coordinator)])


class PlantNeedsWaterBinarySensor(WateringPlantEntity, BinarySensorEntity):
    """``on`` while the plant is dry."""

    _attr_translation_key = ENTITY_NEEDS_WATER
    _attr_icon = WATER_ALERT_ICON

    def __init__(self, coordinator: WateringCoordinator, plant_id: str) -> None:
        """Initialise the sensor for one plant."""
        super().__init__(coordinator, plant_id, ENTITY_NEEDS_WATER)

    @property
    def fallback_name(self) -> str:
        """Device-less plants get an explicit name."""
        return "needs water"

    @property
    def is_on(self) -> bool:
        """Whether the plant currently needs water."""
        verdict = self._verdict
        return bool(verdict is not None and verdict.needs_water)

    @property
    def available(self) -> bool:
        """Unavailable when there is no usable reading.

        A plant with ``no_data`` must not read as "does not need water".
        """
        verdict = self._verdict
        return verdict is not None and verdict.status != STATUS_NO_DATA


class PlantsNeedWaterBinarySensor(WateringAggregateEntity, BinarySensorEntity):
    """Aggregate: ``on`` when at least one plant needs water."""

    _attr_translation_key = ENTITY_PLANTS_NEED_WATER
    _attr_icon = WATER_ALERT_ICON

    def __init__(self, coordinator: WateringCoordinator) -> None:
        """Initialise the aggregate sensor."""
        super().__init__(coordinator, ENTITY_PLANTS_NEED_WATER)

    @property
    def is_on(self) -> bool:
        """Whether any plant needs water."""
        return self.coordinator.any_needs_water


class _NeedsWaterManager(WateringPlatformManager):
    """Creates one binary sensor per discovered plant."""

    def build(self, plant_id: str) -> list[BinarySensorEntity]:
        """Build the platform entities for one plant."""
        return [PlantNeedsWaterBinarySensor(self.coordinator, plant_id)]
