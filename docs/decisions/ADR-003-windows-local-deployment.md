# ADR-003: Windows factory-PC deployment

* **Status**: Accepted
* **Date**: 2026-10-09
* **Context**: FactoryOps is a Django modular monolith aimed at one factory. The pilot already runs on SQLite with environment-based `SECRET_KEY` and `ALLOWED_HOSTS`. The factory PC must start the application at boot, open the existing login page for a desktop user, accept LAN clients, and back up the database without a resident IT team. The development server is not a production server. PostgreSQL is allowed by the settings comments but is not configured, and changing the engine would be a migration and operations project of its own.

## Decision

Keep SQLite. Point the production file at `FACTORYOPS_SQLITE_PATH` (default under `C:\FactoryOps\data`) so code updates do not sit on top of the database file.

Serve the application with Waitress and WhiteNoise. Both are pinned in `requirements.txt` and run without IIS, Nginx, or a C compiler.

Start Waitress from Task Scheduler as SYSTEM at boot, with restart-on-failure. Open the existing `/accounts/login/` page from a separate logon task for a named Windows user. Do not store FactoryOps credentials in the task, the shortcut, or the browser arguments.

Do not enable Windows automatic sign-in in the scripts. Document it as an optional local trade-off.

Back up with `sqlite3.Connection.backup`, copy media, redact secrets out of the copied environment file, and verify integrity and hashes before pruning older verified backups.

Run migrations from the install and update scripts only. The start script must not migrate and must not delete an existing database.

Bind `0.0.0.0` only so other devices on the factory LAN can connect, and add a Windows firewall rule for the Private and Domain profiles. Do not document port-forwarding to the internet.

## Consequences

* `manage.py` still defaults to development settings. Production is selected by the Windows scripts.
* `check --deploy` will warn about HSTS and secure cookies while the LAN uses HTTP. That is accepted and recorded in the README. It is not a reason to set `ALLOWED_HOSTS=*`.
* Task Scheduler can be disabled by a local administrator more easily than a Windows Service. A service wrapper was rejected because it adds a binary and a failure mode the plant cannot inspect as easily.
* A crash loop from a bad environment file will retry every minute until an administrator fixes `factoryops.env`. The error is in `logs\server-console.log`.
* This decision does not claim the software was installed on the factory PC. Installation remains a manual supervised trial.
