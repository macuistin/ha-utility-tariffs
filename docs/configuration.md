# Configuration

## Options

The last page of setup asks for the meters and bill dates below, with the meters from your Energy
dashboard suggested. Leave it empty to show prices only. The same fields are in the options.

Open the integration, choose the three dots, then **Configure**. Configure is a list of pages, each
with a line saying what is set now. Open a page, change it and you come back to the list. Coming back saves the change and reloads the integration once. Choose **Done** to close Configure.

| Page | What is on it |
| --- | --- |
| Electricity tariff, Gas tariff | **Choose a different plan** with the same pages as setup: country, supplier and plan, area, or your own rates. A Bills page follows, for the day a bill starts, how long it runs and, for electricity, the connected load. The same page, and the window length and cheap rule, can also be opened from the tariff page without changing the plan, because they belong to that fuel's tariff. The sensors keep their entity IDs and history. Either fuel is changed from this one Configure. A fuel that is not followed yet shows "not followed yet" and is added when you come back to the list |
| Energy meters (Gas meter for gas) | The import, export and whole-home sensors, the start of history and the largest rise a meter can show. **Fill history now** reads the meters' statistics and fills the half hours nothing was booked for when you save. It is the same as the `backfill` action |
| Battery | The battery's discharge meter, charge, size and wear. Electricity only |
| Tariff store | Read the store again, or delete the saved files. Both happen when you save |

| Option | Meaning |
| --- | --- |
| Window length | Minutes in the cheapest and dearest windows, 30 to 720 in steps of 30 (default 120) |
| Energy imported, exported, used by the home, taken out of the battery | Sensors in kWh that only ever rise. The import meter switches the bill on |
| Battery charge, size and wear per kWh | Used with the home meter to value the energy the battery holds |
| Connected load (kW) | Only for a tariff that charges per kW of connected (sanctioned) load, as some in India do. Find it on your bill or supply agreement. Without it that tariff shows prices but no bill, and its bill service reports that the load is missing |
| Largest rise a meter can show (kW) | The most power your home could draw, default 100. A meter reading that rises faster than this is left out of the bill and raises a repair issue. A meter reset, or a meter that comes back after being unavailable, is left out without a repair |
| Start of history | Optional. The first day to fill from your meters' hourly statistics when the plan starts. Leave empty for the last year. Saving the options runs the fill again |
| Day of the month a bill starts, months in one bill, a month a bill starts in | Line the bill up with your supplier's. Empty follows the tariff |

Two tick boxes on the Tariff store page act once and are not saved: **Read the tariff store again now** and
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
The form starts from the country you chose: its currency and the VAT rate in force there today, read
from the store, which you can change. Each price shows its unit, such as `EUR/kWh`.
Enter the main unit rate, export rate, standing charge per day, monthly levy, discount on energy,
VAT, whether your prices already include VAT, and the day of the month a bill starts (1 to 28). Then
add any timed rates, such as a night rate, with their hours. Where timed rates overlap, the
cheapest applies. Rates are entered as they appear on your bill, before VAT unless you say the
prices include it. They are kept in your own Home Assistant and are never sent to the store.
Public holidays are not applied. Changing the rates means reconfiguring again.

## Changing plan

Open the integration, choose the three dots, then **Reconfigure** (or use the Electricity tariff or
Gas tariff page in Configure), and pick another country, supplier, plan or area. The sensors keep their entity IDs, history and place in the Energy
dashboard and your automations, and the saved energy history is priced again under the new plan.
## One integration, two tariffs

Utility Tariffs is one integration entry. Under it sit the tariffs you follow: an **Electricity
tariff** and a **Gas tariff**, each with its own device. The device row shows the supplier and plan.
Add the second fuel from Configure. Removing a tariff from the integration page removes its
device, sensors and saved history. One tariff of each service is followed.

The electricity device is always called Electricity tariff and the gas device Gas tariff, whatever
the plan, so new sensors read `sensor.electricity_tariff_import_price` or
`sensor.gas_tariff_import_price`. An install that was set up before 1.5.0b6 keeps the entity IDs it
already has, such as `sensor.utility_tariff_import_price`. Installs from before the single entry
keep their entity IDs, history and saved energy history: the first start moves each existing tariff
under the one entry.

Actions such as `find_window` take the integration's entry and an optional `service` (`electricity`
by default, or `gas`) that says which tariff to use.
