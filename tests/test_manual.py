"""A tariff typed in by the household, from the flow to the sensors."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.utility_tariffs.const import DOMAIN
from tests.helpers import without_bands

BASE = {
    "name": "My plan",
    "country": "IE",
    "currency": "EUR",
    "base_rate_name": "Day",
    "base_rate": 0.30,
    "export_rate": 0.19,
    "standing_charge": 0.60,
    "levy": 1.5,
    "discount_rate": 0.0,
    "vat_rate": 9.0,
    "vat_included": False,
    "bill_start_day": 5,
}


async def _step(hass: HomeAssistant, result, user_input):
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def _to_base_form(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await _step(hass, result, {"country": "IE"})
    result = await _step(hass, result, {"tariff": "Type in my own rates"})
    assert result["step_id"] == "manual_template"
    return await _step(hass, result, {"template": "blank"})


async def _make(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Dublin")
    result = await _to_base_form(hass)
    result = await _step(hass, result, BASE)
    assert result["step_id"] == "manual_more"
    result = await _step(hass, result, {"next_step_id": "manual_period"})
    result = await _step(
        hass, result, {"name": "Night", "rate": 0.12, "start": "23:00:00", "end": "08:00:00"}
    )
    result = await _step(hass, result, {"next_step_id": "manual_done"})
    result = await _step(hass, result, {})  # the meters and bill dates page, left empty
    await hass.async_block_till_done()
    return result


async def test_own_rates_make_an_entry_that_prices_the_day(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to("2026-11-14 12:00:00+00:00")
    result = await _make(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My plan"
    assert result["data"]["manual"]["periods"][0]["name"] == "Night"
    assert result["data"]["entity_key"] == "manual"
    assert hass.states.get("sensor.utility_tariff_import_price").state == "0.327"
    assert hass.states.get("sensor.utility_tariff_export_price").state == "0.19"
    assert hass.states.get("sensor.utility_tariff_import_rate_band").state == "Day"


async def test_the_timed_rate_applies_at_night(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to("2026-11-14 23:30:00+00:00")
    await _make(hass)

    assert hass.states.get("sensor.utility_tariff_import_price").state == "0.1308"
    assert hass.states.get("sensor.utility_tariff_import_rate_band").state == "Night"


async def test_a_bad_currency_is_refused_with_the_form_kept(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _to_base_form(hass)
    result = await _step(hass, result, {**BASE, "currency": "euros"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_tariff"}


async def test_a_period_that_starts_and_ends_together_is_refused(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _to_base_form(hass)
    result = await _step(hass, result, BASE)
    result = await _step(hass, result, {"next_step_id": "manual_period"})
    result = await _step(
        hass, result, {"name": "Night", "rate": 0.1, "start": "01:00:00", "end": "01:00:00"}
    )

    assert result["errors"] == {"base": "empty_period"}


async def test_a_period_that_cannot_be_written_down_is_refused(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _to_base_form(hass)
    result = await _step(hass, result, BASE)
    result = await _step(hass, result, {"next_step_id": "manual_period"})
    result = await _step(
        hass, result, {"name": "", "rate": 0.1, "start": "01:00:00", "end": "02:00:00"}
    )

    assert result["errors"] == {"base": "invalid_tariff"}


async def test_a_store_plan_can_be_swapped_for_own_rates_and_keep_its_entities(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    from homeassistant.config_entries import SOURCE_RECONFIGURE
    from homeassistant.helpers import entity_registry as er

    freezer.move_to("2026-11-14 12:00:00+00:00")
    await hass.config.async_set_time_zone("Europe/Dublin")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    for key, value in (("country", "IE"), ("tariff", "P Energy \u2013 Flat")):
        result = await _step(hass, result, {key: value})
    result = await _step(hass, result, {})
    entry = result["result"]
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await _step(hass, result, {"country": "IE"})
    result = await _step(hass, result, {"tariff": "Type in my own rates"})
    result = await _step(hass, result, {"template": "blank"})
    result = await _step(hass, result, BASE)
    result = await _step(hass, result, {"next_step_id": "manual_done"})
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert "manual" in entry.data and "tariff" not in entry.data
    after = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert without_bands(after) == without_bands(before)
    assert hass.states.get("sensor.utility_tariff_import_price").state == "0.327"


@pytest.mark.parametrize(
    ("template", "base_name", "timed"),
    [
        ("flat", "All day", None),
        ("day_night", "Day", ("Night", "23:00:00", "08:00:00")),
        ("peak_offpeak", "Off-peak", ("Peak", "17:00:00", "19:00:00")),
        ("cheap_midday", "Day", ("Midday", "11:00:00", "15:00:00")),
        ("cheap_overnight", "Day", ("Overnight", "02:00:00", "06:00:00")),
    ],
)
async def test_each_template_fills_the_form_and_makes_a_valid_tariff(
    hass: HomeAssistant,
    use_store: Callable[..., Path],
    template: str,
    base_name: str,
    timed: tuple[str, str, str] | None,
) -> None:
    from custom_components.utility_tariffs.manual import problem_with

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await _step(hass, result, {"country": "IE"})
    result = await _step(hass, result, {"tariff": "Type in my own rates"})
    result = await _step(hass, result, {"template": template})
    fields = {str(key): key for key in result["data_schema"].schema}
    assert fields["base_rate_name"].default() == base_name
    assert ("timed_rate" in fields) == (timed is not None)

    typed = {**BASE, "base_rate_name": base_name}
    if timed is not None:
        typed["timed_rate"] = 0.12
    result = await _step(hass, result, typed)
    assert result["step_id"] == "manual_more"
    result = await _step(hass, result, {"next_step_id": "manual_done"})
    result = await _step(hass, result, {})
    saved = result["data"]["manual"]
    assert problem_with(saved, "My plan") is None
    expected = []
    if timed is not None:
        expected = [{"name": timed[0], "start": timed[1], "end": timed[2], "rate": 0.12}]
    assert [
        {k: p[k] for k in ("name", "start", "end", "rate")} for p in saved["periods"]
    ] == expected
    assert "timed_rate" not in saved


async def test_a_template_price_that_cannot_be_used_keeps_the_form(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await _step(hass, result, {"country": "IE"})
    result = await _step(hass, result, {"tariff": "Type in my own rates"})
    result = await _step(hass, result, {"template": "day_night"})

    result = await _step(hass, result, {**BASE, "currency": "??", "timed_rate": 0.1})

    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "invalid_tariff"}
