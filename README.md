# Utility Tariffs

A Home Assistant integration that knows your tariff. It prices every half hour from the open
tariff store, and works out the cheapest and dearest windows, the bill so far and, with your own
energy sensors, what solar and a battery save and which plan would have cost least.

Status: early development. Nothing is installable yet.

## Bill so far

In the integration's options, choose the sensors that count the energy you import and export, such
as your smart meter's totals (kWh, Wh or MWh, only ever rising). Every minute the rise since the
last reading is booked into a half-hourly history, which is saved and priced under the tariff for
the current bill period. You get the bill so far, the energy imported this period and how much of
the period the history covers. A meter that updates only every half hour or day books each step in
the minute it appears, so the bill by rate band can differ slightly from your supplier's.

## Energy dashboard

The import price and export price sensors can be used as the "entity with the current price" for
a grid connection in the Energy dashboard, and as the entity for export compensation.

- Both report the price per kWh in the tariff's currency, such as `EUR/kWh`, and move at every
  half hour.
- The export price is `0` when the tariff pays nothing for export, so it is always a number.
- The dashboard lists only price entities in your Home Assistant currency (Settings, System,
  General). A tariff in another currency does not appear in the picker.

## How it is built

- All tariff, price, window, ranking, savings and billing code is written and tested in
  [utility-tariffs](https://github.com/macuistin/utility-tariffs) and copied here unchanged
  (`custom_components/utility_tariffs/lib/`, each folder with an `UPSTREAM.json`).
- The integration is Home Assistant glue around it: the cache, timers, repairs, storage and
  entities.
- Electricity only to start.

## Licence

MIT. See `LICENSE`.
