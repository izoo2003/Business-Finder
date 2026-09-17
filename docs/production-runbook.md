# Production runbook

## Start order

1. Postgres (`docker compose up -d db`) — healthy; ports bound to `127.0.0.1` only
2. Redis (`docker compose up -d redis`) — `127.0.0.1:6379`
3. `python manage.py migrate` && `python manage.py seed_sources`
4. Celery worker
5. Celery Beat (**one instance only**)
6. Production WSGI (do **not** use `runserver` in production)

## Windows (local)

```powershell
docker compose up -d
celery -A config worker -l info --pool=solo -n worker1@%h
celery -A config beat -l info
python manage.py runserver
```

Use a unique `-n` if you ever run multiple workers. Avoid duplicate default nodenames.

## Linux / Compose workers

```powershell
docker compose --profile workers up -d
```

Compose `worker` / `beat` services use the default Celery pool (Linux containers). On Windows hosts, prefer the venv + `--pool=solo` path above.

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
| Broker connection refused | Start Redis; confirm `REDIS_URL` |
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
