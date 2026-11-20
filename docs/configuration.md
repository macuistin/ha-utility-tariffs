# Configuration

## Options

The last page of setup asks for the meters and bill dates below, with the meters from your Energy
dashboard suggested. Leave it empty to show prices only. The same fields are in the options.

Open the integration, choose the three dots, then **Configure**. Saving the options reloads the
integration.

| Option | Meaning |
| --- | --- |
| Window length | Minutes in the cheapest and dearest windows, 30 to 720 in steps of 30 (default 120) |
| Energy imported, exported, used by the home, taken out of the battery | Sensors in kWh that only ever rise. The import meter switches the bill on |
| Battery charge, size and wear per kWh | Used with the home meter to value the energy the battery holds |
| Connected load (kW) | Only for a tariff that charges per kW of connected (sanctioned) load, as some in India do. Find it on your bill or supply agreement. Without it that tariff shows prices but no bill, and its bill service reports that the load is missing |
| Largest rise a meter can show (kW) | The most power your home could draw, default 100. A meter reading that rises faster than this is left out of the bill and raises a repair issue. A meter reset, or a meter that comes back after being unavailable, is left out without a repair |
| Start of history | Optional. The first day to fill from your meters' hourly statistics when the plan starts. Leave empty for the last year. Saving the options runs the fill again |
| Day of the month a bill starts, months in one bill, a month a bill starts in | Line the bill up with your supplier's. Empty follows the tariff |

Two tick boxes in the same form act once and are not saved: **Read the tariff store again now** and
**Delete the saved tariff files first**. See [how the tariffs are kept current](tariff-store.md).

## Bill dates

In the integration's options you can set the day of the month a bill starts (1 to 28) and how many
months one bill covers (1, 2, 3, 4, 6 or 12). For a bill longer than a month, also give a month a
bill starts in, so the periods line up with your supplier's: a two-month bill that starts on
16 February has start day 16 and start month 2. Anything left empty follows the tariff, and a day
count is not offered because suppliers bill by calendar month. The bill so far and the saving this
bill period both use these dates.

## Your own rates

When your plan is not in the store, choose **Type in my own rates** at setup, or in Reconfigure.
First pick the shape closest to your tariff: a flat rate, day and night (night 23:00 to 08:00), peak
and off-peak (peak 17:00 to 19:00), a cheap midday (11:00 to 15:00) or a cheap overnight window
(02:00 to 06:00), or start from nothing. The shape only fills in the rate names and hours. You type
the prices, and can add more timed rates afterwards.
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
