"""The release reads one version and its notes, so the places that state it must agree."""

from __future__ import annotations

import json
import re
import tomllib

from scripts.release_notes import section
from tests.helpers import PKG, ROOT

VERSION = re.compile(r"^\d+\.\d+\.\d+((a|b|rc)\d+)?$")


def _manifest_version() -> str:
    return str(json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))["version"])


def test_the_manifest_version_is_one_a_release_can_tag() -> None:
    assert VERSION.match(_manifest_version())


def test_pyproject_and_the_manifest_state_the_same_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == _manifest_version()


def test_the_changelog_has_notes_for_the_manifest_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert section(changelog, _manifest_version())


def test_a_section_stops_at_the_next_heading() -> None:
    text = "# Changelog\n\n## 1.1.0\n\nNew.\n\n## 1.0.0\n\nFirst.\n"
    assert section(text, "1.1.0") == "New."
    assert section(text, "1.0.0") == "First."
    assert section(text, "2.0.0") == ""
