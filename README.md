# Phone Scrapper

Continuous **US business phone number collection agent**. It pulls publicly listed numbers from official place APIs, normalizes them to E.164, deduplicates with full provenance, respects free-tier quotas, optionally enriches records, and exposes an operator UI (**Phone Desk**) plus Django admin.

**Phases 1–9 are complete.** Prefer APIs over crawling; website crawl is permission-gated only.

Repository: [github.com/izoo2003/Phone-Scrapper](https://github.com/izoo2003/Phone-Scrapper)

---

## What it does

1. **Acquire** business phones from place/search APIs (city + category queries).
2. **Normalize & validate** to US E.164; map area code → state; reject invalids.
3. **Store uniquely** with business context, source, raw payload, first/last seen.
4. **Track quotas** per source (daily/monthly/soft) with safety buffers so free tiers are not overspent.
5. **Enrich** (optional) with offline line-type hints and DialCode when quota allows.
6. **Orchestrate** scheduled cycles and an operator Start/Stop loop.
7. **Operate** via Phone Desk (Next.js) or Django admin.

---

## Stack

| Layer | Technology |
|--------|------------|
| Backend | Django 5, Django REST Framework |
| Database | PostgreSQL 16 (Docker) or Supabase Postgres |
| Jobs | Celery + Redis (worker + Beat) |
| Operator UI | Next.js 15 / React 19 (**Phone Desk**) |
| HTTP / phones | httpx (retries), phonenumbers |
| Secrets | Env vars + Fernet-encrypted keys from the UI |

---

## Architecture

| Django app | Responsibility |
|------------|----------------|
| `config` | Settings, URLs, Celery, ops dashboard |
| `sources` | Source registry, quota preflight/updates, encrypted API keys |
| `phones` | Phone records, normalization, area codes, enrichment |
| `acquisition` | API clients, ingest, scheduler, scraper control, authorized crawl |
| `api` | Staff session API for Phone Desk |
| `frontend/` | Operator UI (Scraper, Numbers, Usage, Keys) |

**Flow:** Scheduler / Scraper Start → eligible sources (quota + priority) → fetch → extract → normalize → unique store → enrichment → quota/metrics update.

---

## Data sources

| Source | Slug | Role | Default active |
|--------|------|------|----------------|
| OpenStreetMap / Overpass | `openstreetmap` | Free volume (soft politeness limits) | Yes |
| Geoapify | `geoapify` | Places search (daily free style) | Yes |
| LocationIQ | `locationiq` | Places search | Yes |
| TomTom | `tomtom` | Places search (`MYTOMTOM_API_KEY`) | Yes |
| Foursquare | `foursquare` | Places (monthly free style) | Yes |
| Yelp Fusion | `yelp` | High quality (optional) | No |
| Google Places | `google-places` | High completeness (SKU-aware) | No |
| DialCode | `dialcode` | Enrichment only (not acquisition) | Yes |
| Authorized website | (manual) | Crawl only if `authorized=true` | Not seeded |

Clients live under `acquisition/` (`overpass`, `geoapify`, `locationiq`, `tomtom`, `foursquare`, `yelp`, `google_places`, `authorized_crawl`).

---

## Features

### Source registry & quotas
- Central `DataSource` records: priority, active flag, window type, remaining calls, reset time, status (Healthy / Low / Exhausted / Error).
- Pre-flight checks before every job; counters updated after each response; safety buffer left unused.
- Commercial APIs preferred while free room remains; OSM for volume when commercial tiers are low.

### Phone storage
- Unique E.164 key; national format; business name, address, city, state, category.
- Provenance (source, query context), raw payload, validation and enrichment fields.
- Re-see updates last-seen and context — no duplicate rows.

### Normalization & validation
- Strip noise/extensions → US parse → E.164 → length/area-code checks → area code → state.
- Invalid candidates never enter the main table.

### Enrichment
- Background / CLI batches: offline formatting & line-type hints; DialCode when quota allows.
- Celery Beat runs enrichment hourly.

### Orchestration & scraper control
- Acquisition cycles every 30 minutes (Beat); operator **Start** enables the continuous loop.
- Cities/categories configurable (`ORCHESTRATION_*` env or Phone Desk).
- `HarvestRun`, cursors, and `AcquisitionDecision` audit every cycle.
- Source ERROR cooldown (`SOURCE_ERROR_COOLDOWN_MINUTES`).

### Operator UI — Phone Desk (`http://127.0.0.1:3000`)
| Page | Purpose |
|------|---------|
| **Scraper** | Start / Stop collection, orchestration cities & categories, session stats, worker health banner |
| **Numbers** | Search, filters, detail, CSV download |
| **Usage** | Remaining free-tier room and alerts |
| **Keys** | Paste/rotate API keys (stored encrypted; used immediately) |

Sign in with the same **staff** user as Django admin.

### Django admin (`http://127.0.0.1:8000/admin/`)
- Data sources, phone records, harvest runs, decisions, cursors, orchestration state.
- Ops dashboard: quotas, harvest stats, alerts.

### Hardening (Phase 9)
- Shared HTTP retries (`HTTP_MAX_RETRIES`), timeouts, ERROR cooldown.
- Secret-safe logging (URL/key redaction; httpx not dumping secrets).
- Authorized crawl: HTTPS + SSRF guards; refuses non-authorized sources.

---

## Quick start

### 1. Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Fill SECRET_KEY (required), Postgres, OVERPASS_USER_AGENT, and API keys as available
# Local admin: set DEBUG=True in your private .env only
docker compose up -d
python manage.py migrate
python manage.py seed_sources
python manage.py createsuperuser
```

### 2. Operator stack (recommended)

```powershell
powershell -File .\scripts\start-operator.ps1
```

Starts Django (`:8000`), Celery worker (`--pool=solo`), Beat, and Next.js (`:3000`).

Open **http://127.0.0.1:3000** and sign in with your staff user.

### 3. Manual processes (if not using the script)

```powershell
docker compose up -d
python manage.py runserver
celery -A config worker -l info --pool=solo -n worker1@%h
celery -A config beat -l info
cd frontend; npm install; npm run dev
```

Linux Compose workers (optional): `docker compose --profile workers up -d`

Production: use a real WSGI server — do **not** use `runserver`. See [docs/production-runbook.md](docs/production-runbook.md).

---

## Management commands

| Command | Purpose |
|---------|---------|
| `seed_sources` | Upsert default API sources in the registry |
| `seed_demo_phones` | Demo phone rows for schema checks |
| `revalidate_phones` | Re-run normalization on stored rows |
| `enrich_phones --limit N` | Manual enrichment batch |
| `run_acquisition_cycle [--dry-run] [--limit N]` | One orchestration cycle |
| `fetch_overpass --city Austin --category restaurant --limit 25` | OSM pull |
| `fetch_geoapify` / `fetch_locationiq` / `fetch_tomtom` | Places pulls |
| `fetch_foursquare` / `fetch_yelp` / `fetch_google` | Additional APIs |
| `crawl_authorized --slug SLUG` | Crawl only if source is authorized |

Examples:

```powershell
python manage.py run_acquisition_cycle --dry-run
python manage.py fetch_overpass --city Austin --category restaurant --limit 25
python manage.py enrich_phones --limit 5
```

---

## Staff API (Phone Desk)

Base: `http://127.0.0.1:8000/api/` — Django session + CSRF; **staff only**.

| Area | Endpoints |
|------|-----------|
| Auth | `GET /api/auth/csrf/`, `POST /api/auth/login/`, `POST /api/auth/logout/`, `GET /api/auth/me/` |
| Scraper | `GET /api/scraper/status/`, `POST .../start/`, `POST .../stop/`, `PUT .../orchestration/` |
| Phones | `GET /api/phones/`, `GET /api/phones/filters/`, `GET /api/phones/export.csv`, `GET /api/phones/<id>/` |
| Usage | `GET /api/usage/`, `GET /api/alerts/` |
| Keys | `GET /api/keys/`, `PUT /api/keys/<slug>/` |

Frontend default API base: `NEXT_PUBLIC_API_URL` → `http://127.0.0.1:8000`.

---

## Configuration

Copy `.env.example` → `.env`. Important variables:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Required Django secret (no default) |
| `DEBUG` / `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | Runtime & HTTPS |
| `FRONTEND_ORIGINS` | CORS/CSRF for Phone Desk |
| `POSTGRES_*` or `DATABASE_URL` | Database (local Docker or Supabase) |
| `REDIS_URL` | Celery broker |
| `ORCHESTRATION_CITIES` / `ORCHESTRATION_CATEGORIES` / `ORCHESTRATION_LIMIT` | Default cycle targets |
| `YELP_API_KEY`, `GOOGLE_PLACES_API_KEY`, `FOURSQUARE_API_KEY`, … | Optional provider keys |
| `GEOAPIFY_API_KEY`, `LOCATIONIQ_API_KEY`, `MYTOMTOM_API_KEY`, `DIALCODE_API_KEY` | Active free-tier style sources |
| `OVERPASS_URL`, `OVERPASS_USER_AGENT` | OSM (real contact User-Agent required) |
| `HTTP_TIMEOUT`, `HTTP_MAX_RETRIES`, `SOURCE_ERROR_COOLDOWN_MINUTES` | Hardening |

Keys can also be pasted in Phone Desk → **Keys** (encrypted in DB; env remains fallback).

---

## Docs

| Doc | Contents |
|-----|----------|
| [docs/production-runbook.md](docs/production-runbook.md) | Start order, Windows vs Linux workers, health checks, env tunables |
| [docs/adding-a-source.md](docs/adding-a-source.md) | Register a new API or authorized website |
| [docs/categories.md](docs/categories.md) | Orchestration categories and OSM tag map |
| [docs/compliance.md](docs/compliance.md) | Provider ToS, attribution, crawl policy |

---

## Security & compliance

- Commit **only** `.env.example`. Never commit `.env`, `logs/`, or real API keys.
- Rotate any key that appeared in logs, terminals, or chat.
- Prefer secret scanning (`gitleaks` / `trufflehog`) before push.
- Stay inside free/approved quotas; keep full provenance; APIs over scraping.
- Authorized websites only (`source_type=website` + `authorized=true` + allowlisted base URL).
- OSM: respect ODbL / attribution and use an identifying User-Agent.

---

## Verification checklist

1. Redis up; one worker + one Beat; `celery -A config inspect ping`
2. `enrich_phones --limit 3` updates enrichment fields
3. `run_acquisition_cycle --dry-run` then a live cycle → HarvestRun + AcquisitionDecision
4. Admin dashboard loads; pause a source → dry-run skips it
5. Phone Desk Start collects; Stop disables the loop; Usage shows quotas
6. `crawl_authorized` refuses non-authorized sources
7. `logs/app.log` has **no** raw `apiKey=` / `?key=` values

---

## License / use

Collect only publicly listed business contact data within each provider’s terms and your organization’s approvals. This project is built for internal operator use with staff authentication — it is not a public phone dump API.
