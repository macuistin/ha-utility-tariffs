"""The packages under lib/ import only the standard library and the packages named for them."""

from __future__ import annotations

import ast
import sys

import pytest

from tests.helpers import PKG

LIB = PKG / "lib"
ALLOWED = {
    "timeutil": set(),
    "tariff": {"timeutil"},
    "tariffstore": set(),
    "tariffranking": {"tariff"},
}


def _imports(path) -> list[tuple[int, str | None, int]]:
    """Each import as (relative level, module, line)."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(0, alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append((node.level, node.module, node.lineno))
    return found


def test_every_package_in_lib_is_in_the_table():
    folders = {p.name for p in LIB.iterdir() if p.is_dir() and p.name != "__pycache__"}
    assert folders == set(ALLOWED)


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_a_package_imports_only_the_standard_library_and_its_allowed_packages(name):
    stdlib = set(sys.stdlib_module_names)
    for path in sorted((LIB / name).glob("*.py")):
        for level, module, line in _imports(path):
            where = f"{path.name}:{line}"
            if level == 0:
                assert (module or "").split(".")[0] in stdlib, f"{where} imports {module}"
            elif level >= 2:
                sibling = (module or "").split(".")[0]
                assert sibling in ALLOWED[name], f"{where} reaches into lib/{sibling}"
