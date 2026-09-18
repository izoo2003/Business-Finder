# Railway setup (click-by-click)

You already have the **web** app and `REDIS_URL`. You still need two more always-on services from the **same GitHub repo**: **worker** and **beat**. Without them, Phone Desk shows collection as unavailable.

Operators never do this. You do it **once**.

---

## What you should end up with

In one Railway project:

| Service | What it does | Public URL? |
|---------|--------------|-------------|
| Your existing API (web) | Serves `/api` | Yes |
| Redis | Job queue (`REDIS_URL`) | No |
| **worker** (new) | Actually collects numbers | No |
| **beat** (new) | Timers / scheduled jobs | No |

---

## Step 1 — Open the project

1. Go to [railway.app](https://railway.app) → your project.
2. Confirm you see your **web/API** service and that it has `REDIS_URL` in Variables.

---

## Step 2 — Create the worker service

1. Click **+ New**.
2. Choose **GitHub Repo** (same repo as the web service).
3. After it appears, click the new service → rename it to **`worker`** (click the name at the top).
4. Open **Settings**.
5. Under **Build** / **Deploy**, find **Custom Start Command** (or **Start Command**) and set:

```text
celery -A config worker -l info
```

6. If you see **Config as Code** / config file path, you can set it to `railway.worker.toml` instead of typing the command — same result.
7. Open **Variables**.
8. Copy the **same variables** the web service uses. Minimum that must match web:

- `REDIS_URL` (you already have this — add/reference it on worker too)
- `SECRET_KEY`
- `DATABASE_URL` **or** your `POSTGRES_*` / Supabase DB vars
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_ORIGINS`
- Any API keys the web service has (`GEOAPIFY_API_KEY`, etc.)

   Tip: In Railway, use **Variable Reference** / shared variables so worker reads the same `REDIS_URL` as web (don’t invent a second Redis).

9. **Do not** click “Generate domain” for worker. Leave it private.
10. Deploy (Railway usually deploys automatically). Wait until status is **Success** / online.
11. Open the **worker** → **Deployments** → latest → **View logs**. You should see Celery start, something like `celery@... ready`.

---

## Step 3 — Create the beat service

1. Click **+ New** again.
2. Choose the **same GitHub repo**.
3. Rename the service to **`beat`**.
4. **Settings** → **Start Command**:

```text
celery -A config beat -l info
```

   Or config file path: `railway.beat.toml`.

5. **Variables**: same set as web/worker (`REDIS_URL`, DB, `SECRET_KEY`, etc.).
6. **No public domain.**
7. Deploy and check logs — Beat should stay running (one process).  
   **Important:** create only **one** beat service. Two Beats double-schedule jobs.

---

## Step 4 — Double-check Redis is shared

On **web**, **worker**, and **beat**:

1. Variables → confirm each has `REDIS_URL`.
2. The value should be the **same** Redis instance (reference the Redis plugin variable if Railway offers it).

If worker has no `REDIS_URL`, it cannot see jobs from Start collecting.

---

## Step 5 — Verify in Phone Desk

1. Open your live Phone Desk (frontend).
2. Sign in → **Scraper**.
3. The “temporarily unavailable” banner should be **gone**.
4. Press **Start collecting**.
5. Within a minute you should see recent collection activity (or at least “Collecting now”).

If the banner remains:

- Worker deploy failed → read worker logs.
- Worker missing `REDIS_URL` or DB vars → copy from web.
- Web and worker point at different Redis URLs → fix references.

---

## What you do NOT need to do

- Operators do **not** start Redis or Celery.
- **Start collecting** does **not** create these services.
- You do **not** need a public URL on worker or beat.
- After this one-time setup, normal Git pushes redeploy web/worker/beat automatically (each service watches the repo).

---

## Quick copy-paste start commands

| Service | Start command |
|---------|----------------|
| web (already set) | `python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60` |
| worker | `celery -A config worker -l info` |
| beat | `celery -A config beat -l info` |
