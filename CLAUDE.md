# Forest Detection System — Project Context

Final-year BSc Information Technology dissertation, Zambia University College of Technology.
Author: Samuel Bikiloni (2300096). Supervisor: Mr. Chilanga.

**Title:** Automated Web-Based Deforestation Detection and Alert System Using
Sentinel-2 Imagery for the Copperbelt Province, Zambia

Detects potential deforestation in the Copperbelt Province from Sentinel-2 imagery
using NDVI change detection, and alerts Forestry Department officers.

## Who uses this system

Authorised officers of the Zambian Forestry Department **only**. Not public-facing.

The access restriction is a deliberate security control, not a convenience:
publishing precise locations of suspected illegal clearing would inform the people
responsible. State this reasoning if the design is ever questioned.

Three roles: `ADMIN`, `PROVINCIAL_FORESTRY_OFFICER`, `DISTRICT_FORESTRY_OFFICER`.
The admin provisions accounts and configures thresholds but has **no operational
alert duties** — separation of duties keeps the audit trail independent.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- PostgreSQL 16 + PostGIS, GeoAlchemy2
- Copernicus Data Space Ecosystem for Sentinel-2 (NOT Google Earth Engine — see below)
- rasterio / shapely / pyproj / geopandas / rasterstats for raster work
- Docker Compose for local dev
- Frontend: undecided between React (scaffolded in `frontend/`) and server-rendered
  Jinja templates. Jinja is faster for a solo developer under deadline.
- Mapping: OpenLayers (NOT Leaflet — needs native reprojection, WMS/WMTS, layer clipping)

## Architecture

Strict layering, already established. Respect it:

```
app/api/          FastAPI routers — HTTP only, no business logic
app/services/     business logic — testable without a web server
app/repositories/ data access — all queries live here
app/models/       SQLAlchemy ORM
app/schemas/      Pydantic request/response
app/core/         config, security
```

Detection logic must stay runnable without FastAPI, a database, or a network call.
This is what makes the accuracy evaluation possible as an isolated exercise.

## Critical open issues

### 1. Detection returns hardcoded values — HIGHEST PRIORITY

`app/services/detection_service.py` around line 282 contains:

```python
vegetation_loss_area = 3.85
ndvi_before = 0.81
ndvi_after = 0.42
```

and `app/services/analysis_service.py` around line 284 has `cloud_cover=5.4`.

The pipeline runs end-to-end but computes nothing from imagery. Replacing these with
real rasterio computation is the single most important task in the project.
Do not build new features until `DetectionService` returns a number derived from pixels.

### 2. `Detection` has no geometry column

Only `ForestArea` has geometry. Without geometry on `Detection` you cannot map a
detection, check whether it falls inside a reserve, or enforce jurisdiction spatially.

Add: `Geometry("MULTIPOLYGON", srid=32735)` — UTM 35S covers the Copperbelt and
gives areas in square metres directly.

### 3. `AnalysisJob` compares single images, not seasonal windows

Currently has one `satellite_image_id`. Needs `baseline_start`, `baseline_end`,
`comparison_start`, `comparison_end`.

**Why this matters:** miombo vegetation in the Copperbelt has a severe wet/dry cycle.
NDVI falls across the entire province every dry season. Comparing adjacent months
produces false deforestation everywhere. Always compare *equivalent seasonal windows
in different years* (e.g. May–July 2024 vs May–July 2025).

This is the main methodological defence in the dissertation. Do not weaken it.

### 4. No jurisdiction on `User`

`Province` and `District` models exist but nothing links a user to one. Requirement
FR-04 (jurisdiction-scoped access) has nothing to enforce against.

Add `district_id` / `province_id` to `User`, then a FastAPI dependency that filters
every query. **Enforce on the server, in the repository layer.** A UI that hides data
is not access control; a query that cannot return it is.

### 5. No audit log

FR-19 requires logging every login, analysis execution and alert status change with
user and timestamp. `AuditMixin` gives row timestamps only, not an action trail.
Audit records are write-once — no update method.

### 6. No cloud masking or compositing

Nothing in `app/services/` masks cloud. Use the Sentinel-2 SCL band, then build a
median composite across each seasonal window. This also handles cloud gaps for free.

## Things to remove

- Hardcoded stub values (see above)
- `RESEARCHER` from `UserRole` — the dissertation excludes researchers as users
- `DAILY` and `EVERY_2_DAYS` from `MonitoringFrequency` — Sentinel-2 revisits every
  ~5 days; offering daily monitoring promises what the data cannot deliver
- `NATIONAL_PARK`, `GAME_MANAGEMENT_AREA` from `ProtectedStatus` — outside scope
- "Google Earth Engine" from the README roadmap — contradicts `copernicus_service.py`

## Known fixes needed

- `backend/requirements.txt` is saved as UTF-16 — re-save as UTF-8
- `docker-compose.yml` has no `db` service but `DATABASE_URL` points at `db:5432` —
  add `postgis/postgis:16-3.4`

## Why Copernicus, not Google Earth Engine

Deliberate choice. Earth Engine is free for academic use but **government operational
use requires a paid commercial licence** — and this system is built for a government
department. Copernicus removes that barrier.

Cost of the choice: cloud masking and compositing must be implemented locally with
rasterio, tiles are ~1GB each, and the "low-resource environment" claim is weaker
because processing is local rather than on Google's servers.

If asked in the viva, present it as a licensing-driven decision with a known trade-off.

## Detection rules

- **Minimum detectable area: 0.5 hectares** = 50 Sentinel-2 pixels at 10 m.
  Aligns with the statutory definition of a forest in Zambian law, and suppresses
  isolated noise pixels. Put this in `config.py`, never as a literal.
- NDVI threshold is configurable per analysis job (`AnalysisJob.ndvi_threshold`).
- Store `ndvi_before`, `ndvi_after`, `ndvi_delta` on every detection — not just the
  conclusion. Lets detections be re-evaluated when a threshold changes, without
  reprocessing imagery.
- A job completing with **zero detections is a valid outcome**, not a failure.
  Distinguish it from `FAILED` — the officer's response differs (wait for clearer
  imagery vs investigate a fault).
- Failed jobs are never revived. Resubmission creates a new job so the failure
  stays in the audit record.

## Analysis is asynchronous

A cloud-free seasonal composite over a district takes minutes. Officer submits →
immediate acknowledgement → background processing → notification on completion.

Job states: `PENDING → RUNNING → COMPLETED | FAILED`.

Do **not** introduce Celery + Redis. Use a scheduled command that picks up queued
jobs. Three processes to deploy on free hosting is not worth it. Celery is listed
as future work in Chapter Six.

## Map layers

The map must show **vegetation**, not streets. A road map is the wrong base layer.

- Base: Sentinel-2 true colour (baseline period / comparison period), Esri World Imagery
- Analysis overlays: NDVI baseline, NDVI comparison, **NDVI difference** (red where
  vegetation declined) — the difference layer is the important one
- Vectors: detection polygons, forest reserve boundaries, jurisdiction boundary
- Roads: OSM as an **optional low-opacity overlay, off by default** — useful only for
  judging whether a detection is reachable when planning a field visit

Worth building: a draggable swipe divider comparing baseline and comparison imagery.
~30 lines in OpenLayers, and it makes a detection self-evidently right or wrong.

## Testing

Required minimum, all runnable without network or database:

- NDVI returns correct value for hand-calculated red/NIR inputs
- NDVI returns 0.0 when red == NIR
- Change detection flags an array whose decline exceeds threshold
- Change detection does not flag one below threshold
- Patches under 0.5 ha are suppressed
- Jurisdictional filtering excludes an out-of-boundary detection

Test FR-04 by authenticating as a Kitwe officer and requesting a Ndola detection by
direct URL. Screenshot the rejection — it is evidence for Chapter Four.

## Conventions

- Never commit `.env` or Copernicus credentials
- Meaningful commit messages — the history is evidence of authorship
- Explain the approach before writing code; the author must be able to defend every
  line in a viva
- Do not paste large code blocks into the dissertation — appendix only

## Build order

1. Real detection computation (replace stubs) ← **currently here**
2. Schema: detection geometry, seasonal windows, user jurisdiction, audit log
3. Cloud masking + compositing + 0.5 ha filter + unit tests
4. Jurisdiction enforcement
5. Frontend
6. Alerts and review workflow
7. Accuracy evaluation for Chapter Five
