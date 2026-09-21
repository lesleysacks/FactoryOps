# FactoryOps v1 Pilot Package

FactoryOps is a Django modular monolith for a **single-factory operational pilot**.

It records what happened on the floor — materials, production, warehouse events, and customer demand — and shows that history on role dashboards. It is **not** an ERP, WMS, CRM, or accounting system.

## What v1 can answer

**Raw materials:** What arrived? What was consumed? What was lost? What should remain? What was counted?

**Production:** Which run ran? What was produced? What was rejected?

**Finished goods:** What entered the warehouse? What left? What should remain? What was counted?

**Demand:** Who ordered it? Which dispatch was linked to which order? How much is reserved? Is the order fulfilled?

## Package contents

| Document | Purpose |
|---|---|
| [Architecture](docs/architecture.md) | Domains, principles, and what is in / out of v1 |
| [ERD](docs/erd.md) | Entity relationships by domain |
| [User Guide](docs/user-guide.md) | Login, Admin capture, dashboards |
| [Dashboard Suite](docs/dashboard-suite.md) | Five role dashboards and data sources |
| [Pilot Playbook](docs/pilot-playbook.md) | How to run a factory week on this system |
| [System Health Report](docs/system-health.md) | Tests, gaps, risks, deferred work |
| [Local setup](docs/setup.md) | Install, migrate, run |

## v1 scope

**In**

- Material master, stock counts, receipts, consumption, waste, scrap
- Production runs, output, rejects, finished-good master
- Warehouse, finished-good stock events, dispatch, reconciliation
- Customers, orders, dispatch allocation, reservations, availability, fulfilment status
- Role dashboards (operator, supervisor, manager, executive, inventory)
- Django Admin as the capture surface

**Out**

- Invoicing, pricing, CRM, freight, procurement, accounting
- Warehouse transfers, bins, aisles, racks
- QC workflows, operational photos, Excel export, AI
- Shift / handover / downtime apps (stubs only)

## Roles

| Role | Capture | Dashboards |
|---|---|---|
| Operator | Admin (if given staff access) | Operator |
| QC | Same as operator until QC records exist | Operator |
| Supervisor | Admin | Operator, Supervisor, Inventory |
| Admin | Admin | All dashboards |

## Daily path

1. Operators record events in **Django Admin** (`/admin/`).
2. Supervisors open **dashboards** (`/supervisor/`, `/inventory/`).
3. Reconciliations are **calculated explicitly** — they do not run on save.
4. History is never overwritten. Corrections are new events or adjustments.

## Run locally

See [docs/setup.md](docs/setup.md). Short path:

```powershell
Copy-Item .env.example .env
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- App: http://127.0.0.1:8000
- Admin: http://127.0.0.1:8000/admin

## Engineering rules that still apply

- Extend, never rebuild
- Event history over running balances
- `DecimalField(12, 3)` for quantities
- Calculations in services, not `save()`
- Additive migrations only
- Leave `accounts.0002_alter_user_managers` untouched until a dedicated accounts cleanup
