"""The store's note on what a country is missing, in the home's language when the store has it."""

from __future__ import annotations

from typing import Any


def reason_for(row: dict[str, Any] | None, language: str) -> str | None:
    """The country's own-language note when it matches the home language, else the English one.

    The store holds English plus at most one other language, so a home in any third language
    reads the English.
    """
    if not row:
        return None
    local = row.get("reason_local")
    if isinstance(local, dict) and local.get("text"):
        if language.lower().split("-")[0] == local.get("language"):
            return str(local["text"])
    reason = row.get("reason")
    return reason if isinstance(reason, str) and reason else None
