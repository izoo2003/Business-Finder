"""Celery tasks for acquisition orchestration (Phase 7+9)."""

from __future__ import annotations

import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from acquisition.scheduler import execute_cycle, orchestration_limit, scraper_is_enabled
from acquisition.secrets_safe import safe_error_message

logger = logging.getLogger("acquisition")


@shared_task(
    name="acquisition.tasks.run_acquisition_cycle",
    bind=True,
    max_retries=2,
    soft_time_limit=280,
    time_limit=300,
    autoretry_for=(SoftTimeLimitExceeded, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
)
def run_acquisition_cycle(self, limit: int | None = None) -> dict:
    """Beat safety net: only collects while the operator has Start pressed."""
    if not scraper_is_enabled():
        return {"status": "stopped", "harvest_run_id": None}

    run = execute_cycle(dry_run=False, limit=limit)
    from acquisition.scraper_control import record_session_progress

    record_session_progress(run)
    return {
        "harvest_run_id": run.pk,
        "status": str(run.status),
        "source": run.source.slug if run.source_id else None,
        "city": run.city,
        "category": run.category,
        "saved": run.saved,
        "updated": run.updated,
        "error": run.error[:500] if run.error else "",
    }


@shared_task(
    name="acquisition.tasks.run_scraper_loop",
    bind=True,
    ignore_result=True,
    soft_time_limit=None,
    time_limit=None,
)
def run_scraper_loop(self) -> dict:
    """Keep collecting until the operator presses Stop. One loop at a time."""
    from acquisition.scraper_control import (
        acquire_loop_lock,
        record_session_progress,
        refresh_loop_lock,
        release_loop_lock,
        loop_sleep_seconds,
    )

    owner = str(self.request.id or "loop")
    if not acquire_loop_lock(owner):
        logger.info("Scraper loop already running; skip duplicate")
        return {"status": "already_running"}

    cycles = 0
    try:
        while scraper_is_enabled():
            refresh_loop_lock(owner)
            run = execute_cycle(dry_run=False)
            record_session_progress(run)
            cycles += 1
            if not scraper_is_enabled():
                break
            time.sleep(loop_sleep_seconds(run))
    finally:
        release_loop_lock(owner)
    logger.info("Scraper loop exited after %s cycle(s)", cycles)
    return {"status": "stopped", "cycles": cycles}


@shared_task(
    name="acquisition.tasks.run_source_job",
    soft_time_limit=280,
    time_limit=300,
)
def run_source_job(slug: str, city: str, category: str, limit: int | None = None) -> dict:
    """Targeted fetch for a specific source + city + category."""
    from acquisition.models import HarvestRun
    from acquisition.runner import FetchError, run_source_fetch
    from django.utils import timezone

    started = timezone.now()
    run_limit = limit if limit is not None else orchestration_limit()
    try:
        result = run_source_fetch(
            slug,
            city=city,
            category=category,
            limit=run_limit,
            persist_cursor=True,
        )
    except FetchError as exc:
        run = HarvestRun.objects.create(
            source=None,
            city=city,
            category=category,
            started_at=started,
            finished_at=timezone.now(),
            status=HarvestRun.Status.FAILED,
            error=safe_error_message(exc, max_len=4000),
        )
        return {
            "harvest_run_id": run.pk,
            "status": str(run.status),
            "error": run.error[:500],
        }

    stats = result.stats
    run = HarvestRun.objects.create(
        source=result.source,
        city=result.city,
        category=result.category,
        started_at=started,
        finished_at=timezone.now(),
        status=HarvestRun.Status.SUCCESS,
        fetched=stats.fetched,
        saved=stats.saved,
        updated=stats.updated,
        skipped_invalid=stats.skipped,
        quota_remaining_before=result.quota_remaining_before,
        quota_remaining_after=result.quota_remaining_after,
        cursor_before=result.cursor_before or {},
        cursor_after=result.cursor_after or {},
    )
    return {
        "harvest_run_id": run.pk,
        "status": str(run.status),
        "source": result.source.slug,
        "city": result.city,
        "category": result.category,
        "saved": stats.saved,
        "updated": stats.updated,
    }
