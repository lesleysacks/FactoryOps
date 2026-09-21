# FactoryOps — System Health Report (v1 Pilot)

Snapshot of the codebase as of the v1 dashboard exercise. This is an engineering status report, not a live plant KPI feed.

## Verdict

**The operational core is healthy enough for a supervised factory pilot.**  
**The shop-floor UI is Admin-only.**  
**Original QC / photos / Excel / AI milestones are not built — by design at this checkpoint.**

## Automated health

| Check | Result |
|---|---|
| `python manage.py check` | No issues (0 silenced) |
| `pytest` | **233 passed** (M1–M12 plus 15 dashboard tests) |
| `makemigrations` materials / production / orders | Clean |
| `makemigrations --check` (whole project) | Fails only on pre-existing `accounts.0002_alter_user_managers` |

Leave `accounts.0002_alter_user_managers` untouched until an accounts cleanup is scheduled.

## Domain health

| Domain | Models | Tests | Notes |
|---|---|---|---|
| Accounts | User + roles | Present | Manager drift uncommitted |
| Factories | Factory, ProductionLine | Present | Thin, adequate |
| Machines | Machine + status | Present | No telemetry |
| Materials | Full RM ledger + recon | Present | M1–M4, M6–M7, M8 consumption link |
| Production | Runs, FG, warehouse, dispatch, recon | Present | M5, M6 rejects, M8–M10 |
| Orders | Customer, order, allocation, reservation | Present | M11–M12 |
| Dashboard | Views + aggregations | 15 tests | Read-only |
| Shifts / Handovers / Downtime / Reports | Empty models | Empty | Stubs in `INSTALLED_APPS` |

## Formula integrity (do not change in pilot)

- Material expected closing = opening + additions − consumption − waste − scrap  
  Date filter: UTC date of DateTime events.
- FG expected closing = opening + additions + INCREASE − DECREASE − dispatches
- Available FG = latest **non-null** closing count − all reservations for that warehouse + finished good
- Fulfilment from **dispatch allocations**, not from reservations
- Rejects are **not** in the material recon formula

SQLite `Sum` on decimals is quantized to 0.001 in services.

## Known defects and debt

| Item | Severity | Pilot impact |
|---|---|---|
| `accounts.0002_alter_user_managers` uncommitted | Low | Ignore during pilot |
| `requirements.txt` pins Django 6.1.1; runtime observed 5.2.17 | Medium | Pin to the version you actually run before production deploy |
| `requirements-dev.txt` pins pytest 8.3.5; runtime observed 9.x | Low | Dev-only |
| `LOGIN_REDIRECT_URL=/dashboard/` | Resolved | Alias route exists |
| Dashboards write nothing; operators need staff to capture | High for unattended floor | Assign staff or pair with supervisor |
| `MEDIA_ROOT` reserved; no photo models | Low | Ignore |
| QC role has no QC tables | Low | QC users use operator dashboard |
| Empty apps still installed | Low | Do not demo them |
| UTC-only timestamps | Medium | Align shift clocks with UTC or accept date-boundary surprises |

## Security (pilot)

- Auth required on dashboards
- Role gates on each dashboard
- Factory scoping when `user.factory` is set
- `SECRET_KEY` from environment; do not commit `.env`
- `DEBUG` must be false on any network-exposed host
- Admin is powerful — limit staff users

This is **not** a hardened multi-tenant SaaS review.

## Fit vs original early roadmap

Completed as intended: materials foundation through production output and waste.

Replaced: QC (M7 original), photos (M8 original), dashboards (M10 original — now present), Excel (M11 original), AI (M12 original).

Added beyond original: FG warehouse ledger, dispatch, customers, allocations, reservations, fulfilment.

## Go / no-go for pilot

**Go** if:

- One factory, named users, Admin capture is acceptable
- You will calculate recon explicitly at period end
- You will not promise invoicing or AI

**No-go** if:

- Operators cannot use a browser Admin form
- You need QC sign-off in the system on day one
- You need bin-level warehousing or customer invoices

## Recommended freeze

For the duration of the v1 pilot, freeze:

- Reconciliation formulas
- Model rebuilds of materials / production / orders
- New domains (transfers, CRM, AI)

Allow only: bugfixes, permissions, documentation, and operator-capture screens if the floor cannot use Admin.
