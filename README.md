# Forest Detection System

A secure, incremental web system for detecting potential deforestation in the Copperbelt Province, Zambia using Sentinel-2 imagery and NDVI change detection.

## Development roadmap

1. **Foundation (current):** API structure, typed configuration, containerisation, health checks, and automated tests.
2. **Persistence:** PostgreSQL/PostGIS, Alembic migrations, and spatial data models.
3. **Detection:** Google Earth Engine integration, Sentinel-2 cloud masking, NDVI, and change detection.
4. **Dashboard:** React map interface, area-of-interest selection, and result views.
5. **Alerts and access:** authenticated users, alert rules, audit logging, and reports.
6. **Verification and deployment:** security review, end-to-end tests, backups, and production deployment.

## Run the foundation

Install Python 3.12 or later, then from `backend`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

The health endpoint is available at `http://localhost:8000/api/v1/health`.

Copy `backend/.env.example` to `backend/.env` before running Docker. Keep `.env` private; it contains environment-specific configuration and future credentials.