# Adding a data source

## 1. Registry entry

Add a dict to `DEFAULT_SOURCES` in [`sources/management/commands/seed_sources.py`](../sources/management/commands/seed_sources.py), or create via Admin → Data sources:

| Field | Purpose |
|-------|---------|
| `name` / `slug` | Unique id used by runner (`slug`) |
| `source_type` | `api` or `website` |
| `priority` | Lower = preferred by scheduler |
| `is_active` | Pause/resume without deleting |
| `api_key_env_var` | Env var name used as fallback if no key is pasted in the operator UI |
| `quota_max` / `window_type` | Free-tier window (daily / monthly / soft) |
| `safety_buffer_percent` | Leave unused (typically 10) |
| `allowed_params` | Documented query capabilities |

Run:

```powershell
python manage.py seed_sources
```

## 2. Credentials

Paste keys in the operator **Keys** page (stored encrypted in the database and used immediately). `.env` is still a fallback for local setup. Restart the worker after changing `.env` only — UI-pasted keys do not need a restart.

## 3. Client + runner

1. Implement a client under `acquisition/` that returns `BusinessCandidate` (or `ClientSearchResult` with resume cursor).
2. Register the slug in `ACQUISITION_SLUGS` / `MIN_CALLS` in [`acquisition/runner.py`](../acquisition/runner.py).
3. Call `record_api_call` after each paid request; use `request_with_retries` for HTTP.

## 4. Authorized websites

Only when company-approved:

```json
{
  "authorized": true,
  "base_url": "https://example.com/directory/",
  "start_paths": ["/"],
  "delay_seconds": 1.5
}
```

`source_type` must be `website`. Test:

```powershell
python manage.py crawl_authorized --slug your-slug --limit 5
```

Unauthorized sources are refused.

## 5. Verify

```powershell
python manage.py run_acquisition_cycle --dry-run
python manage.py fetch_<slug> --city Austin --category restaurant --limit 5
```

Check Admin → Harvest runs and Acquisition decisions.
