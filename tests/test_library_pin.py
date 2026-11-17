"""The tariff library is pinned once, in the manifest, and the test environments install the same pin."""

from __future__ import annotations

import json
import re

from tests.helpers import PKG, ROOT

MARKER = "utility-tariffs-lib=="


def _pins(text: str) -> set[str]:
    return {line.strip() for line in text.splitlines() if line.startswith(MARKER)}


def test_the_manifest_pins_one_archive_of_the_library() -> None:
    requirements = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))["requirements"]
    assert len(requirements) == 1
    assert re.fullmatch(MARKER + r"\d+\.\d+\.\d+", requirements[0])


def test_both_test_environments_install_the_manifest_pin() -> None:
    manifest = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))["requirements"]
    for name in ("requirements-test.txt", "tests/requirements-floor.txt"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert _pins(text) == set(manifest), name
