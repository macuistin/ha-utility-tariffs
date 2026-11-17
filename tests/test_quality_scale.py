"""The quality scale file lists every rule, and the manifest claims no tier it does not earn."""

from __future__ import annotations

import json

import yaml

from tests.helpers import PKG

TIERS = {
    "bronze": (
        "action-setup appropriate-polling brands common-modules config-flow-test-coverage "
        "config-flow dependency-transparency docs-actions docs-high-level-description "
        "docs-installation-instructions docs-removal-instructions entity-event-setup "
        "entity-unique-id has-entity-name runtime-data test-before-configure test-before-setup "
        "unique-config-entry"
    ),
    "silver": (
        "action-exceptions config-entry-unloading docs-configuration-parameters "
        "docs-installation-parameters entity-unavailable integration-owner log-when-unavailable "
        "parallel-updates reauthentication-flow test-coverage"
    ),
    "gold": (
        "devices diagnostics discovery-update-info discovery docs-data-update docs-examples "
        "docs-known-limitations docs-supported-devices docs-supported-functions "
        "docs-troubleshooting docs-use-cases dynamic-devices entity-category entity-device-class "
        "entity-disabled-by-default entity-translations exception-translations icon-translations "
        "reconfiguration-flow repair-issues stale-devices"
    ),
    "platinum": "async-dependency inject-websession strict-typing",
}
SETTLED = {"done", "exempt"}


def _status(value: object) -> str:
    return str(value["status"] if isinstance(value, dict) else value)


def _rules() -> dict[str, str]:
    document = yaml.safe_load((PKG / "quality_scale.yaml").read_text())
    return {name: _status(value) for name, value in document["rules"].items()}


def test_every_rule_is_listed_once_with_a_known_status() -> None:
    rules = _rules()

    assert set(rules) == {name for names in TIERS.values() for name in names.split()}
    assert set(rules.values()) <= SETTLED | {"todo"}


def test_an_exemption_says_why() -> None:
    document = yaml.safe_load((PKG / "quality_scale.yaml").read_text())

    for name, value in document["rules"].items():
        if _status(value) == "exempt":
            assert value.get("comment"), name


def test_the_manifest_claims_no_tier_the_file_does_not_support() -> None:
    claimed = json.loads((PKG / "manifest.json").read_text()).get("quality_scale")
    if claimed is None:
        return
    rules = _rules()
    for tier, names in TIERS.items():
        for name in names.split():
            assert rules[name] in SETTLED, f"{claimed} claimed but {name} is {rules[name]}"
        if tier == claimed:
            break
