"""Choosing a tariff from the store, against a real flow manager."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from utility_tariffs_lib.tariffstore import folder_reader

from custom_components.utility_tariffs.const import DOMAIN
from tests.support.building import build_store
from tests.support.fixtures import flat, tariff, write_store


async def _start(hass: HomeAssistant):
    """Open the flow at its first page, the country."""
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_a_plan_with_areas_is_chosen_in_three_pages(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _start(hass)
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "IE"})
    assert result["step_id"] == "plan"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tariff": "p/plan"}
    )
    assert result["step_id"] == "area"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"area": "urban"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "P Energy Plan (Urban)"
    assert result["data"] == {
        "country": "IE",
        "provider": "p",
        "tariff": "plan",
        "area": "urban",
        "name": "P Energy Plan (Urban)",
        "entity_key": "IE/p/plan/urban",
    }
    assert result["result"].unique_id == "IE/p/plan/urban"


async def test_the_pages_say_where_the_person_is_and_what_comes_next(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _start(hass)
    assert result["description_placeholders"] == {"step": "1"}
    assert result["last_step"] is False
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "IE"})
    assert result["step_id"] == "plan"
    assert result["description_placeholders"]["step"] == "2"
    assert result["description_placeholders"]["country_note"] == ""
    options = result["data_schema"].schema["tariff"].config["options"]
    assert [o["label"] for o in options] == ["P Energy \u2013 Flat", "P Energy \u2013 Plan"]


async def test_a_partial_country_shows_its_reason_as_text_on_the_plan_page(
    hass: HomeAssistant, use_store: Callable[..., Path], tmp_path: Path
) -> None:
    from tests.support.fixtures import country

    block = {**country(), "availability": "partial", "reason": "Only the energy price is held."}
    folder = write_store(
        tmp_path / "partial", {"p/plan/1.json": tariff(), "p/flat/1.json": flat()}, block
    )
    build_store(folder)
    use_store(folder_reader(folder))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "IE"})

    assert "Only the energy price is held." in result["description_placeholders"]["country_note"]


async def test_the_country_starts_at_the_home_country_when_the_store_holds_it(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    await hass.config.async_update(country="IE")
    result = await _start(hass)
    key = next(k for k in result["data_schema"].schema if k == "country")

    assert key.description == {"suggested_value": "IE"}


async def test_a_country_must_be_chosen_unless_own_rates_are_ticked(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "choose_country"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"own_rates": True}
    )
    assert result["step_id"] == "manual"


async def test_the_area_page_names_the_plan(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _to(hass, ("country", "IE"), ("tariff", "p/plan"))

    assert result["step_id"] == "area"
    assert result["description_placeholders"] == {"step": "3", "plan": "P Energy Plan"}


async def test_a_plan_with_one_price_skips_the_area_step(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "IE"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"tariff": "p/flat"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "P Energy Flat"
    assert result["data"]["area"] == "all"


async def test_only_one_tariff_can_be_followed(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="IE/p/flat/all", data={}).add_to_hass(hass)
    result = await _start(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_only_countries_the_store_holds_are_offered(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _start(hass)
    selector = result["data_schema"].schema["country"]
    assert selector.config["countries"] == ["IE"]  # the store also lists one it has no tariffs for


async def test_an_unreachable_store_with_nothing_cached_aborts(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    def unreachable(path: str) -> bytes:
        raise OSError("no network")

    use_store(unreachable)
    result = await _start(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def _reconfigure(hass: HomeAssistant, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def _to(hass: HomeAssistant, *steps: tuple[str, str]):
    result = await _start(hass)
    for key, value in steps:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {key: value})
    return result


async def test_a_store_that_fails_after_the_country_aborts_at_the_supplier(
    hass: HomeAssistant, use_store: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from utility_tariffs_lib.tariffstore import StoreError

    from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess

    async def fail(self, *args, **kwargs):
        raise StoreError("down")

    monkeypatch.setattr(TariffStoreAccess, "async_providers", fail)
    result = await _to(hass, ("country", "IE"))

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_a_store_that_fails_when_listing_plans_aborts(
    hass: HomeAssistant, use_store: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from utility_tariffs_lib.tariffstore import StoreError

    from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess

    async def fail(self, *args, **kwargs):
        raise StoreError("down")

    monkeypatch.setattr(TariffStoreAccess, "async_tariffs", fail)
    result = await _to(hass, ("country", "IE"))

    assert result["reason"] == "cannot_connect"


async def test_a_supplier_with_no_plan_in_force_aborts(
    hass: HomeAssistant, use_store: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess

    async def none(self, *args, **kwargs):
        return {}

    monkeypatch.setattr(TariffStoreAccess, "async_tariffs", none)
    result = await _to(hass, ("country", "IE"))

    assert result["reason"] == "no_tariffs"


async def test_a_plan_whose_file_cannot_be_read_aborts_at_the_area(
    hass: HomeAssistant, use_store: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from utility_tariffs_lib.tariffstore import StoreError

    from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess

    async def fail(self, *args, **kwargs):
        raise StoreError("down")

    monkeypatch.setattr(TariffStoreAccess, "async_areas", fail)
    result = await _to(hass, ("country", "IE"), ("tariff", "p/plan"))

    assert result["reason"] == "cannot_connect"


async def test_changing_plan_keeps_the_entities_and_their_ids(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    from homeassistant.helpers import entity_registry as er

    first = await _to(
        hass, ("country", "IE"), ("tariff", "p/plan"), ("area", "urban")
    )
    entry = first["result"]
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert before

    result = await _reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"own_rates": False}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "IE"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"tariff": "p/flat"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "IE/p/flat/all"
    assert entry.data["tariff"] == "flat"
    assert entry.title == "P Energy Flat"
    after = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert after == before


async def test_an_entry_made_before_the_entity_key_keeps_its_entities(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    from homeassistant.helpers import entity_registry as er

    old = MockConfigEntry(
        domain=DOMAIN,
        unique_id="IE/p/plan/urban",
        data={
            "country": "IE",
            "provider": "p",
            "tariff": "plan",
            "area": "urban",
            "name": "P Energy Plan (Urban)",
        },
    )
    old.add_to_hass(hass)
    await hass.config_entries.async_setup(old.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(registry, old.entry_id)
    }
    assert all(uid.startswith("IE/p/plan/urban_") for uid in before)

    result = await _reconfigure(hass, old)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"own_rates": False}
    )
    for key, value in (("country", "IE"), ("tariff", "p/flat")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {key: value})
    await hass.async_block_till_done()

    assert old.data["entity_key"] == "IE/p/plan/urban"
    after = {
        e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(registry, old.entry_id)
    }
    assert after == before


async def test_changing_to_a_plan_already_followed_is_refused(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    # Entries made before the single-tariff rule can still exist side by side.
    MockConfigEntry(domain=DOMAIN, unique_id="IE/p/flat/all", data={}).add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, unique_id="IE/p/plan/urban", data={"entity_key": "x"})
    other.add_to_hass(hass)
    result = await _reconfigure(hass, other)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"own_rates": False}
    )
    for key, value in (("country", "IE"), ("tariff", "p/flat")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {key: value})

    assert result["reason"] == "already_configured"


async def test_the_bill_dates_are_saved_as_options(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _to(hass, ("country", "IE"), ("tariff", "p/flat"))
    entry = result["result"]
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "window_minutes": 120,
            "bill_start_day": 16,
            "bill_months": "2",
            "bill_start_month": 2,
        },
    )

    assert flow["type"] is FlowResultType.CREATE_ENTRY
    assert flow["data"]["bill_start_day"] == 16
    assert flow["data"]["bill_months"] == 2
    assert flow["data"]["bill_start_month"] == 2
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
