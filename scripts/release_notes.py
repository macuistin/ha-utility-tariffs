"""Release notes for a version: its section of CHANGELOG.md.

    python -m scripts.release_notes 1.0.0

Prints the section to stdout and exits 1 when the changelog has no section for the version or the
section is empty. The release workflow passes the output to the GitHub release.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^## (?P<version>\S+)\s*$")


def section(changelog: str, version: str) -> str:
    """The text under `## version`, up to the next `## ` heading, or "" when there is none."""
    lines: list[str] = []
    inside = False
    for line in changelog.splitlines():
        found = HEADING.match(line)
        if found:
            if inside:
                break
            inside = found["version"] == version
        elif inside:
            lines.append(line)
    return "\n".join(lines).strip()


def main(argv: list[str]) -> int:
    version = argv[1]
    body = section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    if not body:
        sys.stderr.write(f"CHANGELOG.md has no notes under '## {version}'.\n")
        return 1
    sys.stdout.write(body + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
