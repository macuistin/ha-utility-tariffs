# Troubleshooting

## Common problems

- **Setup says the store could not be read.** Check that Home Assistant can reach
  `raw.githubusercontent.com` over https, then try again.
- **Prices stopped updating.** The held prices keep working while the store is unreachable. For a
  price-feed tariff, a repair issue appears if tomorrow's prices are still missing after 22:00.
- **The bill is empty.** Set an import meter in the options. It must be a kWh sensor that only
  rises.
- **Reporting a bug.** Open the integration, choose the three dots, **Download diagnostics**, and
  attach the file. Your area and the names of your energy sensors are removed from it.

## Known limitations

- Electricity and gas. One tariff of each per Home Assistant. Water and heating oil are not supported yet.
- Prices are only as current as the open store. A plan the store does not hold can be typed in as
  your own rates, but public holidays are not applied to those.
- The bill is an estimate from the meters you choose and can differ from your supplier's by small
  amounts. Plan ranking is a comparison of past use, not a forecast, and ignores exit fees and
  contract terms.
- Nothing is guessed for prices that are not published yet.
