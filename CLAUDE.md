# Utility Tariffs

Rules for AI assistants working in this repo. `AGENTS.md` is a symlink to this file. The detailed
rules are in `.claude/rules/`. Keep this file under 150 lines and put detail in a rule file.

## What this is

A Home Assistant custom integration, distributed through HACS, that gives the current tariff of
any supplier as entities: prices, rate bands, cheapest and dearest windows, and (with the
user's own energy sensors) the bill so far, savings, and the cheapest plan for the usage.
Electricity only to start. It is a separate integration from `macuistin/givenergy_inverter_manager`
and shares code with it.

## All tariff maths lives elsewhere

`macuistin/utility-tariffs` is the only source of tariff, price, window, ranking, savings and
billing code. `custom_components/utility_tariffs/lib/` holds copies, written by
`scripts/copy_tariffstore.py` with an `UPSTREAM.json` each. Never edit a copy or a copied test.
If the integration needs engine behaviour that is not there, open an issue and a pull request in
`macuistin/utility-tariffs` first, then copy. No local patch, even a temporary one. Home
Assistant glue (cache files, timers, repairs, storage, entities) is written here.

## Layout

| Path | Role |
| --- | --- |
| `custom_components/utility_tariffs/` | The integration: `config_flow.py` (country, supplier, plan, area), `coordinator.py` (the tariff and two days of prices, read nightly), `sensor.py`, `entity.py` |
| `custom_components/utility_tariffs/lib/` | Copied packages. `lib/README.md` has the rules and the allowed imports |
| `custom_components/utility_tariffs/helper/` | Home Assistant glue meant to be shared with the GivEnergy integration: no domain or constants of its own, no tariff maths. Cache access first, then updater and slot storage |
| `scripts/copy_tariffstore.py` | Copies the packages and their tests from a checkout of the store |
| `custom_components/utility_tariffs/{meter,accountant,energy_store,bill,bill_sensor}.py` | The bill from the user's own meters: `meter.py` reads a rising kWh sensor into rises, `accountant.py` books them every minute into the slot history, `energy_store.py` saves it per entry, `bill.py` prices the period with `price_period`, `bill_sensor.py` shows it. Only when an import meter is set in the options |
| `tests/` | Unit tests. `tests/lib/` holds the copied tests |
| `.github/workflows/` | `tests.yml`, `hassfest.yml`, `hacs.yml`, `tariffstore-copy.yml` (weekly copy pull request) |

## Commands

The code uses Python 3.14 syntax. Make the virtualenv with `uv venv --python 3.14 .venv`, then
`uv pip install -r requirements-test.txt`. Every test runs on a real Home Assistant through
`pytest-homeassistant-custom-component`, so there are no stubs. `tests/requirements-floor.txt` is the
minimum Home Assistant in `hacs.json`. `strings.json` and `translations/en.json` stay identical.

```bash
ruff check custom_components tests scripts
mypy --follow-imports=silent custom_components/utility_tariffs
bandit -q -r custom_components/utility_tariffs -c .bandit.yaml
python -m pytest tests -q
python scripts/copy_tariffstore.py ../utility-tariffs      # refresh the copies
python scripts/copy_tariffstore.py --check ../utility-tariffs   # exit 1 if a copy is behind
```

Run the first four before pushing. Say plainly which checks you ran.

## Working agreements

- Docs, strings and rules follow `.claude/rules/docs-and-style.md` (UK English, generic, no
  maintainer or household details, Conventional Commits, stacked PRs with merge commits).
- Python limits are in `.claude/rules/python-style.md`.
- Search the existing constants before adding a config option, constant or entity. Say so in the
  pull request when you add one.
- Tests drive behaviour. Do not read a source file and assert a string in it.
- Never rebase, amend or force-push a branch with an open PR. Never merge a PR or cut a release
  unless the maintainer asks.
- Improve these instructions as you work. When a task costs you time on something the next
  session should already know, add it to this file or a rule in the same PR.
