# Utility Tariffs

A Home Assistant integration that knows your tariff. It prices every half hour from the open
tariff store, and works out the cheapest and dearest windows, the bill so far and, with your own
energy sensors, what solar and a battery save and which plan would have cost least.

Status: early development. Nothing is installable yet.

## How it is built

- All tariff, price, window, ranking, savings and billing code is written and tested in
  [utility-tariffs](https://github.com/macuistin/utility-tariffs) and copied here unchanged
  (`custom_components/utility_tariffs/lib/`, each folder with an `UPSTREAM.json`).
- The integration is Home Assistant glue around it: the cache, timers, repairs, storage and
  entities.
- Electricity only to start.

## Licence

MIT. See `LICENSE`.
