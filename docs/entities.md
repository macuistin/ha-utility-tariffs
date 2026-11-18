# Entities and actions

Each followed tariff is one device. Prices are in the tariff's currency per kWh.

| Entity | Meaning |
| --- | --- |
| Import price, Export price | The price in force now, all taxes and discounts in |
| Import rate band | The name of the band in force now |
| Previous import price, Next import price, Next price change | The price before the current one, the one after it, and when it starts |
| Import price rating | Where the current price sits in today's range: very low, low, normal, high or very high. A flat tariff is always normal |
| Lowest, highest and average import price today | Over the local day. The average is weighted by time. The export versions are off until you enable them |
| Cheapest window start and end, Dearest window start, Cheapest window active | The best stretch of the length set in the options, from now to the end of tomorrow. The window starts at its earliest best time and ends where that price stops changing, so a window inside a long band ends with the band |
| Prices valid from, Prices valid to, Prices last read, Tariff summary, Tariff store offline, Tomorrow's prices available | Diagnostics. The dates are the store's for the plan in force (valid to is unknown while open ended). Prices last read is when this install last read the store. The summary is named after the plan and lists provider, country, how complete the store is for that country and why, revision, source link, completeness and band prices. Tomorrow's prices available is only for a tariff on a price feed |

### Price forecast

| Entity | Meaning |
| --- | --- |
| Price forecast | The time the prices are known until. Its `slots` attribute lists the next 48 hours (start, end, price, band and whether the price is `fixed` or `published`). `changes` lists revisions the store already holds, with each band's new price. `window_percentiles` and `history_percentiles` give the low, 50th and high percentile of the prices ahead and of this time of day over the last 28 days (shown after 7 days). `complete` says whether prices are known to the end of the range asked for |
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
