# Example dashboard: bill, savings and plan ranking

[`bill-dashboard.yaml`](bill-dashboard.yaml) is a dashboard view you can paste into your own
dashboard. It uses only standard cards (markdown, tile, heading and history graph), so nothing
extra needs installing.

## Use it

1. Open your dashboard, choose **Edit**, then the three dots, then **Raw configuration editor**.
2. Paste the file's contents under `views:`.
3. Replace `electricity_tariff` in each entity id with your tariff's device name.

Set an import meter in the options first. The saving needs a house consumption meter too.

## What it shows

| Card | Entities and attributes it reads |
| --- | --- |
| This bill period: spend so far, days priced | **Bill so far** and its `period_start`, `days_priced` and `days_in_period` attributes |
| Saved by solar and battery, with and without bars | **Savings this bill period** and its `bill_without_system` attribute |
| Share saved, energy imported | **Savings share this bill period**, **Import this bill period** |
| Cheapest plans table | **Plan rank** and its `summary`, `top_plans`, `plans_compared`, `period_start`, `period_end` and `days_recorded` attributes, plus **Cheapest plan saving** |
| Over the period | History of **Bill so far** and **Savings this bill period** |

Gas has its own bill and plan sensors under the gas subentry. Copy the view and use those entity ids.

## What the integration does not expose as entities

These are not in the example, because there is no entity to read. Nothing here is invented.

- **Line by line table** (energy, supplier discount, standing charge, levy, VAT, export credit,
  each with paid, would have paid and saved). The lines exist only in the HTML returned by the
  `utility_tariffs.bill_summary` action, and only for the bill as paid. There is no "would have
  paid" per line.
- **Daily bars of paid against would have paid.** No sensor holds a per-day bill. **Bill so far**
  and **Savings this bill period** have no state class, so they have no long-term statistics
  either. The history graph at the bottom shows the running totals instead.
- **Without them bar by component.** Only the total without a system is held
  (`bill_without_system`), not its lines.

A line table and a daily series would need new sensors or attributes in the integration.
