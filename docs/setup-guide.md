# Setup and reconfigure guide

Step by step, with a diagram for each path. The pictures are screenshots of Home Assistant's dark
theme. The integration follows one tariff only, so the country, supplier and plan pictures come from
the Reconfigure flow, which asks the same questions as first setup.

## First setup

```mermaid
flowchart TD
    A[Settings, Devices & services,<br/>Add integration] --> B[Choose Utility Tariffs]
    B --> D[Country]
    D --> F[Supplier and plan,<br/>or Type in my own rates]
    F -->|A plan| G{Prices differ<br/>by area?}
    G -->|yes| H[Area]
    G -->|no| I[Done]
    H --> I
    F -->|Own rates| J[Rates, standing charge,<br/>VAT, timed rates]
    J --> I
    I --> K[Optional: Configure<br/>to add meters]
```

1. Open Settings, Devices & services, then Add integration, and choose **Utility Tariffs**.

   ![Add integration](images/setup-1-add-integration.png)

2. On the first page, pick your country. It starts at your Home Assistant country when the store
   holds it.

   ![Choose a country](images/setup-3-country.png)

3. The second page is one list. **Type in my own rates** is at the top, for a plan that is not in
   the store. Below it is every supplier and plan for the country. Where the store holds only part
   of a country's prices, the page says what is missing. A third page names the plan and asks for
   your area, only where its prices differ by area. Each page shows which step it is. For your own
   rates, a shape page comes first, with flat, day and night, peak and off-peak, cheap midday and
   cheap overnight, so the form starts with the rate names and hours filled in.

4. Open the integration, choose the three dots, then **Configure**, to set the meters, window
   length and bill dates. Each is explained in [Configuration](configuration.md).

   ![Options form](images/setup-4-options.png)

## Reconfigure

Reconfigure changes the plan or your own rates. The sensors keep their entity IDs, history and
place in the Energy dashboard, and the saved energy history is priced again under the new plan.

```mermaid
flowchart TD
    A[Open the integration,<br/>three dots, Reconfigure] --> B{Change to?}
    B -->|A store plan| C[Country, supplier,<br/>plan, area]
    B -->|My own rates| D[Rates form]
    C --> E[Integration reloads]
    D --> E
    E --> F[Same entity IDs and history,<br/>energy history re-priced]
```

1. Open the integration, choose the three dots, then **Reconfigure**.

   ![Reconfigure menu](images/reconfigure-1-menu.png)

2. Pick another country, supplier, plan or area.

   ![Pick another plan](images/reconfigure-2-plan.png)

3. To change your own rates, enter the new rates in the form. Changing the rates means
   reconfiguring again.

   ![Own rates form](images/reconfigure-3-own-rates.png)

## Configure or reconfigure?

| You want to change | Use |
| --- | --- |
| Plan, supplier, area or your own rates | Configure, Tariff (or Reconfigure) |
| Meters, battery, bill dates, window length, the other fuel | Configure, on the page for that topic |
