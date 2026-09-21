# FactoryOps — Architecture (v1 Pilot)

## Principles

1. **Modular monolith.** One Django project, domain apps under `apps/`, one database, one deployable.
2. **Event history, not running balances.** Masters do not store `current_quantity`. Counts and movements are separate rows.
3. **Deterministic truth.** Reconciliation, availability, and fulfilment are explicit service calculations. AI is not in v1 and is not a source of truth.
4. **Factory integrity.** Materials, warehouses, finished goods, customers, and orders must share the same factory.
5. **Role-based access.** `ADMIN`, `SUPERVISOR`, `OPERATOR`, `QC` on the user model. Dashboards enforce role. Capture is Django Admin.

## Operational flow

```
Raw materials
    StockRecord / Addition / Consumption / Waste / Scrap
        → StockReconciliation.calculate()
            ↓
Production
    ProductionRun → ProductionOutput → FinishedGood
            ↓
Finished-goods warehouse
    StockRecord / Addition / Adjustment / Dispatch
        → FinishedGoodReconciliation.calculate()
            ↓
Commercial demand
    CustomerOrder → OrderLine → OrderReservation
                 → DispatchAllocation → fulfilment_status
```

## Domain map

| App | Role in v1 | Status |
|---|---|---|
| `apps.accounts` | User, roles, factory assignment | Active |
| `apps.factories` | Factory, production line | Active |
| `apps.machines` | Asset register + status | Thin (no telemetry) |
| `apps.materials` | RM inventory events + recon | Active |
| `apps.production` | Runs, output, warehouse, FG inventory | Active |
| `apps.orders` | Customers, orders, allocation, reservations | Active |
| `apps.dashboard` | Role dashboards (read-only) | Active |
| `apps.shifts` | — | Stub |
| `apps.handovers` | — | Stub |
| `apps.downtime` | — | Stub |
| `apps.reports` | — | Stub |

## Calculation boundaries

All of these are **opt-in**. Saving a source row does not recompute them.

| Calculation | Location | Formula |
|---|---|---|
| Material expected closing | `apps.materials.services` | opening + additions − consumption − waste − scrap |
| FG expected closing | `apps.production.services` | opening + additions + INCREASE − DECREASE − dispatches |
| Available FG stock | `apps.orders.services` | latest counted closing − reservations |
| Order fulfilment | `apps.orders.services` | dispatch allocations vs ordered qty |

Date windows use **UTC calendar dates** (`TIME_ZONE=UTC`).

## Capture vs display

- **Capture:** Django Admin. Dashboards do not insert inventory, production, or order rows.
- **Display:** `/operator/`, `/supervisor/`, `/manager/`, `/executive/`, `/inventory/`.
- **Home** (`/` and `/dashboard/`) redirects by role.

## Settings shape

- `config/settings/base.py` — shared
- `config/settings/development.py` — local
- Secrets from `.env` (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`)
- `AUTH_USER_MODEL = accounts.User`
- SQLite for local / pilot unless operations later choose PostgreSQL

## Out of architecture (v1)

Invoicing, pricing, CRM, freight, procurement, accounting, warehouse transfers, bin locations, QC workflows, photos, Excel export, AI.

## Decision record

Historical ADR: [ADR-001 Modular monolith](decisions/ADR-001-modular-monolith.md). Domain list in that ADR is older than v1 (it predates materials / production / orders). This document is the current map.
