# ADR-001: Selection of Modular Monolith Architecture for FactoryOps

* **Status**: Accepted
* **Date**: 2026-09-15
* **Context**: FactoryOps needs to support immediate local deployment on single factory servers while keeping open the path to multi-factory cloud aggregation. microservices introduce unnecessary network complexity, deployment overhead, and distributed transaction challenges for local factory deployments.

## Decision
We adopt a **Modular Monolith** architecture pattern using Django applications (`apps/*`) with explicit boundary boundaries:
- Each domain (accounts, factories, machines, shifts, telemetry) is encapsulated in its own Django app under `apps/`.
- Domain models cross-reference using standard Django ForeignKeys with explicit `related_name` conventions.
- Direct database cross-querying between modules is strictly governed, laying the ground for eventual microservice extraction if ever warranted.

## Consequences
### Positive
- Single database transaction boundary for complex shift handovers.
- Zero network overhead for local operational reads/writes.
- Simplified CI/CD pipeline and single deployment artifact.
- Rapid developer velocity.

### Negative / Risks
- Developers must maintain strict module boundaries to prevent spaghetti coupling.
- Enforced with automated code reviews and modular test suites.
