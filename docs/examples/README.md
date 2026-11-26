# Example dashboard: bill, savings and plan ranking

[`bill-dashboard.yaml`](bill-dashboard.yaml) is a dashboard view you can paste into your own
dashboard. It uses only standard cards (markdown, tile, gauge and heading), so nothing extra
needs installing. The colour comes from what the markdown card already allows: `<font color>`
and Home Assistant's own `<ha-alert>` banner.

## Use it

1. Open your dashboard, choose **Edit**, then the three dots, then **Raw configuration editor**.
2. Replace the whole contents with this file. To keep your other views, paste the part from `- title: Bill` down as one more item under your own `views:`.
3. Replace `electricity_tariff` in each entity id with your tariff's device name.

Set an import meter in the options first. The saving needs a house consumption meter too.

## What it shows

| Card | Entities and attributes it reads |
| --- | --- |
| This bill period: spend so far, days priced | **Bill so far** and its `period_start`, `days_priced` and `days_in_period` attributes |
| Saved by solar and battery, with and without bars | **Savings this bill period** and its `bill_without_system` attribute |
| Share saved, energy imported | **Savings share this bill period**, **Import this bill period** |
| Cheapest plans table | **Plan rank** and its `summary`, `top_plans`, `plans_compared`, `period_start`, `period_end` and `days_recorded` attributes, plus **Cheapest plan saving** |
| Line by line: paid, would have paid, saved | The `lines` attribute of **Savings this bill period**, and its `bill_so_far`, `bill_without_system` and `bill_difference` attributes |
| Day by day bars | The `daily` attribute of **Savings this bill period** |

Gas has its own bill and plan sensors under the gas subentry. Copy the view and use those entity ids.

## Reading the attributes

The line table and the daily bars read attributes that hold lists. A line with `included: true`
is a tax already inside the prices, so the table leaves it out of the rows and the total and
shows it underneath. A day with no recorded house load is left out of the bars. See the
[features page](../features.md) for what each attribute holds.

Without a house consumption meter there is no **Savings this bill period**, so these two cards
show a message. **Bill so far** has a `lines` attribute with `paid` only.
