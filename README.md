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

## Cheaper plans

When an import meter is set, the integration prices your last whole bill under every other plan of
your country and area in the store, every night shortly after midnight, and ranks them. **Plan
rank** is where your plan stands (1 is the cheapest), with the cheapest few plans and their bills
in its attributes. **Cheapest plan saving** is what the cheapest plan would have saved, and is 0
when yours is cheapest. When the saving is at least 5% of your bill, a repair notice names the
plan.

This re-prices what you used. It is not a forecast, it never switches your plan, and it does not
know exit fees, contract terms or whether a plan is open to you. A plan that lists no export price
is priced with your plan's export rate. Plans that hold only other areas, or cannot be read, are
left out and counted. To follow a plan, use Reconfigure.

## Bill dates

In the integration's options you can set the day of the month a bill starts (1 to 28) and how many
months one bill covers (1, 2, 3, 4, 6 or 12). For a bill longer than a month, also give a month a
bill starts in, so the periods line up with your supplier's: a two-month bill that starts on
16 February has start day 16 and start month 2. Anything left empty follows the tariff, and a day
count is not offered because suppliers bill by calendar month. The bill so far and the saving this
bill period both use these dates.

## Your own rates

When your plan is not in the store, choose **Type in my own rates** at setup, or in Reconfigure.
Enter the main unit rate, export rate, standing charge per day, monthly levy, discount on energy,
VAT, whether your prices already include VAT, and the day of the month a bill starts (1 to 28). Then
add any timed rates, such as a night rate, with their hours. Where timed rates overlap, the
cheapest applies. Rates are entered as they appear on your bill, before VAT unless you say the
prices include it. They are kept in your own Home Assistant and are never sent to the store.
Public holidays are not applied. Changing the rates means reconfiguring again.

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
