# FactoryOps on a Windows 11 factory PC

This is the deployment guide for one dedicated Windows 11 PC that hosts FactoryOps for the factory. The PC runs the existing Django application. It is not a rewrite, and it is not an internet service.

The application stays a Django project on SQLite. Waitress serves it. WhiteNoise serves static files. Uploaded QC photos stay on disk and are only returned to a signed-in user at the right factory. Windows Task Scheduler starts the server at boot. A separate display account can open the login page in full-screen Edge.

## What was verified in this repository

Automated checks on the development machine cover production configuration, the health check, media permissions, a Waitress boot, and a SQLite backup restored into a separate folder.

These items need the physical factory PC and network. They were not executed from this change:

- Windows Task Scheduler across a reboot
- The Edge full-screen window
- The Windows Firewall rule
- A phone on factory Wi-Fi
- A power cut and UPS shutdown

Do not treat those as done until the checklist at the end of this guide has been walked on that PC.

## Layout

Use paths outside any user profile so the SYSTEM startup task can read them:

```text
C:\FactoryOps\app\        the git checkout (manage.py lives here)
C:\FactoryOps\app\.env    secrets; never commit this file
C:\FactoryOps\app\db.sqlite3
C:\FactoryOps\app\media\  QC photos and other uploads
C:\FactoryOps\logs\
C:\FactoryOps\backups\    timestamped backup folders
C:\ProgramData\FactoryOps\factoryops.config.json
```

`factoryops.config.json` stores paths, the port, and the login URL. It does not store `SECRET_KEY` or any password.

## One-time install

Install Python 3.12 or newer and Git. Put the checkout in `C:\FactoryOps\app`. Open **Windows PowerShell as administrator**:

```powershell
Set-Location C:\FactoryOps\app
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\windows\Install-FactoryOps.ps1 -ProjectRoot C:\FactoryOps\app
```

The first run copies `.env.production.example` to `.env` and stops. Generate a secret and edit `.env`:

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Paste that value into `SECRET_KEY`. Set:

```env
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

Add the PC's LAN address only after you know it (see phones below). Then run the installer again. A second run is safe: it keeps the existing `.env`, applies migrations, and refreshes the scheduled tasks. It does not flush or replace production data.

The installer registers:

| Task | When | Account |
|---|---|---|
| `FactoryOpsServer` | At startup | SYSTEM |
| `FactoryOpsBackup` | Daily at 02:00 | SYSTEM |

`FactoryOpsServer` runs `Start-FactoryOps.ps1 -Service`, which runs `scripts\serve_production.py` in the foreground. If that process exits, Task Scheduler starts it again after one minute (up to 999 times) and ignores an overlapping start. The task also starts after an ordinary reboot, including when nobody is signed in.

Confirm the configuration without staying up:

```powershell
$env:DJANGO_SETTINGS_MODULE = 'config.settings.production'
.\.venv\Scripts\python.exe scripts\serve_production.py --check
```

`production configuration ok` means the secret, hosts, and CSRF origins are acceptable. `DEBUG` in `.env` cannot turn debug back on under this settings module.

## Start, stop, status, restart, uninstall

Run these from an elevated PowerShell if a script says it needs one. Status and the server start request can be run after install by an administrator:

```powershell
.\deploy\windows\Start-FactoryOps.ps1
.\deploy\windows\Get-FactoryOpsStatus.ps1
.\deploy\windows\Restart-FactoryOps.ps1
.\deploy\windows\Stop-FactoryOps.ps1
.\deploy\windows\Uninstall-FactoryOps.ps1
```

Uninstall asks for confirmation. It removes the scheduled tasks, the firewall rule, and the display-account shortcut. It leaves the database, `media\`, logs, backups, `.env`, and the ProgramData config in place.

Logs:

- `C:\FactoryOps\logs\operations.log` — start, stop, backup, kiosk
- `C:\FactoryOps\logs\server.log` — Waitress stdout and stderr
- `C:\FactoryOps\logs\factoryops.log` — Django request and security warnings

If port 8000 is already taken by something that is not `serve_production.py`, the start script exits with an error and does not kill that process.

`python manage.py runserver` remains the local development command. It is not the factory service.

## Full-screen display

The server does not need a signed-in person. The full-screen page does, because this install does not turn on automatic Windows sign-in and does not store a password.

1. In Windows Settings, create a local **standard** user such as `FactoryDisplay`. Do not put that account in Administrators.
2. Sign in as `FactoryDisplay` once, then sign out, so Windows creates the profile.
3. From an elevated PowerShell:

```powershell
.\deploy\windows\Register-FactoryOpsKiosk.ps1 -DisplayUser FactoryDisplay
```

You can pass `-DisplayUser` to `Install-FactoryOps.ps1` instead. The script writes a Startup-folder shortcut only for that user. The shortcut runs `Start-FactoryOpsKiosk.ps1`, which waits up to 60 seconds for `http://127.0.0.1:8000/health/` and then opens Microsoft Edge at the login URL:

```text
http://127.0.0.1:8000/accounts/login/
```

Change the URL in `.env` (`FACTORYOPS_KIOSK_URL`) and re-run the installer, or edit `kioskUrl` in `C:\ProgramData\FactoryOps\factoryops.config.json`. The path must stay `/accounts/login/`. The launcher rejects a URL that contains `password=`.

After the next sign-in of `FactoryDisplay`, Edge opens the FactoryOps login page full screen. Closing Edge does not stop Waitress. Phones can still reach the server.

To leave kiosk mode for maintenance, an authorised person can:

- Press Ctrl+Alt+Del and sign out of `FactoryDisplay`, or
- Press Ctrl+Alt+Del, open Task Manager, and end Microsoft Edge

Do not disable Task Manager, Windows Update, or recovery options. This repository does not script those changes. If the site wants a single-app Windows session, an administrator can configure Assigned Access in Settings by hand and point it at the same login URL. Do not use that session to sign FactoryOps in as an administrator.

## Phones on factory Wi-Fi

Keep the application off the public internet. Do not add a port-forward on the router.

1. On the factory PC:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
  Select-Object IPAddress, InterfaceAlias
Get-NetAdapter | Select-Object Name, MacAddress, Status
```

2. In the router or DHCP server, reserve that MAC address so the PC keeps the same IPv4 address. A reservation on the factory LAN is the stable address. A public DNS name is not required.

3. Edit `.env` on the PC. Host names do not include a port. CSRF origins include the scheme and port:

```env
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000,http://192.168.1.50:8000
```

Use the address you reserved. Restart the server after saving `.env`:

```powershell
.\deploy\windows\Restart-FactoryOps.ps1
```

4. Allow the port from the private network only, still from an elevated PowerShell:

```powershell
.\deploy\windows\Install-FactoryOpsFirewall.ps1 -Port 8000 -RemoteAddress LocalSubnet
```

The rule is named `FactoryOps LAN`. It is inbound TCP, Private profile, remote address `LocalSubnet`. The script refuses `Any`, `*`, and `0.0.0.0/0`. Set the PC's network profile to Private. A Public profile will not match this rule; do not open the Public profile to make phones work.

5. On a phone joined to the factory Wi-Fi, open:

```text
http://192.168.1.50:8000/accounts/login/
```

Health, from the PC or a phone:

```text
http://192.168.1.50:8000/health/
```

A healthy body is `{"status": "ok"}`. It does not include paths, secrets, or exception text. `{"status": "unavailable"}` with HTTP 503 means the process is up and the database check failed.

### If a phone cannot connect

| What you see | What to check |
|---|---|
| Phone loads other internet sites but not the PC | Guest Wi-Fi or client isolation is on. Phones must be on a factory SSID that can reach other devices. Do not solve this by publishing the PC to the internet. |
| Browser says it cannot connect | Firewall profile is Public, the rule was not installed, or the PC address changed. Run `Get-FactoryOpsStatus.ps1` on the PC, then `Get-NetIPAddress`. |
| Django "Invalid HTTP_HOST" or a 400 | The phone's host is missing from `ALLOWED_HOSTS`. Add the exact address and restart. |
| Login page loads, form returns 403 | The phone origin is missing from `CSRF_TRUSTED_ORIGINS`, including `http://` and the port. |
| Worked yesterday, fails today | DHCP gave the PC a new address. Reserve the MAC, update `.env`, restart. |
| `/health/` is not `ok` | Read `C:\FactoryOps\logs\server.log` and `factoryops.log`. |

### HTTP on the factory LAN

Anyone who can see traffic on that Wi-Fi can read passwords and session cookies sent over plain HTTP. Treat the factory SSID as a closed network: a strong Wi-Fi passphrase, no guest sharing of the same SSID, and no router port-forward.

When credentials must not travel in clear text, put a TLS reverse proxy on the same PC (Caddy or IIS) and give phones an `https://` URL. Then set `FACTORYOPS_USE_HTTPS=true` and change every CSRF origin to `https://`. Production settings will mark the session and CSRF cookies Secure. Leave `SECURE_SSL_REDIRECT` unset until that proxy is actually listening, or browsers will fail before TLS exists. This repository does not create a certificate authority.

## Backups and restore

The daily task runs `scripts\backup_factoryops.py`. That uses SQLite's backup API on a read-only connection, then `PRAGMA integrity_check`. It does not copy the live database file with the file copier while writes may be in progress. Each run creates a new folder and does not overwrite an existing one:

```text
C:\FactoryOps\backups\20261010T020000Z\db.sqlite3
C:\FactoryOps\backups\20261010T020000Z\media\
C:\FactoryOps\backups\20261010T020000Z\manifest.json
```

`manifest.json` records the creation time, the SQLite engine, every included file, its size, and its SHA-256 checksum. `.env` is not copied. If `media` has no files, the backup says so and still saves the database.

Folders older than `FACTORYOPS_BACKUP_RETENTION_DAYS` (default 14, also `retentionDays` in the ProgramData config) are removed. The live database and live `media` folder are not deleted. A failed backup prints `BACKUP FAILED` and writes an error line to `operations.log`. The scheduled task exits non-zero so Task Scheduler shows the failure.

Run a backup by hand:

```powershell
.\deploy\windows\Backup-FactoryOps.ps1
```

From the project virtual environment, the same tool reads the database path from Django settings:

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py backup_factoryops --destination C:\FactoryOps\backups
python manage.py verify_restore --backup C:\FactoryOps\backups\20261010T020000Z --destination C:\FactoryOps\restore-test
```

`verify_restore` checks checksums, SQLite integrity, migrations, and Django checks on that disposable copy. It refuses the live database path. Omit `--destination` to use a temporary directory that is deleted after the checks.

A file copy into a new empty folder, still without touching the live database, asks for confirmation:

```powershell
.\deploy\windows\Restore-FactoryOps.ps1 `
  -Backup C:\FactoryOps\backups\20261010T020000Z `
  -Destination C:\FactoryOps\restore-test
```

Stop the server before you ever copy a restored database over the live one. Keep the previous backup and the files you moved aside. The restore script will not do that replacement for you. See the README section "Backup and recovery" for the manual steps.

Put a second copy of `C:\FactoryOps\backups` on removable media that does not stay attached to the PC. A backup on the same disk is not a recovery plan for a dead drive.

Use a UPS that can run the PC through a short outage and can ask Windows to shut down cleanly. After an unplanned power loss, Task Scheduler starts `FactoryOpsServer` at boot. SQLite's WAL mode (set when the production process opens the database) keeps committed transactions. Sign in to `FactoryDisplay` when you want the full-screen login again. Confirm `/health/` before operators record production.

## Acceptance checklist

| # | Check | Where it is proven |
|---|---|---|
| 1 | Clean install on Windows 11 | Manual on the factory PC. The installer is idempotent and refuses a placeholder secret. |
| 2 | Production server starts | Automated: `serve_production.py --check` and a Waitress `/health/` plus login page. Windows service start is manual. |
| 3 | Server returns after reboot | Manual. The task is At startup, SYSTEM, StartWhenAvailable. |
| 4 | Full-screen login after the display session starts | Manual. Shortcut opens `/accounts/login/` only. Automatic Windows sign-in is not configured. |
| 5 | Server stays up when the browser closes | By design the browser is a different process. Confirm on the PC by ending Edge and reloading `/health/`. |
| 6 | Phone on factory Wi-Fi | Manual after the firewall rule, DHCP reservation, and `.env` hosts. |
| 7 | Login and role permissions | Existing automated permission tests. Sign in once on the PC with each role before go-live. |
| 8 | Production, inventory, QC, handover, downtime, and reports | Existing automated suite. Handover, downtime, and reports apps are still the existing modules; this work does not replace them. |
| 9 | Data and photos survive a restart | SQLite and `media` are files on disk, not memory. Confirm a QC photo is still present after `Restart-FactoryOps.ps1`. |
| 10 | Database and media backup | Automated round-trip of the backup API. The 02:00 task still has to be seen once in Task Scheduler on the PC. |
| 11 | Restore to a separate folder | Automated, including the refusal to overwrite the live database. |
| 12 | Bad hosts, missing secret, unauthorised media | Automated. Placeholder secret and `ALLOWED_HOSTS=*` refuse to boot. Unknown Host gets HTTP 400. Anonymous media requests redirect to login. |

## Known limits

- Django stays on SQLite. There is no PostgreSQL migration in this work.
- `manage.py makemigrations --check` can still report the existing accounts user-manager drift. Leave that migration history as it is.
- The PC must not be exposed through router port-forwarding.
- HTTP on the LAN is readable to anyone on that network until a TLS proxy is added.
- The display account is not signed in automatically.
- Waitress is bound to all interfaces (`0.0.0.0`) so phones can connect. The firewall rule is what limits that to the private subnet. Install the rule before joining the PC to factory Wi-Fi.
