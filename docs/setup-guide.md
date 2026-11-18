# Setup and reconfigure guide

Step by step, with a diagram for each path. The pictures are screenshots of Home Assistant's dark
theme. The integration follows one tariff only, so the country, supplier and plan pictures come from
the Reconfigure flow, which asks the same questions as first setup.

## First setup

```mermaid
flowchart TD
    A[Settings, Devices & services,<br/>Add integration] --> B[Choose Utility Tariffs]
    B --> C{How do you want to<br/>set the tariff?}
    C -->|Pick a plan from the store| D[Country]
    D --> E[Supplier]
    E --> F[Plan]
    F --> G{Prices differ<br/>by area?}
    G -->|yes| H[Area]
    G -->|no| I[Done]
    H --> I
    C -->|Type in my own rates| J[Rates, standing charge,<br/>VAT, timed rates]
    J --> I
    I --> K[Optional: Configure<br/>to add meters]
```

1. Open Settings, Devices & services, then Add integration, and choose **Utility Tariffs**.

   ![Add integration](images/setup-1-add-integration.png)

2. Choose **Pick a plan from the store**, or **Type in my own rates**.

   ![Choose how to set the tariff](images/setup-2-choose-source.png)

3. For a store plan, pick the country on the first page. The second page lists every supplier and
   plan for that country in one list. Where the store holds only part of a country's prices, the
   page says what is missing. A third page asks for your area, only where the plan's prices differ
   by area. Each page shows which step it is.

   ![Choose a country](images/setup-3-country.png)

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
| Plan, supplier, area or your own rates | Reconfigure |
| Meters, window length, bill dates, battery details | Configure (options) |
