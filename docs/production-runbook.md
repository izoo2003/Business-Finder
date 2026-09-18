# Production runbook

## Product rule

**Operators never start Redis or Celery.** Those run as always-on hosting services.  
Phone Desk **Start** / **Stop** only turns collection on or off.

Live Railway setup: [railway-deploy.md](railway-deploy.md).

## Start order (infrastructure)

1. Postgres — healthy
2. Redis
3. `python manage.py migrate` && `python manage.py seed_sources`
4. Celery **worker** (always on, restart on failure)
5. Celery **Beat** (**one instance only**, always on)
6. Production WSGI (do **not** use `runserver` in production)
7. Frontend (Phone Desk)

## Windows (local operator machine)

```powershell
powershell -File .\scripts\start-operator.ps1
```

Or manually:

```powershell
docker compose up -d db redis
celery -A config worker -l info --pool=solo -n worker1@%h
celery -A config beat -l info
python manage.py runserver
```

Use a unique `-n` if you ever run multiple workers. Avoid duplicate default nodenames.

## Linux / VPS (Docker)

```bash
docker compose up -d
```

Starts Postgres, Redis, **worker**, and **Beat** with `restart: unless-stopped`. Run Gunicorn / the frontend beside that stack (or behind your reverse proxy).

## Railway (recommended live)

See [railway-deploy.md](railway-deploy.md): separate **web**, **worker**, **beat** services + Redis plugin. Same repo; different start commands. After that, users only press Start in Phone Desk.

## Secrets & GitHub readiness

1. **Never commit** `.env`, `logs/`, or files with real API keys. Only `.env.example` (empty placeholders) belongs in git.
2. **Rotate keys** that ever appeared in `logs/app.log`, terminal output, chat, or issues — especially Geoapify, LocationIQ, TomTom (query-string keys), plus Django `SECRET_KEY`, Supabase DB password / secret keys if this machine or chat shared them.
3. Before first push, run a secret scan (e.g. [gitleaks](https://github.com/gitleaks/gitleaks) or [trufflehog](https://github.com/trufflesecurity/trufflehog)) on the working tree.
4. Confirm: `git check-ignore -v .env logs/app.log` and that `git status` does not list them.
5. Do **not** paste terminal lines that contain `apiKey=` / `?key=` into GitHub issues or PRs.
6. Prefer `REDIS_URL=redis://:PASSWORD@127.0.0.1:6379/0` if Redis is reachable beyond localhost.

When `DEBUG=False`, Django enables HTTPS redirects, secure cookies, and HSTS. Set `CSRF_TRUSTED_ORIGINS` to your real HTTPS origin(s).

## Health checks

```powershell
celery -A config inspect ping --timeout 5
python manage.py run_acquisition_cycle --dry-run
```

- Logs: `logs/app.log` (must never contain raw API keys; httpx is WARNING-only)
- Admin dashboard: `/admin/` (quotas, harvest, alerts, decisions)

## Common failures

| Symptom | Action |
|---------|--------|
| DuplicateNodenameWarning | Kill extra workers; start one with `-n worker1@%h` |
| Broker connection refused | Start Redis; confirm `REDIS_URL` on web **and** worker/beat |
| Scraper “temporarily unavailable” | Worker or Redis down — redeploy Railway worker/Redis; not a Phone Desk setting |
| Source stuck ERROR | Wait `SOURCE_ERROR_COOLDOWN_MINUTES` or set Healthy in admin |
| Quota exhausted | Wait reset; scheduler falls through to OSM/soft sources |
| Beat not firing | Ensure single Beat process; check `CELERY_BEAT_SCHEDULE` |
| `SECRET_KEY` ImproperlyConfigured | Set a long random `SECRET_KEY` in `.env` (required; no default) |

## Env tunables (Phase 9)

| Variable | Default | Purpose |
|----------|---------|---------|
| `HTTP_TIMEOUT` | 30 | httpx timeout seconds |
| `HTTP_MAX_RETRIES` | 3 | retries on 429/5xx/network |
| `SOURCE_ERROR_COOLDOWN_MINUTES` | 60 | auto-clear ERROR status |
| `ORCHESTRATION_LIMIT` | 25 | phones per acquisition cycle |
| `AUTHORIZED_CRAWL_DELAY_SECONDS` | 1.5 | polite delay between pages |
| `CSRF_TRUSTED_ORIGINS` | (empty) | HTTPS origins when `DEBUG=False` |
| `SECURE_SSL_REDIRECT` | True when `DEBUG=False` | Force HTTPS in production |
