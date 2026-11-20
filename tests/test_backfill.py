"""The history filled from the meters' long-term statistics, and the rules it keeps."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from utility_tariffs_lib.tariff import SlotEnergy, SlotHistory

from custom_components.utility_tariffs.backfill import Filler, Hour, slot_totals
from custom_components.utility_tariffs.const import (
    CONF_EXPORT_ENERGY,
    CONF_HISTORY_START,
    CONF_IMPORT_ENERGY,
    DOMAIN,
    METER_TARGETS,
)
from tests.test_sensor import NOON, _setup

DUBLIN = ZoneInfo("Europe/Dublin")
METER = "sensor.meter_in"
OUT = "sensor.meter_out"
DAY = date(2026, 11, 13)
FIRST = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)  # 06:00 in Dublin in November


@pytest.fixture(autouse=True)
def _enable_custom_integrations(recorder_mock: object, enable_custom_integrations: None) -> None:
    """Start the recorder before `hass`."""


def _hours(*kwh: float, start: datetime = FIRST) -> list[Hour]:
    return [Hour(start + timedelta(hours=n), value) for n, value in enumerate(kwh)]


def _fill(
    history: SlotHistory, hours: dict[str, list[Hour]], marks: dict[date, set[int]] | None = None
) -> tuple[dict[date, set[int]], int]:
    marks = {} if marks is None else marks
    filler = Filler(history, marks, METER_TARGETS, CONF_IMPORT_ENERGY)
    return marks, filler.fill(slot_totals(hours, DUBLIN, 100.0)).slots


def test_an_hour_is_spread_over_its_two_half_hours() -> None:
    history = SlotHistory(DUBLIN)
    _, slots = _fill(history, {CONF_IMPORT_ENERGY: _hours(2.0)})

    day = history.get(DAY)
    assert slots == 2
    assert day is not None
    assert day.flows["import"][12:14] == [1.0, 1.0]
    assert day.seconds[12:14] == [1800.0, 1800.0]
    assert day.flows["import"][11] == 0.0


def test_the_other_meters_fill_beside_the_import() -> None:
    history = SlotHistory(DUBLIN)
    _fill(history, {CONF_IMPORT_ENERGY: _hours(2.0), CONF_EXPORT_ENERGY: _hours(0.5)})

    day = history.get(DAY)
    assert day is not None
    assert day.flows["export"][12] == pytest.approx(0.25)


def test_a_half_hour_booked_live_is_never_overwritten() -> None:
    history = SlotHistory(DUBLIN)
    live = FIRST + timedelta(minutes=30)
    history.record(SlotEnergy(flows={"import": 0.4}), live, live + timedelta(minutes=30))

    marks, slots = _fill(history, {CONF_IMPORT_ENERGY: _hours(2.0)})

    day = history.get(DAY)
    assert day is not None
    assert slots == 1
    assert day.flows["import"][12:14] == [1.0, 0.4]
    assert marks[DAY] == {12}


def test_a_second_run_replaces_what_it_filled_and_does_not_add_to_it() -> None:
    history = SlotHistory(DUBLIN)
    marks, _ = _fill(history, {CONF_IMPORT_ENERGY: _hours(2.0)})
    _fill(history, {CONF_IMPORT_ENERGY: _hours(4.0)}, marks)

    day = history.get(DAY)
    assert day is not None
    assert day.flows["import"][12:14] == [2.0, 2.0]
    assert day.seconds[12] == 1800.0


def test_a_new_meter_is_added_by_running_again() -> None:
    history = SlotHistory(DUBLIN)
    marks, _ = _fill(history, {CONF_IMPORT_ENERGY: _hours(2.0)})
    _fill(history, {CONF_IMPORT_ENERGY: _hours(2.0), CONF_EXPORT_ENERGY: _hours(1.0)}, marks)

    day = history.get(DAY)
    assert day is not None
    assert day.flows["export"][12] == pytest.approx(0.5)
    assert day.flows["import"][12] == pytest.approx(1.0)


def test_an_hour_no_supply_could_deliver_is_left_unread() -> None:
    history = SlotHistory(DUBLIN)
    _, slots = _fill(history, {CONF_IMPORT_ENERGY: _hours(1.0, 500.0, -3.0)})

    assert slots == 2  # only the first hour


def test_an_hour_without_a_figure_is_not_counted_as_zero() -> None:
    history = SlotHistory(DUBLIN)
    gap = [Hour(FIRST, 1.0), Hour(FIRST + timedelta(hours=2), 1.0)]
    _, slots = _fill(history, {CONF_IMPORT_ENERGY: gap})
    day = history.get(DAY)

    assert slots == 4
    assert day is not None
    assert day.seconds[14:16] == [0.0, 0.0]


def test_the_import_meter_decides_whether_a_half_hour_is_read() -> None:
    history = SlotHistory(DUBLIN)
    _, slots = _fill(history, {CONF_EXPORT_ENERGY: _hours(1.0)})

    assert slots == 0
    assert history.get(DAY) is None


def _import_statistics(hass: HomeAssistant, entity_id: str, start: datetime, rises: list[float]) -> None:
    total = 100.0
    # The first row of a meter has nothing before it, so it carries no change.
    rows = [StatisticData(start=start - timedelta(hours=1), sum=total, state=total)]
    for number, rise in enumerate(rises):
        total += rise
        rows.append(StatisticData(start=start + timedelta(hours=number), sum=total, state=total))
    meta = StatisticMetaData(
        source="recorder",
        statistic_id=entity_id,
        name=None,
        unit_of_measurement="kWh",
        unit_class="energy",
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
    )
    async_import_statistics(hass, meta, rows)


async def _history_of(hass: HomeAssistant, entry_id: str, day: date):  # type: ignore[no-untyped-def]
    accountant = hass.config_entries.async_get_entry(entry_id).runtime_data.accountant
    await hass.async_block_till_done()
    return accountant, accountant.store.history.get(day)


async def test_setup_fills_the_history_from_the_statistics(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    _import_statistics(hass, METER, FIRST, [2.0, 1.0])
    await async_wait_recording_done(hass)
    hass.states.async_set(METER, "102", {"unit_of_measurement": "kWh"})

    entry = await _setup(hass, options={CONF_IMPORT_ENERGY: METER})

    accountant, day = await _history_of(hass, entry.entry_id, DAY)
    assert day is not None
    assert day.flows["import"][12:16] == pytest.approx([1.0, 1.0, 0.5, 0.5])
    assert accountant.last_backfill.slots == 6  # the hour before the first rise counts too


async def test_the_start_of_history_in_the_options_limits_the_fill(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    _import_statistics(hass, METER, FIRST, [2.0])
    await async_wait_recording_done(hass)
    hass.states.async_set(METER, "102", {"unit_of_measurement": "kWh"})

    entry = await _setup(
        hass, options={CONF_IMPORT_ENERGY: METER, CONF_HISTORY_START: "2026-11-14"}
    )

    _, day = await _history_of(hass, entry.entry_id, DAY)
    assert day is None


async def test_the_action_fills_again_and_answers_with_what_it_did(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    hass.states.async_set(METER, "100", {"unit_of_measurement": "kWh"})
    entry = await _setup(hass, options={CONF_IMPORT_ENERGY: METER})
    _import_statistics(hass, METER, FIRST, [2.0])
    await async_wait_recording_done(hass)

    answer = await hass.services.async_call(
        DOMAIN,
        "backfill",
        {"config_entry_id": entry.entry_id, "start": "2026-11-13"},
        blocking=True,
        return_response=True,
    )

    assert answer == {"half_hours_filled": 4, "first_day": "2026-11-13", "last_day": "2026-11-13"}


async def test_the_action_needs_a_meter(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    from homeassistant.exceptions import ServiceValidationError

    freezer.move_to(NOON)
    entry = await _setup(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "backfill", {"config_entry_id": entry.entry_id}, blocking=True,
            return_response=True,
        )


async def test_what_was_filled_is_kept_across_a_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    _import_statistics(hass, METER, FIRST, [2.0])
    await async_wait_recording_done(hass)
    hass.states.async_set(METER, "102", {"unit_of_measurement": "kWh"})
    entry = await _setup(hass, options={CONF_IMPORT_ENERGY: METER})
    accountant, _ = await _history_of(hass, entry.entry_id, DAY)
    await accountant.store.async_save()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    accountant, day = await _history_of(hass, entry.entry_id, DAY)
    assert accountant.store.backfilled[DAY] == {10, 11, 12, 13}
    assert day is not None
    assert day.flows["import"][12] == pytest.approx(1.0)
