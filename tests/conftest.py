"""Fixtures: a real Home Assistant, and a tariff store built on disk instead of the network."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

from custom_components.utility_tariffs import config_flow, coordinator
from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess
from custom_components.utility_tariffs.lib.tariffstore import FolderCache, Store, folder_reader
from tests.lib.tariffstore.building import build_store
from tests.lib.tariffstore.fixtures import flat, tariff, write_store


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
        store = Store(reader or folder_reader(folder), FolderCache(tmp_path / "cache"))
        access = TariffStoreAccess(hass, store)
        monkeypatch.setattr(config_flow, "store_access", lambda _hass: access)
        monkeypatch.setattr(coordinator, "store_access", lambda _hass: access)
        return folder

    use()
    return use
