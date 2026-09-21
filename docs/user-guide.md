# FactoryOps — User Guide (v1 Pilot)

This guide is for people running the factory on FactoryOps v1.

Two surfaces:

1. **Django Admin** (`/admin/`) — record what happened
2. **Dashboards** (`/operator/` and others) — see what happened

Dashboards never create stock, production, or order records.

## Sign in

1. Open the site (local default: http://127.0.0.1:8000).
2. Sign in at `/accounts/login/`.
3. You land on the dashboard for your role:
   - Operator / QC → Operator
   - Supervisor → Supervisor
   - Admin → Factory manager

If you have no staff flag, Admin URLs will refuse you. Pilot operators who capture data need **staff access** plus permissions (or work through a supervisor).

## Roles

| Role | Typical work |
|---|---|
| Operator | Record counts, receipts, consumption, waste, production output |
| Supervisor | Review dashboards, calculate reconciliations, check variances |
| Admin | Master data, users, all dashboards, period close |
| QC | Same as operator in v1 (no QC records yet) |

Assign each user a **factory**. Dashboards hide other factories. Platform admins may leave factory blank to see all plants.

## Master data (do this first)

In Admin, create in this order:

1. **Factory** (and optional production line)
2. **Unit of measure** (e.g. kg)
3. **Material category**
4. **Materials** (code unique per factory)
5. **Finished goods** (code unique per factory)
6. **Warehouse** (e.g. `FG-MAIN`)
7. **Customers** (if you will record orders)

Do not skip units or categories. Materials require both.

## Daily capture — raw materials

### Opening / closing count

**Materials → Finished Good Stock Records** is for crates in the warehouse. For raw materials use **Materials → Stock records**.

- One row per factory + material + date
- Opening ≥ 0
- Closing may be blank in the morning; fill it at period end
- Never edit yesterday’s row to “fix” today. Add a new date.

### Receipts

**Materials → Material batches** then **Material additions**.

- Quantity > 0
- Batch belongs to the same material
- Several receipts in one day stay several rows

### Consumption

**Materials → Material consumptions**.

- Quantity > 0
- Optional production run and/or text reference
- Does not change the stock count row

### Waste and scrap

**Materials → Material wastes** and **Material scraps**.

- Separate event types. Do not combine them
- Quantity > 0, reason required
- Production rejects are recorded under **Production**, not here

## Daily capture — production

### Run

**Production → Production runs**

- Reference unique per factory
- `IN_PROGRESS` needs `started_at`
- `COMPLETED` needs `started_at` and `ended_at`
- `ended_at` cannot be before `started_at`

### Output

**Production → Production outputs**

- Quantity > 0
- Provide an output name **or** a finished good (or both)
- Finished good must match the run’s factory

### Rejects

**Production → Production rejects**

- Quantity > 0, reason required
- Rejects are not waste and are not scrap

## Daily capture — finished goods warehouse

### Count

**Production → Finished good stock records**

- Warehouse + finished good + date, unique
- Factory of warehouse must match finished good

### Entering inventory

**Production → Finished good additions**

- Quantity > 0
- Optional link to a production output

### Corrections

**Production → Finished good adjustments**

- Quantity always > 0
- Type `INCREASE` or `DECREASE` (do not enter negative quantities)

### Leaving inventory

**Production → Finished good dispatches**

- This is **not** an invoice or a shipment booking
- It only means goods left the warehouse
- Optional operational reference

## Reconciliation (explicit)

1. Ensure a stock record exists for that date.
2. Create **Stock reconciliation** (materials) or **Finished good reconciliation**.
3. In the list, select rows → **Calculate selected reconciliations**.

Results:

- Expected closing
- Actual closing (from the count)
- Variance = actual − expected

Positive variance: more stock than the events explain. Negative: less.

Calculating does **not** change additions, consumption, waste, or dispatches.

## Orders (if the pilot includes demand)

1. **Customer**
2. **Customer order** (`status` defaults to `OPEN`; `fulfilment_status` defaults to `UNFULFILLED`)
3. **Order lines** (finished good + quantity > 0)
4. **Order reservations** — commitment only; stock counts do not change
5. **Dispatch allocations** — link an existing dispatch to a line

Then open the order and run **Calculate fulfilment** only from code/admin if exposed; fulfilment is `CustomerOrder.calculate_fulfilment()`. It does not change commercial `status`.

Same finished good is required on dispatch and order line. Cross-factory links are rejected.

## Dashboards

See [Dashboard Suite](dashboard-suite.md).

Use Admin to enter; use dashboards to review. If a number looks wrong, find the **source row**, do not edit the dashboard.

## Rules that prevent bad data

- Quantities for movements are > 0
- Counts are ≥ 0
- Inactive factory / material / warehouse / customer blocks **new** operational rows
- History stays as separate rows (`09:00 +500` and `14:00 +300` are two receipts)

## What not to do in v1

- Do not type negative adjustment quantities
- Do not treat dispatch as a customer invoice
- Do not expect stock to fall automatically when you reserve
- Do not use empty Shift / Handover / Downtime / Reports apps
- Do not rely on QC or photo modules — they are not built
