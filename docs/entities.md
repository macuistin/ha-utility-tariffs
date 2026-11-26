# Entities and actions

Each followed tariff is one device. Prices are in the tariff's currency per kWh.

| Entity | Meaning |
| --- | --- |
| Import price, Export price | The price in force now, all taxes and discounts in |
| Import rate band | The name of the band in force now |
| Previous import price, Next import price, Next price change | The price before the current one, the one after it, and when it starts |
| Import price rating | Where the current price sits in today's range: very low, low, normal, high or very high. A flat tariff is always normal |
| Lowest, highest and average import price today | Over the local day. The average is weighted by time. The export versions are off until you enable them |
| Time of the lowest and highest import price, today and tomorrow | Timestamps, all off until you enable them. Tomorrow's is unknown until the whole day is priced. A band that began the day before gives the start of the day |
| Import price as a share of today's highest | Percentage, off until you enable it |
| Cheaper periods today | How many half hours of today cost less than now, off until you enable it. Unknown until the day is priced in full |
| Lowest, highest and average import and export price tomorrow | The same figures for tomorrow, all off until you enable them. They are unknown until tomorrow's prices are all held, so a price-feed tariff shows nothing until the feed publishes the whole day, and never a guess |
| Cheapest window start and end, Dearest window start, Cheapest window active | The best stretch of the length set in the options, from now to the end of tomorrow. The window starts at its earliest best time and ends where that price stops changing, so a window inside a long band ends with the band |
| Off-peak | On while the tariff's lowest import price is in force. Off-peak means that lowest price only, not every band below the day's average, so a three-band tariff is off-peak in its cheapest band alone. Its attributes `current_start`, `current_end`, `next_start` and `next_end` hold the times. Unavailable, not off, for a tariff with one price all day and for one that follows a price feed |
| Negative price | Only for a tariff on a price feed. On while the import price in force is below zero, so a load can run and be paid for it. Unavailable when no price is held for now |
| Import price: *band*, Export price: *band* | One sensor for each rate band of the tariff, so an automation can read the off-peak price at noon. The price is the all-in price of one more kWh in that band, with every tax and discount applied, from the same bill calculation as the bill. When a new revision adds a band its sensor appears, and when a revision drops a band its sensor is removed, with no reload. A tariff with more than three bands has these sensors off until you enable them |
| Prices valid from, Prices valid to, Tariff status, Prices last read, Tariff summary, Tariff store offline, Tomorrow's prices available | Diagnostics. The dates are the store's for the plan in force (valid to is unknown while open ended). Tariff status is `current`, `ending` (an end date within 14 days and nothing after it), `ended` (the store lists the plan but holds no prices in force) or `withdrawn` (the store no longer lists it). It is worked out from the store, never typed. The sensor's `needs_attention` attribute is true for `ended` and `withdrawn`, which also raise a repair issue until you follow another plan or the store lists the plan again. The prices already held stay in use meanwhile. Prices last read is when this install last read the store. The summary is named after the plan and lists provider, country, how complete the store is for that country and why, revision, source link, completeness and band prices. Tomorrow's prices available is only for a tariff on a price feed |

### Price forecast

| Entity | Meaning |
| --- | --- |
| Price forecast | The time the prices are known until. For a tariff on a price feed that is the end of the published prices. For a fixed tariff the prices hold until the next revision the store holds, so it is that revision's start, or unknown when there is none (the `prices_fixed` attribute is true). Its `slots` attribute lists the next 48 hours (start, end, import price, export price, band and whether the price is `fixed` or `published`). `import_rates` and `export_rates` hold today's and tomorrow's prices as rows of `start`, `end` and `value`, the shape evcc reads, with neighbouring half hours at the same price joined into one row. None of these attributes are kept in the history. `changes` lists revisions the store already holds, with each band's new price. `window_percentiles` and `history_percentiles` give the low, 50th and high percentile of the prices ahead and of this time of day over the last 28 days (shown after 7 days). `complete` says whether prices are known to the end of the range asked for |
| Next tariff change | The day the next revision starts, with the band prices before and after |
| Next low price, Next high price | When the price next falls to the low percentile of the prices known ahead, or rises to the high one, with when that stretch ends |
| Price level (tariffs on a half-hourly price feed only) | Low, mid or high for the price now, compared with this time of day over the last 28 days, or with the prices ahead until a week of history is held. The `basis` attribute says which |
| Low price percentile, High price percentile | Numbers that set what counts as low (1 to 49, default 10) and high (51 to 99, default 90). A change applies at once |

A fixed tariff is priced two weeks ahead, over every revision the store already holds. A tariff
on a price feed such as Agile Octopus is priced from the published half-hourly prices and stops
where they stop: nothing is guessed for the part not yet published. Tomorrow's Agile prices appear
in the afternoon, so the feed is read every half hour from 16:00 until they are held. If they are
still missing after 22:00 a repair issue says so. The price history for the percentiles builds as
days are published.

The `get_prices` action returns every price that overlaps a range, from yesterday to the furthest
price known, with the import and export price, band and source, and says whether the range is
fully covered and where the prices are known until. The
`find_window` action finds the cheapest or dearest stretch for a load of a given power. Both return
their answer, so use them with `response_variable`.

### Charting the prices

The price forecast sensor holds the prices as attributes, so a chart card needs no template. This
apexcharts-card example draws today's and tomorrow's import price as steps:

```yaml
type: custom:apexcharts-card
graph_span: 48h
span:
  start: day
header:
  show: true
  title: Import price
series:
  - entity: sensor.electricity_tariff_price_forecast
    type: line
    curve: stepline
    data_generator: |
      return entity.attributes.import_rates.flatMap((row) => [
        [new Date(row.start).getTime(), row.value],
        [new Date(row.end).getTime(), row.value],
      ]);
```

Use `export_rates` for the export price. The rows are not checked against a live evcc or Predbat
install: the shape is the one evcc's custom tariff reads, so verify it there before relying on it.

## Units and state classes

Every price sensor has the unit `<currency>/kWh`, which is what the Energy dashboard checks for
a price entity. It needs a numeric state and a unit ending in a price per energy unit, and nothing
else, so it does not ask for a device class or a state class.

Only the **Import price** and **Export price** (the price in force now) have the `measurement`
state class, so Home Assistant keeps long-term statistics for them. The next and previous price,
the day's lowest, highest and average, the price rating and the window and forecast sensors have
no state class, so they are not summarised into statistics. Their values come from the same held
prices, and a long history of them adds nothing the current price does not already hold.

This follows the integrations that the maintainers compared. In Home Assistant 2026.10, Nord Pool,
Amber Electric, easyEnergy and EnergyZero give the `measurement` class to the price in force now.
Nord Pool also gives it to its optional block averages and its optional daily average, and Amber
to its forecast. None of them gives it to the last, next, lowest or highest price. Changing a state
class later changes what is kept in statistics, so do not add one to another sensor without a
reason.
