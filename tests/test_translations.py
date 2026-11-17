"""Every translation follows strings.json: same keys, same placeholders, nothing left empty."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from tests.helpers import PKG

PLACEHOLDER = re.compile(r"\{\w+\}")
LANGUAGES = ("fr", "da", "pt", "ga")


def _flatten(node: Any, prefix: str = "") -> dict[str, str]:
    if isinstance(node, dict):
        out: dict[str, str] = {}
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
        return out
    return {prefix: node}


def _load(name: str) -> dict[str, str]:
    path = PKG / name
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def test_english_translation_is_a_copy_of_strings() -> None:
    assert _load("translations/en.json") == _load("strings.json")


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_translation_has_every_key_and_no_extra(language: str) -> None:
    assert _load(f"translations/{language}.json").keys() == _load("strings.json").keys()


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_translation_keeps_every_placeholder(language: str) -> None:
    english = _load("strings.json")
    for key, text in _load(f"translations/{language}.json").items():
        assert text.strip(), key
        assert sorted(PLACEHOLDER.findall(text)) == sorted(PLACEHOLDER.findall(english[key])), key
