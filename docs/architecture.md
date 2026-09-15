# FactoryOps — Architectural Overview

## Architectural Principles

FactoryOps is built on four core tenets:
1. **Local-First & Offline Capable**: Designed for factory floor environments where internet connectivity can be intermittent or unavailable.
2. **Modular Monolith**: Clean domain boundaries between domain apps (`accounts`, `factories`, `machines`, `shifts`, `downtime`, `maintenance`, `telemetry`, `reports`). All apps reside within a single codebase for speed, deployability, and simple transactional integrity.
3. **Deterministic Truth**: Core operational data is deterministic, fully audited, and stored in standard relational storage. AI or machine learning is purely an optional intelligence layer, never the primary source of truth.
4. **Role-Based Security**: Clear separation between `ADMIN`, `SUPERVISOR`, `OPERATOR`, and `QC` roles enforced at model and view levels.

## Module Map

```
apps/
├── accounts/      # Custom User model, Role TextChoices, auth workflows
├── factories/     # Factory plant structures, locations, and ProductionLines
├── machines/      # Industrial assets, machine codes, and operational status
├── dashboard/     # High-level operational command center UI
```

## Database & Settings Strategy
- **Settings Hierarchy**: `config/settings/base.py` contains common core settings loaded via `python-dotenv`. Environment overrides exist in `development.py` and `production.py`.
- **Database**: Local development utilizes SQLite with zero native C-library dependencies, allowing instant bootstrapping on any factory terminal.
