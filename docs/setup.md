# FactoryOps — Local Development & Setup Guide

Development setup only. A factory PC must use the Windows production guide in the [README](../README.md#factory-pc-deployment-windows), not `runserver`.

Companion docs: [README](../README.md) · [User guide](user-guide.md) · [Pilot playbook](pilot-playbook.md) · [Architecture](architecture.md)

This guide must stay consistent with the README environment rules: env-driven `SECRET_KEY` / `ALLOWED_HOSTS`, no hardcoded LAN IPs, no `ALLOWED_HOSTS=*`.

## System Requirements

- Python 3.12+ (local runtime has also been used with newer 3.x)
- SQLite3 (default local / pilot database)
- Git

After install:

- Role home: http://127.0.0.1:8000  
- Admin: http://127.0.0.1:8000/admin  

After `createsuperuser`, the user defaults to `role=ADMIN`. Assign a factory in Admin so dashboards scope correctly.

## Initial Environment Setup

### 1. Clone

```powershell
git clone https://github.com/lesleysacks/FactoryOps.git
cd FactoryOps
```

### 2. Virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux / macOS: `python3 -m venv .venv` then `source .venv/bin/activate`.

### 3. Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Environment file

```powershell
Copy-Item .env.example .env
```

Linux / macOS: `cp .env.example .env`.

Generate a secret key:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Edit `.env` (project root, next to `manage.py`):

```env
SECRET_KEY=<paste-generated-value>
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

For LAN / factory-PC access, append this machine’s IPv4 (no port, no quotes, no brackets):

```env
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.105
```

Discover the IP with `ipconfig` (Windows), `ip addr` (Linux), or `ifconfig` (macOS). Restart the server after any `.env` change.

Never commit `.env`. Do not set `ALLOWED_HOSTS=*`.

### 5. Database

```powershell
python manage.py migrate
python manage.py createsuperuser
```

### 6. System check & tests

```powershell
python manage.py check
python manage.py makemigrations --check
python -m pytest
```

Note: `makemigrations --check` may fail only on pre-existing `accounts` user-manager drift. Leave that alone unless an accounts cleanup is scheduled (see [system-health.md](system-health.md)).

### 7. Run locally

```powershell
python manage.py runserver
```

### 8. LAN / factory-PC testing

```powershell
python manage.py runserver 0.0.0.0:8000
```

Open `http://<lan-ip>:8000` from another device on the same network. If you see `DisallowedHost`, the LAN IP is missing from `ALLOWED_HOSTS` in `.env`.

## Configuration rules (summary)

1. `SECRET_KEY` from environment only  
2. `ALLOWED_HOSTS` from comma-separated environment value only  
3. No LAN IP literals in Python settings  
4. No `ALLOWED_HOSTS=*`  
5. `.env` gitignored; `.env.example` is the safe template  

More detail: [README — Environment Configuration](../README.md#environment-configuration).
