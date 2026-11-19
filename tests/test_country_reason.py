"""Which of the store's two notes a home reads."""

from __future__ import annotations

import pytest

from custom_components.utility_tariffs.country_reason import reason_for

ROW = {"reason": "English", "reason_local": {"language": "pt", "text": "Português"}}


@pytest.mark.parametrize(
    ("language", "expected"),
    [("pt", "Português"), ("pt-BR", "Português"), ("PT-pt", "Português"), ("en", "English"),
     ("fr", "English")],
)
def test_the_local_note_is_read_only_in_its_own_language(language: str, expected: str) -> None:
    assert reason_for(ROW, language) == expected


def test_a_country_with_no_local_note_reads_english() -> None:
    assert reason_for({"reason": "English"}, "fr") == "English"


def test_a_country_with_no_note_reads_nothing() -> None:
    assert reason_for({}, "fr") is None
    assert reason_for(None, "fr") is None
