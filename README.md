# Forest Detection System

A secure, incremental web system for detecting potential deforestation in the Copperbelt Province, Zambia using Sentinel-2 imagery and NDVI change detection.

## Development roadmap

1. **Foundation (done):** API structure, typed configuration, containerisation, health checks, and automated tests.
2. **Persistence (done):** PostgreSQL/PostGIS, Alembic migrations, and spatial data models (`ForestArea`, `AnalysisJob`, `Detection`, `User`, alerts).
3. **Real detection computation (done):** the Sentinel-2 processing chain — product extraction, NDVI, SCL-band cloud masking, and two-date persistence confirmation — is wired into the analysis job, so a detection's area and NDVI values are computed from pixels.
4. **Schema completion (done):** geometry column on `Detection` (UTM 35S), seasonal baseline/comparison windows on `AnalysisJob`, district/province jurisdiction on `User`, and a write-once audit log.
5. **Jurisdiction enforcement (done):** repository-layer filtering of detection queries by the officer's assigned district or province (FR-04), enforced server-side so an out-of-jurisdiction record cannot be returned by identifier.
6. **Dashboard (next):** OpenLayers map — NDVI baseline/comparison/difference layers, Esri World Imagery, detection and reserve polygons, optional low-opacity OSM roads — over a React or Jinja frontend.
7. **Alerts and review workflow:** alert rules, officer review and status changes, and an auditable alert lifecycle.
8. **Verification and deployment:** accuracy evaluation for the dissertation's results chapter, security review, end-to-end tests, backups, and production deployment.

Analysis jobs run asynchronously via a scheduled command (`PENDING → RUNNING → COMPLETED | FAILED`) — no Celery/Redis.

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

The test suite runs without a database or a network connection. It covers the
NDVI formula, the change-detection threshold, the 0.5 hectare minimum detectable
area, and jurisdiction-scoped access.

Copy `backend/.env.example` to `backend/.env` before running Docker. Keep `.env` private; it contains environment-specific configuration and future credentials.