"""Sensors for where the followed plan ranks among the store's plans."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass

from .coordinator import TariffCoordinator
from .entity import TariffEntity
from .plan_search import PlanRanking, attributes


class PlanRankSensor(TariffEntity, SensorEntity):
    """Where the followed plan stands: 1 is the cheapest for the last whole bill."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "plan_rank")
        self._attr_translation_key = "plan_rank"

    def _ranking(self) -> PlanRanking | None:
        ranker = self.coordinator.ranker
        return None if ranker is None else ranker.ranking

    @property
    def native_value(self) -> int | None:
        ranking = self._ranking()
        return None if ranking is None else ranking.current_rank

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        ranking = self._ranking()
        return None if ranking is None else attributes(ranking)


class CheapestPlanSavingSensor(TariffEntity, SensorEntity):
    """What the last whole bill would have saved on the cheapest plan. 0 when yours is cheapest."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "cheapest_plan_saving")
        self._attr_translation_key = "cheapest_plan_saving"
        self._attr_native_unit_of_measurement = coordinator.data.definition.currency

    @property
    def native_value(self) -> float | None:
        ranker = self.coordinator.ranker
        ranking = None if ranker is None else ranker.ranking
        return None if ranking is None else ranking.saving

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        ranker = self.coordinator.ranker
        ranking = None if ranker is None else ranker.ranking
        if ranking is None:
            return None
        return {
            "cheapest_plan": ranking.cheapest or None,
            "period_start": ranking.first_day.isoformat(),
            "period_end": ranking.last_day.isoformat(),
            "days_recorded": ranking.days_recorded,
        }
