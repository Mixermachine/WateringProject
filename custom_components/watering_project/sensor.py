"""Sensors: per-plant status enum plus an aggregate count."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENTITY_PLANTS_NEEDING_WATER, ENTITY_STATUS, STATUS_ORDER
from .entity import WateringAggregateEntity, WateringPlantEntity, WateringPlatformManager
from .evaluate import WateringCoordinator, WateringRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[WateringRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up plant status sensors and the aggregate count."""
    coordinator = entry.runtime_data.coordinator

    manager = _StatusManager(coordinator, async_add_entities)
    entry.async_on_unload(manager.async_setup())

    async_add_entities([PlantsNeedingWaterSensor(coordinator)])


class PlantStatusSensor(WateringPlantEntity, SensorEntity):
    """Enum status per plant: suspect_battery / no_data / dry / healthy."""

    _attr_translation_key = ENTITY_STATUS
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = list(STATUS_ORDER)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WateringCoordinator, plant_id: str) -> None:
        """Initialise the status sensor for one plant."""
        super().__init__(coordinator, plant_id, ENTITY_STATUS)

    @property
    def fallback_name(self) -> str:
        """Device-less plants get an explicit name."""
        return "status"

    @property
    def native_value(self) -> str | None:
        """Current status value."""
        verdict = self._verdict
        return verdict.status if verdict is not None else None

    def _handle_update(self) -> None:
        """Status flips also matter when only the zero-day counter moved."""
        super()._handle_update()


class PlantsNeedingWaterSensor(WateringAggregateEntity, SensorEntity):
    """Aggregate count of plants that currently need water."""

    _attr_translation_key = ENTITY_PLANTS_NEEDING_WATER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: WateringCoordinator) -> None:
        """Initialise the aggregate count sensor."""
        super().__init__(coordinator, ENTITY_PLANTS_NEEDING_WATER)

    @property
    def native_value(self) -> int:
        """Number of plants needing water."""
        return self.coordinator.needs_water_count


class _StatusManager(WateringPlatformManager):
    """Creates one status sensor per discovered plant."""

    def build(self, plant_id: str) -> list[SensorEntity]:
        """Build the platform entities for one plant."""
        return [PlantStatusSensor(self.coordinator, plant_id)]
