# FactoryOps — Dashboard Suite (v1 Pilot)

Five read-only dashboards over existing models. No new inventory or production domains.

Login home (`/` and `/dashboard/`) redirects:

| Role | Lands on |
|---|---|
| Operator, QC | `/operator/` |
| Supervisor | `/supervisor/` |
| Admin | `/manager/` |

## Access

| Dashboard | Path | OPERATOR | QC | SUPERVISOR | ADMIN |
|---|---|---|---|---|---|
| Operator | `/operator/` | Yes | Yes | Yes | Yes |
| Supervisor | `/supervisor/` | No | No | Yes | Yes |
| Inventory | `/inventory/` | No | No | Yes | Yes |
| Manager | `/manager/` | No | No | No | Yes |
| Executive | `/executive/` | No | No | No | Yes |

Unauthenticated users are sent to login. Wrong role receives HTTP 403.

Factory-assigned users only see their factory. Admin users with no factory see all factories.

Dates are **UTC calendar days**, last **7 days** for trends.

## 1. Operator — daily execution

**Shows**

- Open / planned production runs
- Runs started today
- Materials consumed today (total + rows)
- Recent material additions
- Waste logged today
- Stock counts still missing closing quantity
- Quick actions (Admin add pages)

**Does not**

- Create records (links go to Admin)
- Show costing or QC

**Reads:** `ProductionRun`, `MaterialConsumption`, `MaterialAddition`, `MaterialWaste`, `StockRecord`

## 2. Supervisor — oversight

**Shows**

- In-progress runs
- Today’s output, waste, rejects
- Outstanding material and finished-good reconciliations (`calculated_at` empty)
- Recent non-zero material variances
- 7-day output trend (bar width from max day)

**Reads:** `ProductionRun`, `ProductionOutput`, `MaterialWaste`, `ProductionReject`, `StockReconciliation`, `FinishedGoodReconciliation`

## 3. Factory manager — performance

Admin-only. There is no separate “manager” role.

**Shows**

- 7-day material usage, output, waste totals and daily series
- Order fulfilment status counts
- Recent material variances and reconciliation history
- Recent warehouse dispatches

**Reads:** `MaterialConsumption`, `ProductionOutput`, `MaterialWaste`, `StockReconciliation`, `CustomerOrder`, `FinishedGoodDispatch`

## 4. Executive — high level

Admin-only. Same 7-day window. No operational tables beyond significant variances.

**Shows**

- Production, consumption, waste, reject totals
- Fulfilled vs unfulfilled order counts
- Significant material variances (non-zero, in window)

**Reads:** same operational tables, aggregated

## 5. Inventory — control

**Shows**

- Latest **material** `StockRecord` per factory+material
- Latest **finished-good** stock record per warehouse+item
- Today’s additions and consumption
- Reconciliation exceptions (non-zero variance)
- Recent dispatches

Snapshots are the latest **count**, not a perpetual computed on-hand (reservations are not subtracted here; that lives in `calculate_available_stock()` for planning).

**Reads:** `StockRecord`, `FinishedGoodStockRecord`, `MaterialAddition`, `MaterialConsumption`, `StockReconciliation`, `FinishedGoodDispatch`

## Implementation

| Piece | Path |
|---|---|
| Aggregations | `apps/dashboard/services.py` |
| Permissions | `apps/dashboard/permissions.py` |
| Views | `apps/dashboard/views.py` |
| Templates | `templates/dashboard/*.html` |

Services **only read**. They do not call `calculate()` on reconciliations or fulfilment.

## Known limits

- Quick actions require Django staff + model permissions
- No charts library; trends are tables (supervisor uses a simple bar)
- No Excel export
- Empty shift/downtime apps are not shown
