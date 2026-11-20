# Changelog

Each release has a section here. The release workflow publishes the section for the version in
`manifest.json` as the release notes, so write it before you run the workflow.

## Unreleased

**Fixed**

- A negative reading from an energy meter is no longer used as the starting point for the next
  step. It used to book a large false rise as use once the meter read normally again.
- A meter reading that rises faster than your home could draw is left out of the bill, as before,
  and now raises a repair issue that names the meter and the time. The issue clears a day after the
  last reading that was left out. The diagnostics list each reading left out and why.

**Added**

- A price sensor for each rate band, such as **Import price: Night**, so an automation can read
  a band's price at any time of day and not only the band in force now. They follow the tariff:
  a new revision that adds a band adds its sensor, and one that drops a band removes it. A tariff
  with more than three bands has them off until you enable them.
- The price forecast sensor has `import_rates` and `export_rates` attributes: today's and
  tomorrow's prices as `start`, `end` and `value` rows, with half hours at the same price joined.
  A chart card can read them without a template, and `docs/entities.md` has an apexcharts-card
  example. The `slots` attribute gains `export_price`. None of these are kept in the history.
- An **Off-peak** binary sensor, on while the tariff's lowest import price is in force, with the
  start and end of the current and the next off-peak stretch as attributes. A tariff with one price
  all day, or one that follows a price feed, has no off-peak, so the sensor is unavailable.
- A **Largest rise a meter can show (kW)** option. A rise faster than this is left out of the bill.
  Leave it empty for 100 kW.

## 1.3.1

**Added**

- Setting up a new tariff now ends with a page for your energy meters and bill dates, so you no
  longer have to open the options afterwards. The grid import, export and battery meters from your
  Energy dashboard are suggested. Every field is optional, and they stay in the options.
- The note on what a country's plans are missing, shown on the plan page and as an attribute of
  the tariff info sensor, is now read in your Home Assistant language when the store holds it in
  that language. Each country holds English and one other language, its own. Other languages
  read the English note.

## 1.3.0

**Added**

- Plans for five more places in the tariff store: Zambia, Manitoba (Manitoba Hydro), New Brunswick
  (NB Power), Brazil and India. They appear in the country list at setup like any other country.
- A **Connected load (kW)** option for a tariff that charges per kW of connected (sanctioned) load,
  as the India plans do. Until it is set, that tariff shows its prices but no bill, and the bill
  summary service says the load is missing. The plan ranking prices every plan with the same load.
- A kept price day is read again once it is six hours old, so a corrected price day is no longer
  shown for ever.

**Changed**

- Setup starts at the country, then one list of every supplier and plan for it. **Type in my own
  rates** is the first choice in that list, so there is no separate "how do you want to set the
  tariff" page. A store plan takes two pages, or three when its prices differ by area. The country
  starts at your Home Assistant country, or at the followed plan's country on Reconfigure.
- The plan list is searchable: type to filter it. A value that is not in the list is refused.
- The step numbers no longer promise a total, because the area page only follows some plans. The
  area page names the plan it is for.

**Upgrading**

- Home Assistant installs `utility-tariffs-lib` 0.3.1 when it restarts. Nothing else to do.

## 1.2.0

**Changed**

- Setup has two pages instead of three for most plans: the country, then one list of every supplier
  and plan for it. The area page appears only for a plan priced by area. Each page says which step
  it is, and the buttons read Next until the last page. Where the store holds only part of a
  country's prices, the plan page says what is missing.
- The Tariff summary sensor has two new attributes, `country_availability` and `country_reason`,
  taken from the store's country index.

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
