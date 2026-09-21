# FactoryOps — Local Development & Setup Guide

v1 pilot documents: [README](../README.md) · [User guide](user-guide.md) · [Pilot playbook](pilot-playbook.md)


## System Requirements
- Python 3.12+ (local runtime has also been used with 3.14)
- SQLite3 (default local / pilot database)
- Git

Dashboards: http://127.0.0.1:8000 (role home), http://127.0.0.1:8000/admin (capture).

After `createsuperuser`, give the user `role=ADMIN` (createsuperuser already defaults to ADMIN) and assign a factory in Admin so dashboards scope correctly.

## Initial Environment Setup

### 1. Clone & Environment Configuration
```bash
git clone <repository-url>
cd FactoryOps
```

Copy the template environment file:
```bash
cp .env.example .env
```
*(On Windows PowerShell: `Copy-Item .env.example .env`)*

### 2. Activate Virtual Environment
```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Database Migrations
```bash
python manage.py migrate
```

### 5. Create Administrator Account
```bash
python manage.py createsuperuser
```

### 6. Run System Check & Test Suite
```bash
python manage.py check
pytest
```

### 7. Launch Development Server
```bash
python manage.py runserver
```
Navigate to `http://127.0.0.1:8000` for the Operational Dashboard and `http://127.0.0.1:8000/admin` for Django Admin.
