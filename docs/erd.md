# FactoryOps — ERD (v1 Pilot)

Logical model only. Quantities are `Decimal(12,3)`. Most operational FKs use `PROTECT`. Unique keys are factory-scoped unless noted.

## Domain flow

```mermaid
flowchart LR
  F[Factory]
  M[Materials]
  P[Production]
  W[Warehouse / FG]
  O[Orders]
  F --> M
  F --> P
  F --> W
  F --> O
  P --> W
  W --> O
```

## Factories and people

```mermaid
erDiagram
  Factory ||--o{ ProductionLine : has
  Factory ||--o{ User : assigns
  ProductionLine ||--o{ Machine : has
  Factory ||--o{ Customer : has
  Factory ||--o{ Warehouse : has
  Factory ||--o{ Material : has
  Factory ||--o{ FinishedGood : has
  Factory ||--o{ ProductionRun : has
  Factory ||--o{ CustomerOrder : has
```

## Materials

```mermaid
erDiagram
  Factory ||--o{ MaterialCategory : has
  Factory ||--o{ Material : has
  MaterialCategory ||--o{ Material : classifies
  UnitOfMeasure ||--o{ Material : measures
  Material ||--o{ StockRecord : counted_as
  Material ||--o{ MaterialBatch : lots
  Material ||--o{ MaterialAddition : receipts
  Material ||--o{ MaterialConsumption : usage
  Material ||--o{ MaterialWaste : waste
  Material ||--o{ MaterialScrap : scrap
  Material ||--o{ StockReconciliation : recon
  MaterialBatch ||--o{ MaterialAddition : received_in
  ProductionRun ||--o{ MaterialConsumption : optional_link
```

**StockRecord** unique on `(factory, material, recording_date)`. Closing quantity may be blank until counted.

**StockReconciliation** unique on `(factory, material, reconciliation_date)`. Result fields stay null until `calculate()`.

## Production and warehouse

```mermaid
erDiagram
  Factory ||--o{ ProductionRun : has
  Factory ||--o{ FinishedGood : has
  Factory ||--o{ Warehouse : has
  ProductionRun ||--o{ ProductionOutput : produces
  ProductionRun ||--o{ ProductionReject : rejects
  FinishedGood ||--o{ ProductionOutput : optional_link
  Warehouse ||--o{ FinishedGoodStockRecord : counted_as
  Warehouse ||--o{ FinishedGoodAddition : receipts
  Warehouse ||--o{ FinishedGoodAdjustment : adjusts
  Warehouse ||--o{ FinishedGoodDispatch : leaves
  Warehouse ||--o{ FinishedGoodReconciliation : recon
  FinishedGood ||--o{ FinishedGoodStockRecord : counted_as
  ProductionOutput ||--o{ FinishedGoodAddition : optional_link
```

**Warehouse** code unique per factory (`FG-MAIN`, `FG-STORE`, `FG-HOLDING`).

**FinishedGoodStockRecord** unique on `(warehouse, finished_good, recording_date)`.

**FinishedGoodAdjustment** quantity is always positive; direction is `INCREASE` or `DECREASE`.

**FinishedGoodDispatch** is “left inventory”, not a sale.

## Orders

```mermaid
erDiagram
  Factory ||--o{ Customer : has
  Customer ||--o{ CustomerOrder : places
  CustomerOrder ||--o{ CustomerOrderLine : lines
  FinishedGood ||--o{ CustomerOrderLine : ordered
  CustomerOrderLine ||--o{ DispatchAllocation : allocated
  CustomerOrderLine ||--o{ OrderReservation : reserved
  FinishedGoodDispatch ||--o{ DispatchAllocation : linked
  Warehouse ||--o{ OrderReservation : committed_at
```

**CustomerOrder** has two independent statuses:

- `status` — commercial (`OPEN`, `PARTIALLY_ALLOCATED`, `ALLOCATED`, `CANCELLED`)
- `fulfilment_status` — physical (`UNFULFILLED`, `PARTIALLY_FULFILLED`, `FULFILLED`), updated only by `calculate_fulfilment()`

**OrderReservation** does not reduce stock and does not create a dispatch.

## Cardinality notes

| Relationship | Rule |
|---|---|
| Material code | Unique per factory |
| Customer code | Unique per factory |
| Order reference | Unique per factory |
| Production run reference | Unique per factory |
| Finished-good code | Unique per factory |
| Warehouse code | Unique per factory |
| Batch lot | Unique per material |
| Same dispatch / line | Multiple allocation rows allowed (history) |
| Same warehouse / line | Multiple reservation rows allowed (history) |

There is **no** `Material.current_quantity` or `FinishedGood.current_quantity`.
