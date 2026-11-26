# Example dashboard: bill, savings and plan ranking

[`bill-dashboard.yaml`](bill-dashboard.yaml) is a dashboard you can paste in. It is a bill view
with a large figure for the bill so far, with and without bars, a bar chart of each day, the
bill line by line, and your plan ranked against the others.

It needs one HACS card, [`apexcharts-card`](https://github.com/RomRider/apexcharts-card), for the
daily chart. Every other card is a standard one. The bars are small pictures inside the markdown
card and the tables are HTML tables that fill the card, so nothing else needs installing. Without
`apexcharts-card` that one card shows an error and the rest still works.

## Use it

1. Open your dashboard, choose **Edit**, then the three dots, then **Raw configuration editor**.
2. Replace the whole contents with this file. To keep your other views, paste the part from `- title: Bill` down as one more item under your own `views:`.
3. Replace `service_electricity_tariff` in each entity id with your tariff's device name.

Set an import meter in the options first. The saving needs a house consumption meter too.

## What it shows

| Card | Entities and attributes it reads |
| --- | --- |
| This bill period: spend so far, days priced, projection | **Bill so far** and its `period_start`, `days_priced`, `days_in_period`, `days_left` and `projected_bill` attributes |
| Saved by solar and battery, with and without bars | **Savings this bill period** and its `bill_without_system` attribute |
| Four tiles | **Savings share this bill period**, **Import this bill period**, **Plan rank**, **Cheapest plan saving** |
| Cheapest plans, each a bar on the scale of the dearest | **Plan rank** and its `summary`, `top_plans`, `plans_compared`, `period_start`, `period_end` and `days_recorded` attributes, plus **Cheapest plan saving** |
| Line by line: paid, would have paid, saved | The `lines` attribute of **Savings this bill period**, and its `bill_so_far`, `bill_without_system` and `bill_difference` attributes |
| Each day chart and folded table | The `daily` attribute of **Savings this bill period** |

Gas has its own bill and plan sensors under the gas subentry. Copy the view and use those entity ids.

## Reading the attributes

The line table and the daily chart reads attributes that hold lists. A line with `included: true`
is a tax already inside the prices, so the table leaves it out of the rows and the total and
shows it underneath. A day with no recorded house load is left out of the chart. See the
[features page](../features.md) for what each attribute holds.

Without a house consumption meter there is no **Savings this bill period**, so these two cards
show a message. **Bill so far** has a `lines` attribute with `paid` only.
