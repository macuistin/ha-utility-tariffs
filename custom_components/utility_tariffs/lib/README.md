# lib/

Packages written as if each were already its own distribution, so a later move to PyPI is a plain
`git mv`. They live here because HACS ships only `custom_components/utility_tariffs/`. Code the
integration imports at run time must sit inside that folder until it is published somewhere
installable.

## Rules for every package

- It imports only the standard library, itself and the `lib/` packages named for it in the table
  below. `tests/test_lib_rules.py` enforces it.
- It never imports `homeassistant` or any module of the integration outside `lib/`, not even
  under `TYPE_CHECKING`.

## Copied packages

All four packages here are copies. The tariff store, `macuistin/utility-tariffs`, is the source
of truth for all tariff and billing code and calculations. They are written and tested there.

- Never edit a file in a copied folder, or a test under `tests/lib/` that starts with the
  `Copied from the tariff store` line. Change it in the store's repository.
- The Copy tariffstore workflow copies the folders and their tests each week and opens a pull
  request. To copy by hand, run `python scripts/copy_tariffstore.py <path to a checkout>`.
- Each folder's `UPSTREAM.json` records the commit copied and a SHA-256 of each file.
  `tests/lib/test_upstream.py` fails when a file no longer matches.

## Packages

| Package | Purpose | Allowed `lib/` dependencies |
| --- | --- | --- |
| `timeutil` | Elapsed-time maths that stays correct across a clock change | none |
| `tariff` | Tariff model, bill engine, price curve, cheapest window, savings, half-hourly slots | `timeutil` |
| `tariffstore` | Client for the open tariff store: find, fetch, check, cache and compile a tariff | none |
| `tariffranking` | Prices every plan over the same usage and ranks them | `tariff` |
