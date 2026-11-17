# Changelog

Each release has a section here. The release workflow publishes the section for the version in
`manifest.json` as the release notes, so write it before you run the workflow.

## Unreleased

**Added**

- Translations of the setup, options, entity names, service actions and repairs into French, Danish,
  Portuguese and Irish, for the countries the tariff store holds plans for. Other languages stay in
  English. The Irish text has not had a native speaker's review yet.

## 1.1.0

**Added**

- Diagnostic entities that show which prices apply and how fresh the data is: Prices valid from,
  Prices valid to, Prices last read, a Tariff summary with the plan's details in its attributes,
  Tariff store offline, and Tomorrow's prices available for a tariff on a price feed. A tariff of
  your own rates has no store dates, so it has no valid from or to.
- Options to read the tariff store again now, and to delete the saved tariff files and fetch them
  again. Deleting is refused while the store cannot be reached.
- Repairs when your plan's prices are ending within 14 days with nothing after them, and when the
  store has not been reached for 3 days. Prices last read now keeps the time of the last real
  read while the store is unreachable, instead of moving on.

**Changed**

- The README and documentation are reworked: clearer installation, configuration, entity and
  troubleshooting steps, written for any supplier.

## 1.0.1

**Changed**

- Installs the tariff library from PyPI, pinned to one release, instead of shipping a copy.
- Reads the tariff store with an async client through Home Assistant's own web session.
- Declares the Platinum quality scale tier.

## 1.0.0

First release.

**Added**

- The current tariff of any supplier from the open tariff store, as price and rate band entities,
  with the cheapest and dearest windows.
- The bill so far, from the import and export meters you choose.
- Savings for the bill period, with a home meter and an optional battery.
- Import and export price entities that work in the Energy dashboard.
- The cheapest plan for the usage you measured.
- Diagnostics you can download for a bug report, with your area and energy sensor names removed.
- Icons for the price and window entities, help text for the setup fields, and installation,
  configuration, troubleshooting and removal steps in the README.
