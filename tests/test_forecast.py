"""The price forecast: a fixed tariff over a revision, and a tariff on a half-hourly price feed."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number import SERVICE_SET_VALUE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from utility_tariffs_lib.tariffstore import (
    AsyncMemoryCache,
    AsyncPriceStore,
    AsyncStore,
    folder_reader,
    prices,
)

from custom_components.utility_tariffs import coordinator
from custom_components.utility_tariffs.const import DOMAIN
from custom_components.utility_tariffs.helper.store_access import PriceStoreAccess
from tests.helpers import async_reader
from tests.support.building import build_store
from tests.support.fixtures import flat, write_store
from tests.test_sensor import DATA, NOON, _setup, _state

AGILE_BILL = {"total": {
    "kind": "tax", "name": "VAT", "mode": "included", "percent": "$country.vat_percent",
    "of": {"kind": "sum", "of": {
        "energy": {"kind": "series_energy", "series": "octopus_agile"},
        "standing": {"kind": "per_day"}}}}}
FEED = {**DATA, "tariff": "agile", "area": "all", "name": "P Agile"}
EVENING = "2026-11-14 17:30:00+00:00"
FIRST_DAY = date(2026, 10, 17)  # 28 days before the 14th


def day_prices(day: date) -> list[str]:
    """0.10 from 00:00 to 06:00, 0.40 from 16:00 to 19:00, else 0.25. The day the clocks go back
    (25 October) has two more half hours, as a real feed would."""
    extra = ["0.25"] * 2 if day == date(2026, 10, 25) else []
    return ["0.10"] * 12 + ["0.25"] * 20 + ["0.40"] * 6 + ["0.25"] * 10 + extra


def day_file(day: date) -> bytes:
    return prices.dumps_day({
        "schema": 1, "feed": "octopus-agile", "area": "all", "date": day.isoformat(),
        "timezone": "Europe/Dublin", "interval_minutes": 30, "prices": day_prices(day)}).encode()


class Feed:
    """The day files a price feed holds, which a test can add to as time passes."""

    def __init__(self, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
        self.days: dict[str, bytes] = {}

        def read(path: str) -> bytes:
            try:
                return self.days[path]
            except KeyError:
                raise OSError("404") from None

        access = PriceStoreAccess(hass, AsyncPriceStore(async_reader(read), AsyncMemoryCache()))
        monkeypatch.setattr(coordinator, "price_access", lambda _hass: access)

    def publish(self, first: date, last: date) -> None:
        day = first
        while day <= last:
            self.days[prices.day_path("IE", "octopus-agile", "all", day)] = day_file(day)
            day += timedelta(days=1)


@pytest.fixture
def feed(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Feed:
    files = {"p/flat/1.json": flat(), "p/flat/2.json": flat("0.3", "2026-11-20"),
             "p/agile/1.json": flat("1", bill=AGILE_BILL)}
    folder = write_store(tmp_path, files)
    build_store(folder)
    store = AsyncStore(async_reader(folder_reader(folder)), AsyncMemoryCache())
    from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess

    access = TariffStoreAccess(hass, store)
    monkeypatch.setattr(coordinator, "store_access", lambda _hass: access)
    from custom_components.utility_tariffs import config_flow

    monkeypatch.setattr(config_flow, "store_access", lambda _hass: access)
    return Feed(hass, monkeypatch)


def attributes(hass: HomeAssistant, key: str) -> dict:
    state = hass.states.get(f"sensor.utility_tariff_{key}")
    assert state is not None, key
    return dict(state.attributes)


FLAT = {**DATA, "tariff": "flat", "area": "all", "name": "P Flat"}


async def test_a_fixed_tariff_is_forecast_over_a_revision_the_store_already_holds(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, FLAT)

    assert _state(hass, "price_forecast") == "2026-11-28T00:00:00+00:00"
    assert _state(hass, "next_tariff_change") == "2026-11-20T00:00:00+00:00"
    change = attributes(hass, "next_tariff_change")
    assert change["import_prices_before"] == {"All day": 0.25}
    assert change["import_prices_after"] == {"All day": 0.3}
    forecast = attributes(hass, "price_forecast")
    assert forecast["complete"] is True
    assert forecast["changes"] == [
        {"effective_from": "2026-11-20", "import_prices": {"All day": 0.3}}]
    assert {row["source"] for row in forecast["slots"]} == {"fixed"}
    assert forecast["slots"][-1]["price"] == 0.25  # 48 hours from now is before the change
    assert hass.states.get("sensor.utility_tariff_price_level") is None  # fixed prices


async def test_the_price_now_follows_the_revision_when_it_starts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    freezer.move_to("2026-11-19 23:59:00+00:00")
    await _setup(hass, FLAT)
    assert _state(hass, "import_price") == "0.25"

    freezer.move_to("2026-11-20 00:00:30+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, "import_price") == "0.3"
    assert _state(hass, "next_tariff_change") == "unknown"


async def test_a_feed_tariff_shows_the_published_prices_and_where_they_stop(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 14))  # tomorrow is not published yet
    freezer.move_to(NOON)
    await _setup(hass, FEED)

    assert _state(hass, "import_price") == "0.25"
    assert _state(hass, "price_forecast") == "2026-11-15T00:00:00+00:00"
    forecast = attributes(hass, "price_forecast")
    assert forecast["complete"] is False  # the second day is missing
    assert {row["source"] for row in forecast["slots"]} == {"published"}
    assert forecast["slots"][-1]["end"] == "2026-11-15T00:00:00+00:00"  # nothing is invented


async def test_tomorrows_prices_are_read_again_through_the_afternoon(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 14))
    freezer.move_to("2026-11-14 15:50:00+00:00")
    await _setup(hass, FEED)
    assert _state(hass, "price_forecast") == "2026-11-15T00:00:00+00:00"

    feed.publish(date(2026, 11, 15), date(2026, 11, 15))
    freezer.move_to("2026-11-14 16:02:30+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _state(hass, "price_forecast") == "2026-11-16T00:00:00+00:00"
    assert attributes(hass, "price_forecast")["complete"] is True


async def test_the_level_and_the_next_low_and_high_price_follow_the_percentiles(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 15))
    freezer.move_to(EVENING)  # 17:30, in the dear stretch
    await _setup(hass, FEED)

    assert _state(hass, "import_price") == "0.4"
    assert _state(hass, "price_level") == "high"
    assert attributes(hass, "price_level")["basis"] == "history"
    history = attributes(hass, "price_forecast")["history_percentiles"]
    assert history == {"p10": 0.25, "p50": 0.4, "p90": 0.4, "days": 28}
    assert _state(hass, "next_low_price") == "2026-11-15T00:00:00+00:00"
    low = attributes(hass, "next_low_price")
    assert (low["ends"], low["price"], low["threshold"], low["percentile"]) == (
        "2026-11-15T06:00:00+00:00", 0.1, 0.1, 10)
    assert _state(hass, "next_high_price") == "2026-11-14T17:30:00+00:00"  # it is high now


async def test_the_level_uses_the_forecast_until_there_is_a_week_of_history(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    feed.publish(date(2026, 11, 13), date(2026, 11, 15))
    freezer.move_to(EVENING)
    await _setup(hass, FEED)

    assert attributes(hass, "price_forecast")["history_percentiles"] is None
    assert attributes(hass, "price_level")["basis"] == "forecast"
    assert _state(hass, "price_level") == "high"


async def test_changing_a_percentile_moves_what_counts_as_low_with_no_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 15))
    freezer.move_to(EVENING)
    entry = await _setup(hass, FEED)
    assert attributes(hass, "next_low_price")["threshold"] == 0.1

    await hass.services.async_call(
        NUMBER_DOMAIN, SERVICE_SET_VALUE,
        {"entity_id": "number.utility_tariff_low_price_percentile", "value": 40}, blocking=True,
    )
    await hass.async_block_till_done()

    assert entry.options["low_percentile"] == 40
    low = attributes(hass, "next_low_price")
    assert (low["threshold"], low["percentile"]) == (0.25, 40)  # the 40th price known is 0.25
    assert _state(hass, "next_low_price") == "2026-11-14T19:00:00+00:00"  # 0.25 is low enough now
    assert float(hass.states.get("number.utility_tariff_high_price_percentile").state) == 90


@pytest.mark.parametrize("published", [False, True])
async def test_a_repair_is_raised_when_tomorrow_is_still_missing_late_in_the_evening(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed, published: bool
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 15) if published else date(2026, 11, 14))
    freezer.move_to("2026-11-14 22:30:00+00:00")
    entry = await _setup(hass, FEED)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"prices_not_published_{entry.entry_id}")
    assert (issue is not None) is (not published)


async def test_get_prices_names_the_source_of_each_price_and_how_far_they_are_known(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 14))
    freezer.move_to(NOON)
    entry = await _setup(hass, FEED)

    reply = await hass.services.async_call(
        DOMAIN, "get_prices", {"config_entry_id": entry.entry_id, "end": "2026-11-16 00:00:00"},
        blocking=True, return_response=True,
    )

    assert reply["complete"] is False
    assert reply["known_until"] == "2026-11-15T00:00:00+00:00"
    assert {row["source"] for row in reply["prices"]} == {"published"}
    assert json.dumps(reply)  # plain values only


async def test_the_windows_are_still_searched_over_today_and_tomorrow_only(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    """The dearer revision from the 20th is held, but a window is for the next day or so."""
    freezer.move_to(NOON)
    entry = await _setup(hass, FLAT)

    assert _state(hass, "dearest_window_start") < "2026-11-16"
    reply = await hass.services.async_call(
        DOMAIN, "find_window",
        {"config_entry_id": entry.entry_id, "duration": "01:00:00", "highest": True},
        blocking=True, return_response=True,
    )
    assert reply["found"] is True and reply["start"] < "2026-11-16"


@pytest.mark.parametrize("published", [False, True])
async def test_tomorrow_available_follows_what_the_feed_has_published(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed, published: bool
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 15) if published else date(2026, 11, 14))
    freezer.move_to(EVENING)
    await _setup(hass, FEED)

    state = hass.states.get("binary_sensor.utility_tariff_tomorrow_s_prices_available")
    assert state is not None
    assert state.state == ("on" if published else "off")


async def test_a_two_band_tariff_gives_a_handful_of_rate_rows_in_the_evcc_shape(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: object
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    rows = attributes(hass, "price_forecast")["import_rates"]

    assert rows == [
        {"start": "2026-11-14T00:00:00+00:00", "end": "2026-11-14T08:00:00+00:00", "value": 0.15},
        {"start": "2026-11-14T08:00:00+00:00", "end": "2026-11-14T23:00:00+00:00", "value": 0.3},
        {"start": "2026-11-14T23:00:00+00:00", "end": "2026-11-15T08:00:00+00:00", "value": 0.15},
        {"start": "2026-11-15T08:00:00+00:00", "end": "2026-11-15T23:00:00+00:00", "value": 0.3},
        {"start": "2026-11-15T23:00:00+00:00", "end": "2026-11-16T00:00:00+00:00", "value": 0.15},
    ]


async def test_the_export_rates_follow_the_export_price(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, FLAT)

    [row] = attributes(hass, "price_forecast")["export_rates"]

    assert (row["start"], row["end"]) == ("2026-11-14T00:00:00+00:00", "2026-11-16T00:00:00+00:00")
    assert row["value"] == 0.0


async def test_a_feed_tariff_stays_far_below_the_recorder_limit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 15))
    freezer.move_to(EVENING)
    await _setup(hass, FEED)

    forecast = attributes(hass, "price_forecast")

    assert len(forecast["import_rates"]) > 4  # a price per band change, not per half hour
    assert len(json.dumps(forecast)) < 16384
    assert forecast["slots"][0]["export_price"] == 0.0


async def test_tomorrows_figures_are_unknown_until_tomorrow_is_priced(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, feed: Feed
) -> None:
    feed.publish(FIRST_DAY, date(2026, 11, 14))  # tomorrow is not published yet
    freezer.move_to(EVENING)
    entry = await _setup(hass, FEED)
    registry = er.async_get(hass)
    registry.async_update_entity("sensor.utility_tariff_lowest_import_price_tomorrow", disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "lowest_import_price_tomorrow") == "unknown"

    feed.publish(date(2026, 11, 15), date(2026, 11, 15))
    freezer.move_to("2026-11-14 18:02:30+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _state(hass, "lowest_import_price_tomorrow") == "0.1"
