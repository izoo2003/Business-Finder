"""Operator Start/Stop for the acquisition loop."""

from __future__ import annotations

import logging
from datetime import timedelta

import redis
from celery.app.control import Inspect
from django.conf import settings
from django.utils import timezone

from acquisition.models import HarvestRun, OrchestrationState
from acquisition.scheduler import (
    next_city_category,
    orchestration_categories,
    orchestration_cities,
    scraper_is_enabled,
)
from config.celery import app as celery_app

logger = logging.getLogger("acquisition")

LOCK_KEY = "scraper:loop:lock"
LOCK_TTL_SECONDS = 180


def redis_client() -> redis.Redis:
    return redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def worker_online() -> bool:
    """True when at least one Celery worker answers ping. Never block the API."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    def _ping() -> bool:
        inspector: Inspect = celery_app.control.inspect(timeout=0.3)
        replies = inspector.ping()
        return bool(replies)

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return bool(pool.submit(_ping).result(timeout=0.8))
    except (FuturesTimeout, Exception):
        logger.debug("Celery inspect ping failed", exc_info=True)
        return False
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def redis_online() -> bool:
    try:
        return bool(redis_client().ping())
    except Exception:
        return False


def acquire_loop_lock(owner: str) -> bool:
    try:
        return bool(redis_client().set(LOCK_KEY, owner, nx=True, ex=LOCK_TTL_SECONDS))
    except Exception:
        logger.warning("Could not acquire scraper lock; continuing without Redis lock")
        return True


def refresh_loop_lock(owner: str) -> None:
    try:
        client = redis_client()
        current = client.get(LOCK_KEY)
        if current in (None, owner):
            client.set(LOCK_KEY, owner, ex=LOCK_TTL_SECONDS)
    except Exception:
        logger.debug("Could not refresh scraper lock", exc_info=True)


def release_loop_lock(owner: str) -> None:
    try:
        client = redis_client()
        current = client.get(LOCK_KEY)
        if current in (None, owner):
            client.delete(LOCK_KEY)
    except Exception:
        logger.debug("Could not release scraper lock", exc_info=True)


def start_scraper() -> OrchestrationState:
    state = OrchestrationState.get_solo()
    state.scraper_enabled = True
    state.session_started_at = timezone.now()
    state.session_saved = 0
    state.session_updated = 0
    state.last_error = ""
    state.save(
        update_fields=[
            "scraper_enabled",
            "session_started_at",
            "session_saved",
            "session_updated",
            "last_error",
            "updated_at",
        ]
    )
    from acquisition.tasks import run_scraper_loop

    try:
        run_scraper_loop.delay()
    except Exception:
        logger.exception("Could not enqueue scraper loop (is Redis running?)")
    logger.info("Scraper started by operator")
    return state


def stop_scraper() -> OrchestrationState:
    state = OrchestrationState.get_solo()
    state.scraper_enabled = False
    state.save(update_fields=["scraper_enabled", "updated_at"])
    logger.info("Scraper stopped by operator")
    return state


def record_session_progress(run: HarvestRun) -> None:
    if not run.pk:
        return
    state = OrchestrationState.get_solo()
    state.session_saved = (state.session_saved or 0) + (run.saved or 0)
    state.session_updated = (state.session_updated or 0) + (run.updated or 0)
    if run.status == HarvestRun.Status.FAILED and run.error:
        state.last_error = run.error[:500]
    elif run.status == HarvestRun.Status.SUCCESS:
        state.last_error = ""
    state.save(
        update_fields=[
            "session_saved",
            "session_updated",
            "last_error",
            "updated_at",
        ]
    )


def scraper_status() -> dict:
    state = OrchestrationState.get_solo()
    latest = (
        HarvestRun.objects.select_related("source")
        .exclude(error="scraper is stopped")
        .order_by("-started_at")
        .first()
    )
    recent = list(
        HarvestRun.objects.select_related("source")
        .exclude(error="scraper is stopped")
        .order_by("-started_at")[:8]
    )
    next_city, next_category = next_city_category(advance=False)
    online = worker_online()
    return {
        "running": scraper_is_enabled(),
        "worker_online": online,
        "redis_online": redis_online(),
        "session_started_at": state.session_started_at,
        "session_saved": state.session_saved,
        "session_updated": state.session_updated,
        "last_error": state.last_error,
        "cities": orchestration_cities(),
        "categories": orchestration_categories(),
        "next_city": next_city,
        "next_category": next_category,
        "current": _run_payload(latest) if latest else None,
        "recent_runs": [_run_payload(run) for run in recent],
        "loop_sleep_seconds": int(getattr(settings, "SCRAPER_LOOP_SLEEP_SECONDS", 10)),
    }


def _normalize_cities(raw) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("cities must be a list of city names")
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        name = str(item).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    if not out:
        raise ValueError("Add at least one city")
    return out


def _normalize_categories(raw) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("categories must be a list of business types")
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        name = str(item).strip().lower()
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    if not out:
        raise ValueError("Add at least one business type")
    return out


def update_orchestration(*, cities, categories) -> dict:
    """Persist operator city/category filters and clamp rotation indexes."""
    cleaned_cities = _normalize_cities(cities)
    cleaned_categories = _normalize_categories(categories)
    state = OrchestrationState.get_solo()
    state.cities = cleaned_cities
    state.categories = cleaned_categories
    if state.city_index >= len(cleaned_cities):
        state.city_index = 0
    if state.category_index >= len(cleaned_categories):
        state.category_index = 0
    state.save(
        update_fields=[
            "cities",
            "categories",
            "city_index",
            "category_index",
            "updated_at",
        ]
    )
    logger.info(
        "Orchestration filters updated cities=%s categories=%s",
        cleaned_cities,
        cleaned_categories,
    )
    return scraper_status()

def loop_sleep_seconds(run: HarvestRun | None) -> float:
    default = float(getattr(settings, "SCRAPER_LOOP_SLEEP_SECONDS", 10))
    if run is None:
        return default
    if run.status == HarvestRun.Status.SKIPPED:
        return max(default, 30.0)
    return default


def _run_payload(run: HarvestRun) -> dict:
    in_progress = run.finished_at is None
    return {
        "id": run.pk,
        "status": run.status,
        "source": run.source.name if run.source_id else None,
        "source_slug": run.source.slug if run.source_id else None,
        "city": run.city,
        "category": run.category,
        "saved": run.saved,
        "updated": run.updated,
        "fetched": run.fetched,
        "error": (run.error or "")[:400],
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "in_progress": in_progress,
        "duration_seconds": (
            None
            if not run.finished_at
            else max(0, int((run.finished_at - run.started_at) / timedelta(seconds=1)))
        ),
    }
