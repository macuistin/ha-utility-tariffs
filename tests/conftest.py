"""Fixtures: a real Home Assistant, and a tariff store built on disk instead of the network."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from utility_tariffs_lib.tariffstore import AsyncFolderCache, AsyncStore, folder_reader

from custom_components.utility_tariffs import coordinator, plan_steps
from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess
from tests.helpers import async_reader
from tests.support.building import build_store
from tests.support.fixtures import flat, tariff, write_store


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load `custom_components/utility_tariffs`."""


@pytest.fixture
def use_store(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Callable[[Callable[[str], bytes] | None], Path]:
    """Point the integration at a small built store. Pass a reader to replace how it is read."""
    folder = write_store(tmp_path, {"p/plan/1.json": tariff(), "p/flat/1.json": flat()})
    build_store(folder)

    def use(reader: Callable[[str], bytes] | None = None) -> Path:
        store = AsyncStore(
            async_reader(reader or folder_reader(folder)), AsyncFolderCache(tmp_path / "cache")
        )
        access = TariffStoreAccess(hass, store, tmp_path / "cache")
        monkeypatch.setattr(plan_steps, "store_access", lambda _hass, _service="electricity": access)
        monkeypatch.setattr(coordinator, "store_access", lambda _hass, _service="electricity": access)
        return folder

    use()
    return use
