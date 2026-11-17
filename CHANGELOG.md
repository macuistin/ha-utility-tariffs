# Changelog

Each release has a section here. The release workflow publishes the section for the version in
`manifest.json` as the release notes, so write it before you run the workflow.

## Unreleased

**Added**

- Diagnostic entities that show which prices apply and how fresh the data is: Prices valid from,
  Prices valid to, Prices last read, a Tariff summary with the plan's details in its attributes,
  Tariff store offline, and Tomorrow's prices available for a tariff on a price feed. A tariff of
  your own rates has no store dates, so it has no valid from or to.

## 1.0.0

First release.

**Added**

- The current tariff of any supplier from the open tariff store, as price and rate band entities,
  with the cheapest and dearest windows.
- The bill so far, from the import and export meters you choose.
- Savings for the bill period, with a home meter and an optional battery.
- Import and export price entities that work in the Energy dashboard.
- The cheapest plan for the usage you measured.
- Reads the tariff store with an async client through Home Assistant's own web session, and
  installs the tariff library from PyPI. The integration declares the Platinum quality scale tier.
- Diagnostics you can download for a bug report, with your area and energy sensor names removed.
- Icons for the price and window entities, help text for the setup fields, and installation,
  configuration, troubleshooting and removal steps in the README.
