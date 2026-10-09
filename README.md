# FactoryOps

FactoryOps is a Django modular monolith for factory floor inventory, production, and fulfilment visibility. It records material and finished-good events as history, calculates reconciliations explicitly, and presents role-scoped dashboards for a supervised plant pilot.

Remote: [https://github.com/lesleysacks/FactoryOps.git](https://github.com/lesleysacks/FactoryOps.git)

---

## Vision

Give a single factory a reliable operational record: what came in, what was consumed or wasted, what was produced, what left the warehouse, and how that compares to customer demand — without becoming a full ERP, CRM, or finance system.

---

## Current Status (verified from this repository)

**Active / usable for a supervised pilot**

| Area | What exists |
|---|---|
| Accounts | Custom `User` with roles `ADMIN`, `SUPERVISOR`, `OPERATOR`, `QC`; optional factory assignment |
| Factories | `Factory`, `ProductionLine` |
| Machines | Asset register + status (no telemetry) |
| Materials | Stock counts, batches, additions, consumption, waste, scrap, stock reconciliation |
| Production | Runs, output, rejects, material state, FG warehouse ledger, FG additions/adjustments/dispatches, FG reconciliation |
| Orders | Customers, orders/lines, dispatch allocations, reservations, fulfilment status calculation |
| Dashboard | Role homes + read-only supervisor/manager/executive/inventory views |
| Operator capture UI | Floor UI for stock counts/closing, material receipts, start run, output, consumption, material state, complete run |
| Auth | Login / logout under `/accounts/` |
| Admin | Django Admin for master data and full capture |

**Stub apps installed but not productised:** `apps.shifts`, `apps.handovers`, `apps.downtime`, `apps.reports` (empty / placeholder models).

**Not built (by design at this checkpoint):** dedicated QC workflows, photo evidence models, Excel export, AI, invoicing, procurement, bin locations, warehouse transfers, PostgreSQL/Docker deploy pack.

---

## In Development / Planned

Treat these as direction, not delivery promises:

- Harden pilot feedback (operator capture, reconciliation UX)
- Keep stub apps dormant until a real factory need appears
- Production hardening for a Windows factory PC is documented below (Waitress, startup tasks, backups). The database stays SQLite. PostgreSQL is not configured.
- Future domains only when pilot data proves the need (QC records, photos, exports) — not before

See also [docs/system-health.md](docs/system-health.md) and [docs/pilot-playbook.md](docs/pilot-playbook.md).

---

## Core Workflow

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

Captures may go through **Django Admin** and/or the **operator floor UI** (inventory + production paths under `/operator/…`). Dashboards under `/supervisor/`, `/manager/`, `/executive/`, and `/inventory/` are read-oriented aggregations over existing rows.

---

## User Roles

| Role | Typical use in v1 |
|---|---|
| `OPERATOR` | Floor capture + operator dashboard |
| `QC` | Same operator surfaces in v1 (no QC tables yet) |
| `SUPERVISOR` | Supervisor + inventory dashboards; oversight |
| `ADMIN` | Manager + executive dashboards; master data; full Admin |

Login home (`/` and `/dashboard/`) redirects by role. Assign each user a `factory` so scoping works. Platform admins may leave factory blank to see all plants.

---

## Tech Stack

- **Python** 3.12+ (local runtime has also been used with newer 3.x)
- **Django** (see `requirements.txt` pin)
- **SQLite** for local / pilot database
- **python-dotenv** for `.env` loading
- **pytest** + **pytest-django** for tests (`requirements-dev.txt`)

No React, FastAPI, or Docker requirement for local pilot use.

---

## Repo Structure

```
FactoryOps/
├── apps/
│   ├── accounts/      # User + roles
│   ├── factories/     # Factory, production line
│   ├── machines/      # Machine register
│   ├── materials/     # RM inventory + reconciliation
│   ├── production/    # Runs, FG warehouse, FG recon
│   ├── orders/        # Customers, orders, reservations
│   ├── dashboard/     # Role dashboards + operator capture
│   ├── shifts/        # Stub
│   ├── handovers/     # Stub
│   ├── downtime/      # Stub
│   └── reports/       # Stub
├── config/            # Django project (settings, urls, wsgi/asgi)
├── templates/         # Project templates
├── static/            # CSS / favicon
├── docs/              # Architecture, setup, pilot docs
├── tests/             # Cross-cutting config tests
├── manage.py
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── .env.example
└── README.md
```

---

## Installation (Windows primary)

```powershell
git clone https://github.com/lesleysacks/FactoryOps.git
cd FactoryOps

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

Copy-Item .env.example .env
```

Then generate a secret key and put it in `.env` (see Environment Configuration).

Linux / macOS equivalents: `python3 -m venv .venv`, `source .venv/bin/activate`, `cp .env.example .env`.

Full walkthrough: [docs/setup.md](docs/setup.md).

---

## Dependencies

| File | Purpose |
|---|---|
| `requirements.txt` | Runtime (Django, dotenv, tzdata) |
| `requirements-dev.txt` | Includes runtime + pytest, pytest-django, coverage |

Install both for local development and testing.

---

## Environment Configuration

`.env` is **required** for local runs. `config/settings/base.py` loads it via `python-dotenv` and reads:

| Variable | Meaning |
|---|---|
| `SECRET_KEY` | Django secret (required; no Python default) |
| `DEBUG` | `True` or `False` (string compare to `'True'`) |
| `ALLOWED_HOSTS` | Comma-separated hostnames |

### Generate `SECRET_KEY`

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Paste the result into `.env`:

```env
SECRET_KEY=<paste-generated-value>
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

Never commit `.env`. Prefer the placeholder in `.env.example` only as a template.

---

## Database Setup

```powershell
python manage.py migrate
python manage.py createsuperuser
```

`createsuperuser` defaults the new user to role `ADMIN`. In Admin, assign a factory so dashboards scope correctly. Seed master data (UoM, categories, materials, finished goods, warehouse) before live capture — see [docs/user-guide.md](docs/user-guide.md) and [docs/pilot-playbook.md](docs/pilot-playbook.md).

---

## Verify Installation

```powershell
python manage.py check
python manage.py makemigrations --check
python -m pytest
```

`makemigrations --check` may report pre-existing drift on `accounts` user managers; that is known and left untouched unless an accounts cleanup is scheduled. See [docs/system-health.md](docs/system-health.md).

---

## Run Locally

```powershell
python manage.py runserver
```

- App / role home: http://127.0.0.1:8000  
- Admin: http://127.0.0.1:8000/admin  

Default settings module: `config.settings.development` (set in `manage.py`).

---

## LAN / Factory-PC Testing (development server only)

This section uses Django's development server. Do **not** use it as the factory production process. The production procedure is [Factory PC deployment](#factory-pc-deployment-windows).

Bind the dev server to all interfaces:

```powershell
python manage.py runserver 0.0.0.0:8000
```

1. Find this PC’s IPv4 address:
   - **Windows:** `ipconfig`
   - **Linux:** `ip addr`
   - **macOS:** `ifconfig`
2. Add that address to `.env` (comma-separated, no quotes/brackets):

```env
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.105
```

3. Restart `runserver`.
4. On a phone/tablet/other PC on the same LAN, open `http://<that-ip>:8000`.

Do **not** hardcode LAN IPs in Python. Do **not** set `ALLOWED_HOSTS=*`. Keep `DEBUG=False` on any long-lived network-exposed host.

---

## LAN Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `DisallowedHost` / Invalid HTTP_HOST | IP missing from `ALLOWED_HOSTS` | Add the exact host (no port) to `.env`, restart |
| Page works on PC, not on phone | Wrong IP, Wi‑Fi isolation, or firewall | Confirm `ipconfig` IP; allow TCP 8000; same subnet |
| `KeyError: 'SECRET_KEY'` | Missing `.env` or empty key | Copy `.env.example` → `.env` and generate a key |
| Host still rejected after edit | Server not restarted / wrong `.env` path | Restart from project root; `.env` must sit next to `manage.py` |
| Used Python list syntax in `.env` | dotenv expects `key=value` | Use `ALLOWED_HOSTS=localhost,127.0.0.1,<ip>` only |

---

## Development Commands

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py runserver
python manage.py runserver 0.0.0.0:8000
python manage.py migrate
python manage.py makemigrations
python manage.py makemigrations --check
python manage.py check
python manage.py createsuperuser
python -m pytest
python -m pytest -k settings_env
coverage run -m pytest
coverage report
```

---

## Configuration Rules

1. `SECRET_KEY` comes only from the environment — never hardcode a real key in source.
2. `ALLOWED_HOSTS` comes only from the environment as a comma-separated list.
3. No LAN IP literals in Python settings.
4. No `ALLOWED_HOSTS=*`.
5. `.env` is gitignored; commit `.env.example` placeholders only.
6. Do not change domain models or reconciliation formulas for environment-only work.

---

## Security

- Dashboards require authentication; roles gate paths.
- Factory-assigned users are scoped to their factory.
- Admin is powerful — limit staff users in a pilot.
- Never commit secrets, SQLite DBs with plant data, or `media/` uploads.
- For any host reachable beyond localhost, set `DEBUG=False` and tighten `ALLOWED_HOSTS`.

This pilot stack is **not** a hardened multi-tenant SaaS review.

---

## Testing

```powershell
python -m pytest
```

Tests live under each `apps/*/tests.py` / `test_*.py` and cross-cutting cases under `tests/`. Config uses `pytest.ini` with `DJANGO_SETTINGS_MODULE=config.settings.development`.

Do not treat historical pass counts in older docs as live truth — re-run the suite after pulls.

---

## Architecture Principles

1. **Modular monolith** — one Django project, domain apps under `apps/`, one database.
2. **Event history, not running balances** — masters do not store `current_quantity`.
3. **Deterministic truth** — reconciliations and fulfilment are explicit service calculations.
4. **Factory integrity** — materials, warehouses, finished goods, customers, and orders share a factory.
5. **Role-based access** — enforced on dashboards and capture views.

Details: [docs/architecture.md](docs/architecture.md), [docs/dashboard-suite.md](docs/dashboard-suite.md), ADR: [docs/decisions/ADR-001-modular-monolith.md](docs/decisions/ADR-001-modular-monolith.md).

---

## Roadmap

Near-term focus is pilot stability, not greenfield rebuilds:

1. Supervised factory pilot with Admin + operator capture
2. Environment / deploy hygiene (`DEBUG`, hosts, secrets)
3. Only then: QC records, photos, exports, or AI — if the plant asks for them with real data

Stub apps (`shifts`, `handovers`, `downtime`, `reports`) stay dormant until needed.

---

## Factory Pilot

Use [docs/pilot-playbook.md](docs/pilot-playbook.md) for week-0 setup and the daily materials/production loop. Go / no-go criteria live in [docs/system-health.md](docs/system-health.md).

**Go** if one factory, named users, and Admin/operator browser capture are acceptable.  
**No-go** if you need day-one QC sign-off, bin-level warehousing, or invoices inside this system.

---

## Factory PC deployment (Windows)

This is the production procedure for a dedicated factory PC. It is separate from `python manage.py runserver`.

The application has **not** been installed on a factory PC from this repository checkout. Install it on the target Windows computer using the steps below. Python tests for configuration, health, backup, and restore run in development; the PowerShell scripts themselves run only on Windows.

### 1. Supported operating system and prerequisites

- Windows 10 or Windows 11, 64-bit, on the factory PC.
- Python 3.12 or newer, with the `py` launcher enabled. The pinned Django release is in `requirements.txt`.
- PowerShell 5.1 (included with Windows). Run the installer from an elevated PowerShell.
- Microsoft Edge (included with Windows 10/11) for the login window.
- No internet connection is required after dependencies have been installed. Templates and static files do not load remote assets.
- The first `pip install` needs either internet or a wheelhouse prepared on another machine. Daily operation does not call GitHub or other external services.

Development commands (`runserver`, `pytest`) stay on a developer machine. Do not use them as the factory server.

### 2. Installation on a clean PC

Default directory: `C:\FactoryOps`. Pass `-InstallRoot` to use another path.

From an elevated PowerShell, in the extracted FactoryOps folder:

```powershell
Set-Location C:\path\to\FactoryOps
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\windows\Install-FactoryOps.ps1 -InstallRoot C:\FactoryOps -DesktopUser '.\FactoryOperator' -LanAddress '10.0.0.20' -ConfigureFirewall
```

Replace `10.0.0.20` with this PC's Ethernet IPv4 address (`ipconfig`). Replace `.\FactoryOperator` with the Windows account that should see the login window. Omit `-DesktopUser` if you will open the window from a shortcut instead.

The installer:

1. Checks that Windows and Python 3.12+ are present.
2. Copies the application to `C:\FactoryOps\app` (it does not copy `.env`, SQLite files, or media).
3. Creates `C:\FactoryOps\venv` if it is missing and installs `requirements.txt`.
4. Writes `C:\FactoryOps\config\factoryops.env` only when that file is absent.
5. Validates production settings, runs `migrate` once, runs `collectstatic`, and runs `check --deploy`.
6. Registers Task Scheduler jobs and an optional private-network firewall rule.

Re-running the installer does not rotate `SECRET_KEY`, delete `C:\FactoryOps\data`, or replace media.

Create the first administrator yourself. The password is not stored in a script:

```powershell
cd C:\FactoryOps\app
..\venv\Scripts\python.exe manage.py createsuperuser
```

`createsuperuser` assigns the `ADMIN` role. In Admin, assign a factory to each user. Nobody is logged in automatically.

### 3. First-time configuration

Production settings are `config.settings.production`. `manage.py` still defaults to development settings, so the factory scripts set `DJANGO_SETTINGS_MODULE` themselves.

`C:\FactoryOps\config\factoryops.env` holds hosts, paths, and the secret. `C:\FactoryOps\config\factoryops.public` holds only the port and bind address so the desktop shortcut can read them without opening the secret file.

| Path | Contents |
|---|---|
| `C:\FactoryOps\data\db.sqlite3` | SQLite database |
| `C:\FactoryOps\data\media` | Uploaded files |
| `C:\FactoryOps\staticfiles` | Collected static files |
| `C:\FactoryOps\logs` | Application and backup logs |
| `C:\FactoryOps\backups` | Dated verified backups |

The database engine is still SQLite. `FACTORYOPS_SQLITE_PATH` only changes the file location. Do not point it at a PostgreSQL URL.

### 4. Secure SECRET_KEY creation and storage

The installer generates one key with Django's `get_random_secret_key()` and writes it into `factoryops.env`. Later starts and reinstalls keep that key. FactoryOps does not generate a new key on each start.

The installer then limits the file to SYSTEM (read) and Administrators (full control). It does not print the key. Do not commit the file, copy it into the application folder, or paste it into a shortcut.

To rotate the key later, stop the server, edit `SECRET_KEY` in `factoryops.env` by hand, and start the server again. Existing sessions become invalid. There is no automatic rotation.

If the key is missing, still the placeholder, shorter than 50 characters, or `DEBUG=True`, production settings refuse to start and the error is written to `C:\FactoryOps\logs\server-console.log`.

### 5. Database initialization and migration

`Install-FactoryOps.ps1` and `Update-FactoryOps.ps1` run:

```powershell
..\venv\Scripts\python.exe manage.py migrate --noinput
```

`Start-FactoryOps.ps1` does not migrate. An ordinary restart or Windows reboot does not run migrations and does not delete or overwrite `db.sqlite3`.

### 6. Starting and stopping FactoryOps

Production server (Waitress, not `runserver`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Start-FactoryOps.ps1 -InstallRoot C:\FactoryOps
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Stop-FactoryOps.ps1 -InstallRoot C:\FactoryOps
```

If the health check at `http://127.0.0.1:8000/health/` already returns `{"status": "ok"}`, start does nothing. Stop ends the scheduled task and the recorded process tree. It does not delete the database.

Health JSON is only `ok` or `unavailable`. It does not include secrets, tracebacks, or operational records.

### 7. Automatic startup after a Windows restart

The server is a Task Scheduler job named `FactoryOps Server`:

- Trigger: at startup, as SYSTEM, including when nobody is logged on.
- If Waitress exits, Task Scheduler starts it again after one minute, up to 999 times.
- A second start is ignored while one is running.
- The task does not open a console window.

A daily `FactoryOps Backup` task runs at 02:00 as SYSTEM.

This is Task Scheduler rather than a Windows Service. A service wrapper such as NSSM would be another binary to install and another thing for the plant to debug. Task Scheduler is built in, shows the last run result, and can restart a failed process. The limitation is that a scheduled task is easier for a local administrator to disable than a service, and "run whether or not a user is logged on" does not provide a desktop for the browser. The browser is a separate logon task.

### 8. Opening the desktop interface

`FactoryOps Browser` runs at logon for `-DesktopUser` and calls `Open-FactoryOps.ps1`.

- It waits until `/health/` reports ok, up to 120 seconds.
- It then opens Edge in an application window at `http://127.0.0.1:8000/accounts/login/`.
- That is the existing login page. Authentication and role checks are unchanged.
- It does not pass a username or password.
- If the login window is already open, or the launcher is already running, it does not open another window.
- A supervisor can open `FactoryOps` from the desktop shortcut after closing the window. The shortcut does not require a code change.
- If the server never becomes healthy, a message points at `C:\FactoryOps\logs\factoryops.log`. The server process does not stop when the browser closes.

Automatic Windows sign-in is **not** enabled by these scripts. If the plant wants the login window after a reboot without anyone typing a Windows password, a local administrator can turn on Windows AutoLogon for the factory account. That stores a Windows password in the registry and lets anyone who can reach the keyboard use that Windows session. FactoryOps itself still shows its own login page. Prefer a normal Windows sign-in unless the floor cannot staff the PC.

### 9. LAN access from other devices

The server listens on `FACTORYOPS_BIND` (default `0.0.0.0`, TCP port 8000) so other devices on the factory network can connect. `0.0.0.0` means every network interface on this PC. It does not publish the PC to the internet. Do not forward port 8000 on the router.

Find the address on the factory PC:

```powershell
ipconfig
```

Use the IPv4 address of the plant Ethernet adapter. On another device on the same network, open `http://<that-address>:8000/accounts/login/`.

Users still sign in. Roles and factory scoping are unchanged.

When the address is known at install time, pass `-LanAddress`. Later:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Set-FactoryOpsLanAddress.ps1 -InstallRoot C:\FactoryOps -LanAddress '10.0.0.20'
```

That updates `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` and restarts the server. It does not change `SECRET_KEY`. `localhost`, `127.0.0.1`, and the computer name stay on the list. A wildcard host is rejected.

### 10. Firewall and network requirements

With `-ConfigureFirewall`, the installer adds a rule named `FactoryOps LAN` for inbound TCP 8000 on the Private and Domain profiles only. The Public profile is not opened.

```powershell
netsh advfirewall firewall show rule name="FactoryOps LAN"
```

Ask the network administrator for a DHCP reservation for this PC's MAC address so the LAN address stays stable. If DHCP gives the PC a new address, phones and tablets that bookmarked the old address will fail `ALLOWED_HOSTS` until you run `Set-FactoryOpsLanAddress.ps1` with the new address. Using the computer name in `ALLOWED_HOSTS` (the installer adds it) avoids that only when clients browse to the name rather than the raw IP.

Do not expose this HTTP server to the public internet. `FACTORYOPS_HTTPS=True` turns on HTTPS redirects and secure cookies, but this package does not obtain or install a certificate. Leave HTTPS off on an isolated LAN.

`check --deploy` may warn that HSTS and secure cookies are off. Those warnings are expected while the factory uses plain HTTP on the LAN. Do not silence them by setting `ALLOWED_HOSTS=*`.

### 11. Logs and troubleshooting

| File | What it is |
|---|---|
| `C:\FactoryOps\logs\factoryops.log` | Rotating application log (5 MB, five backups) |
| `C:\FactoryOps\logs\server-console.log` | Waitress console and settings errors |
| `C:\FactoryOps\logs\backup.log` | Backup and restore success or failure |

```powershell
Get-Content C:\FactoryOps\logs\factoryops.log -Tail 50
schtasks /Query /TN "FactoryOps Server" /V /FO LIST
```

| Symptom | What to do |
|---|---|
| Login window says FactoryOps did not become ready | Read `server-console.log`. Confirm the FactoryOps Server task is running. |
| `DisallowedHost` from a phone | Add that exact IP with `Set-FactoryOpsLanAddress.ps1`. |
| Production settings will not start | `DEBUG` is true, the secret is still the placeholder, or `ALLOWED_HOSTS` is empty or `*`. |
| Page on this PC works, phone does not | Private firewall rule, same subnet, no Wi-Fi client isolation. |
| Users see a login page, not a traceback | Expected. `DEBUG` is false. Details are in the log, not the browser. |

### 12. Database and media backups

The daily task runs `Backup-FactoryOps.ps1`, which runs:

```powershell
cd C:\FactoryOps\app
..\venv\Scripts\python.exe manage.py backup_factoryops
```

The copy uses SQLite's backup API, not a raw copy of `db.sqlite3` while Waitress may be writing. Media files are copied beside it. The environment file is stored only as `factoryops.env.redacted`, with secret-like values replaced by `REDACTED`. Keep the real `factoryops.env` on the PC and in a place only administrators can read. It is not put in the backup folder.

Each backup is a folder `C:\FactoryOps\backups\FactoryOps-<timestamp>\` with `manifest.json`. The backup is marked verified only after the SQLite integrity check and file hashes match. If verification fails, that attempt is removed and older verified backups are left alone. Retention defaults to 14 verified backups (`FACTORYOPS_BACKUP_RETENTION`). Unverified folders are not treated as restorable.

A manual backup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Backup-FactoryOps.ps1 -InstallRoot C:\FactoryOps
```

### 13. Restore testing

Test a restore without touching the live database:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Test-FactoryOpsRestore.ps1 -InstallRoot C:\FactoryOps -Backup 'C:\FactoryOps\backups\FactoryOps-<timestamp>'
```

That writes a temporary folder under `%TEMP%` and refuses to replace the live file. Inspect the temporary `db.sqlite3` if you need to, then delete the temp folder.

Replace live data only while the server is stopped, and only with the confirmation text:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Stop-FactoryOps.ps1 -InstallRoot C:\FactoryOps
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Restore-FactoryOps.ps1 -InstallRoot C:\FactoryOps -Backup 'C:\FactoryOps\backups\FactoryOps-<timestamp>' -Target 'C:\FactoryOps\data' -ReplaceLive -ConfirmReplace 'REPLACE LIVE DATA'
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Start-FactoryOps.ps1 -InstallRoot C:\FactoryOps
```

There is no separate PostgreSQL restore path because this deployment stays on SQLite.

### 14. Updating FactoryOps safely

On the factory PC, from an elevated PowerShell, with the new source available locally (a USB copy is enough; the update does not contact GitHub):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Update-FactoryOps.ps1 -InstallRoot C:\FactoryOps -Source 'D:\FactoryOps'
```

The script verifies a backup first and stops if that backup fails. It then stores the current code under `C:\FactoryOps\releases\`, copies the new code, installs dependencies, migrates, collects static files, and starts the server. It does not delete the database.

### 15. Rolling back an unsuccessful update

Code only (database stays as it is):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Rollback-FactoryOps.ps1 -InstallRoot C:\FactoryOps -Release 'C:\FactoryOps\releases\app-<timestamp>'
```

If the failed update also applied migrations, put back the pre-update database as well. Use the backup the update created, after you have tested it with `Test-FactoryOpsRestore.ps1`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Rollback-FactoryOps.ps1 -InstallRoot C:\FactoryOps -Release 'C:\FactoryOps\releases\app-<timestamp>' -RestoreDatabase -Backup 'C:\FactoryOps\backups\FactoryOps-<timestamp>' -ConfirmReplace 'REPLACE LIVE DATA'
```

### 16. Uninstalling without deleting production data

Stop and remove the scheduled tasks. Data, backups, logs, and `factoryops.env` stay:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Disable-FactoryOps.ps1 -InstallRoot C:\FactoryOps
```

Remove the virtual environment and program files, still keeping data:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\FactoryOps\app\deploy\windows\Uninstall-FactoryOps.ps1 -InstallRoot C:\FactoryOps -RemoveProgram -RemoveFirewall
```

Deleting the database, media, and backups requires `-DeleteData` and `-ConfirmDeleteData 'DELETE FACTORY DATA'`. Do not use that during a normal uninstall.

### Manual steps on the factory PC

These are not done by the repository tests:

1. Install Windows updates and Python 3.12+ on the factory PC.
2. Copy this project onto the PC (USB or internal share). Do not copy a developer `.env` or a developer `db.sqlite3`.
3. Run `Install-FactoryOps.ps1` from an elevated PowerShell with the LAN address, desktop user, and firewall switch.
4. Run `createsuperuser`, then assign factories and roles in Admin.
5. Confirm `http://127.0.0.1:8000/health/` returns `{"status": "ok"}`.
6. Sign in through the login window and open one operator page and one supervisor page.
7. From another device, open the LAN URL and sign in.
8. Run `Backup-FactoryOps.ps1`, then `Test-FactoryOpsRestore.ps1`, and confirm the live application still has its current records.
9. Reboot the PC and confirm the server is healthy before anyone signs in to Windows, then confirm the login window opens for the desktop user.
10. Ask the network administrator for a DHCP reservation. Do not forward port 8000 to the internet.

### Chosen server and startup approach

- Server: Waitress (`waitress==3.0.2`), bound from `FACTORYOPS_BIND` and `FACTORYOPS_PORT`.
- Static files: WhiteNoise after `collectstatic`.
- Uploaded files: the existing media directory, served only to signed-in users when `DEBUG` is false.
- Process manager: Task Scheduler, documented above.
- Database: existing SQLite configuration, file path overridable, engine unchanged.

## Troubleshooting FAQ

**`DisallowedHost` on a phone using the PC’s LAN IP**  
Add that IP to `ALLOWED_HOSTS` in `.env` and restart `runserver 0.0.0.0:8000`.

**`KeyError: 'SECRET_KEY'`**  
Create `.env` from `.env.example` and generate a key with `get_random_secret_key()`.

**Login works but dashboards look empty**  
Assign the user’s `factory`, and ensure master data + today’s events exist for that factory.

**Operator cannot use Admin**  
Admin needs staff/permissions. Prefer operator floor UI under `/operator/` for supported capture flows, or grant limited staff access for Admin-only models.

**`makemigrations --check` mentions accounts managers**  
Known pre-existing drift; leave it unless you are doing an accounts cleanup.

**Tests fail with missing env**  
Ensure `.env` exists in the project root before `python -m pytest` (settings load `SECRET_KEY` from the environment).
