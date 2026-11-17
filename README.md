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

## Savings

Add a sensor for the energy the whole home uses and you also get "Savings this bill period": what
the home would have paid buying all of its energy from the grid, less what it paid, with export
credit counted. The standing charge cancels, because both bills carry it. For a battery, add its
size and its charge sensor, and the value of the energy it holds more or less than when the bill
period began is added or taken off. A sensor for the energy taken out of the battery, and a wear
cost per kWh, take wear off. Without a record of what was bought for the battery, stored energy is
valued at the cheapest rate band.

## Energy dashboard

The import price and export price sensors can be used as the "entity with the current price" for
a grid connection in the Energy dashboard, and as the entity for export compensation.

- Both report the price per kWh in the tariff's currency, such as `EUR/kWh`, and move at every
  half hour.
- The export price is `0` when the tariff pays nothing for export, so it is always a number.
- The dashboard lists only price entities in your Home Assistant currency (Settings, System,
  General). A tariff in another currency does not appear in the picker.

## Changing plan

Open the integration, choose the three dots, then **Reconfigure**, and pick another country,
supplier, plan or area. The sensors keep their entity IDs, history and place in the Energy
dashboard and your automations, and the saved energy history is priced again under the new plan.
Only one tariff is followed. The device is always called Utility Tariff and the plan is its model,
so sensors read `sensor.utility_tariff_import_price` whatever the plan. Entries made before this
rule keep their existing entity IDs.

## Entities and actions

Each followed tariff is one device. Prices are in the tariff's currency per kWh.

| Entity | Meaning |
| --- | --- |
| Import price, Export price | The price in force now, all taxes and discounts in |
| Import rate band | The name of the band in force now |
| Previous import price, Next import price, Next price change | The price before the current one, the one after it, and when it starts |
| Import price rating | Where the current price sits in today's range: very low, low, normal, high or very high. A flat tariff is always normal |
| Lowest, highest and average import price today | Over the local day. The average is weighted by time. The export versions are off until you enable them |
| Cheapest window start and end, Dearest window start, Cheapest window active | The best stretch of the length set in the options, from now to the end of tomorrow |

The `get_prices` action returns every price from yesterday to the end of tomorrow that overlaps a
range, with the import and export price and band, and says whether the range is fully covered. The
`find_window` action finds the cheapest or dearest stretch for a load of a given power. Both return
their answer, so use them with `response_variable`.

## How it is built

- All tariff, price, window, ranking, savings and billing code is written and tested in
  [utility-tariffs](https://github.com/macuistin/utility-tariffs) and copied here unchanged
  (`custom_components/utility_tariffs/lib/`, each folder with an `UPSTREAM.json`).
- The integration is Home Assistant glue around it: the cache, timers, repairs, storage and
  entities.
- Electricity only to start.

## Licence

MIT. See `LICENSE`.
