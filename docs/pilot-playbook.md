# FactoryOps — Pilot Playbook (v1)

How to run a real factory week on this system without turning it into an ERP project.

## Goal for the pilot

Prove that the plant can **record** and **see**:

- daily material counts and movements
- production runs and output
- waste / scrap / rejects
- finished-good warehouse counts and dispatches
- (optional) customer orders vs dispatches

Do **not** try to replace finance, transport, or CRM in this pilot.

## People

| Seat | System role | Staff in Admin? |
|---|---|---|
| Floor recorder | OPERATOR | Yes, limited to operational models |
| Shift lead | SUPERVISOR | Yes |
| Plant lead | ADMIN | Yes |
| QC inspector | QC | Optional; same screens as operator in v1 |

Create users **before** day 1. Assign `factory`. Create at least one Admin who understands reconciliations.

## Week 0 — setup (half day)

1. Install from [setup.md](setup.md). `migrate`, `check`, `pytest`.
2. Create Factory, UoM, categories, materials, finished goods, warehouse `FG-MAIN`.
3. Optional: customers for 2–3 real buyers.
4. Seed **yesterday’s** closing as **today’s** opening on Stock records if you have a physical count.
5. Walk the operator through one complete material loop in Admin (count → receipt → consumption → waste).
6. Confirm dashboards: operator sees today’s consumption; supervisor sees open runs.

Stop if master data is messy. Do not start capturing live events against duplicate material codes.

## Daily loop (materials + production)

**Morning**

1. Opening stock count for materials you will use today (`Stock record`, closing blank).
2. Confirm or start a `Production run` (`IN_PROGRESS` + `started_at`).

**During the shift**

3. Receipts → batch then addition (do not lump two trucks into one row).
4. Consumption against the run when material is issued.
5. Waste / scrap when loss is known.
6. Production output when product is counted off the line.
7. Rejects when output is rejected.

**End of shift**

8. Closing quantity on the material stock record.
9. Finished-good count on `Finished good stock record` if product went to store.
10. FG addition if product entered the warehouse; dispatch if it left.
11. Supervisor opens `/supervisor/` and `/inventory/`. Investigate missing closings and outstanding reconciliations.

## Daily loop (orders, if in scope)

1. Customer order + lines when demand is known.
2. Reservation against `FG-MAIN` **only if** you want commitment visibility. It will not reduce the count.
3. When goods leave, record **dispatch**, then **allocation** to the order line.
4. Admin/supervisor runs fulfilment calculation when you want status to move off `UNFULFILLED`.

If the pilot is “count and produce only”, skip this loop entirely. The rest of the system still works.

## Weekly close

1. For each material with a complete count: create `Stock reconciliation` for that date → calculate.
2. Same for finished goods if warehouse counts exist.
3. On `/manager/` or `/executive/`, review non-zero variances.
4. Variances are questions, not automatic stock corrections. If the count is wrong, record a new count or an FG adjustment. Do not silently edit history.

## What “good” looks like after two weeks

- Every production day has at least one stock record with opening **and** closing for the main materials
- Every run has output rows (and rejects if they happened)
- Waste is not hidden inside consumption
- Supervisor can name yesterday’s variance without exporting to Excel
- Nobody has invented a spreadsheet that duplicates FactoryOps

## Failure modes to watch

| Symptom | Likely cause | Fix |
|---|---|---|
| Dashboard empty | Events not today UTC, or user factory mismatch | Check timestamps and user.factory |
| Cannot save addition | Batch is another material, or inactive master | Fix batch / activate master |
| Recon calculate fails | No stock record for that date | Create the count first |
| Operator 403 on dashboard | Wrong role | Use operator user |
| Quick action 403 | Not staff / no add permission | Grant Admin access or capture via supervisor |
| “Stock didn’t drop” after reservation | Expected | Reservations do not reduce counts |
| Two receipts became one row | Operator overwrote | Train: new row per event |

## Explicitly out of the pilot

- Invoices, delivery notes, transporters
- Warehouse-to-warehouse transfers
- AI forecasts
- Building the empty shift/handover/downtime apps
- Changing reconciliation formulas mid-pilot

## After the pilot (only if earned)

Justified next steps, in order:

1. Simple operator capture screens (so Admin is not the floor UI)
2. CSV/Excel export of the same queries the dashboards use
3. Photo evidence on waste / reject / recon
4. A small QC check record

Not next: AI, ERP modules, bin locations.
