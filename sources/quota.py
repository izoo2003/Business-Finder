"""Quota preflight and counter updates for DataSource registry."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone

from sources.models import DataSource

logger = logging.getLogger("sources")


class QuotaDenied(Exception):
    """Raised when a source fails preflight and must not be called."""


def usable_remaining(source: DataSource) -> int | None:
    """
    Remaining calls after subtracting the safety buffer.
    Returns None for soft/unlimited sources (always usable if active).
    """
    if source.window_type == DataSource.WindowType.SOFT:
        return None
    if source.quota_remaining is None:
        return 0
    if not source.quota_max:
        return max(0, source.quota_remaining)
    buffer = math.ceil(source.quota_max * (source.safety_buffer_percent / 100.0))
    return max(0, source.quota_remaining - buffer)


def ensure_quota_reset(source: DataSource) -> bool:
    """
    If quota_reset_at has passed (or monthly/daily window rolled), restore counters.
    Returns True if a reset was applied.
    """
    now = timezone.now()
    reset = False

    if source.window_type == DataSource.WindowType.SOFT:
        return False

    if source.quota_reset_at and source.quota_reset_at <= now:
        if source.quota_max is not None:
            source.quota_remaining = source.quota_max
        source.quota_status = DataSource.QuotaStatus.HEALTHY
        source.quota_refreshed_at = now
        # Next reset: daily → tomorrow UTC midnight; monthly → first of next month
        if source.window_type == DataSource.WindowType.DAILY:
            tomorrow = (now.astimezone(dt_timezone.utc) + timedelta(days=1)).date()
            source.quota_reset_at = datetime(
                tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=dt_timezone.utc
            )
        elif source.window_type in (
            DataSource.WindowType.MONTHLY,
            DataSource.WindowType.PER_SKU,
        ):
            year, month = now.year, now.month
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1
            source.quota_reset_at = datetime(year, month, 1, tzinfo=dt_timezone.utc)
        source.save(
            update_fields=[
                "quota_remaining",
                "quota_status",
                "quota_refreshed_at",
                "quota_reset_at",
                "updated_at",
            ]
        )
        reset = True
        logger.info("Quota reset for %s remaining=%s", source.slug, source.quota_remaining)

    return reset


def mark_from_remaining(source: DataSource) -> None:
    """Recalculate Healthy / Low / Exhausted from remaining vs buffer."""
    if source.window_type == DataSource.WindowType.SOFT:
        if source.quota_status == DataSource.QuotaStatus.ERROR:
            return
        source.quota_status = DataSource.QuotaStatus.HEALTHY
        return

    usable = usable_remaining(source)
    if usable is None:
        source.quota_status = DataSource.QuotaStatus.HEALTHY
    elif usable <= 0:
        source.quota_status = DataSource.QuotaStatus.EXHAUSTED
    elif source.quota_max and source.quota_remaining is not None:
        buffer = math.ceil(source.quota_max * (source.safety_buffer_percent / 100.0))
        if source.quota_remaining <= buffer * 2:
            source.quota_status = DataSource.QuotaStatus.LOW
        else:
            source.quota_status = DataSource.QuotaStatus.HEALTHY
    else:
        source.quota_status = DataSource.QuotaStatus.HEALTHY


def preflight_ok(source: DataSource, min_calls: int = 1) -> tuple[bool, str]:
    """
    Run preflight checks. Returns (ok, reason).
    Soft sources always pass if active and not in error status.
    """
    ensure_quota_reset(source)
    clear_error_cooldown(source)
    source.refresh_from_db()

    if not source.is_active:
        return False, "source is inactive"
    if source.quota_status == DataSource.QuotaStatus.ERROR:
        return False, "source is in error/cooldown state"
    if source.quota_status == DataSource.QuotaStatus.EXHAUSTED:
        return False, "source quota is exhausted"

    if source.window_type == DataSource.WindowType.SOFT:
        return True, "ok"

    usable = usable_remaining(source)
    if usable is not None and usable < min_calls:
        return False, f"usable remaining {usable} < required {min_calls} (after safety buffer)"

    return True, "ok"


def clear_error_cooldown(source: DataSource) -> bool:
    """
    If source is ERROR and quota_refreshed_at is older than SOURCE_ERROR_COOLDOWN_MINUTES,
    restore HEALTHY (or recalculate from remaining) so transient failures do not stick forever.
    """
    if source.quota_status != DataSource.QuotaStatus.ERROR:
        return False
    from django.conf import settings

    minutes = int(getattr(settings, "SOURCE_ERROR_COOLDOWN_MINUTES", 60))
    now = timezone.now()
    refreshed = source.quota_refreshed_at
    if refreshed is None:
        # No timestamp — clear after first preflight once cooldown setting applies.
        mark_from_remaining(source)
        if source.quota_status == DataSource.QuotaStatus.ERROR:
            source.quota_status = DataSource.QuotaStatus.HEALTHY
        source.quota_refreshed_at = now
        source.save(update_fields=["quota_status", "quota_refreshed_at", "updated_at"])
        logger.info("Cleared ERROR (no timestamp) for %s -> %s", source.slug, source.quota_status)
        return True
    if refreshed > now - timedelta(minutes=minutes):
        return False
    mark_from_remaining(source)
    if source.quota_status == DataSource.QuotaStatus.ERROR:
        source.quota_status = DataSource.QuotaStatus.HEALTHY
    source.quota_refreshed_at = now
    source.save(update_fields=["quota_status", "quota_refreshed_at", "updated_at"])
    logger.info("Cleared ERROR cooldown for %s -> %s", source.slug, source.quota_status)
    return True


def mark_source_error(source: DataSource) -> None:
    """Mark source ERROR and stamp refreshed_at for cooldown tracking."""
    source.quota_status = DataSource.QuotaStatus.ERROR
    source.quota_refreshed_at = timezone.now()
    source.save(update_fields=["quota_status", "quota_refreshed_at", "updated_at"])


def require_preflight(source: DataSource, min_calls: int = 1) -> None:
    ok, reason = preflight_ok(source, min_calls=min_calls)
    if not ok:
        raise QuotaDenied(f"{source.slug}: {reason}")


def record_api_call(
    source: DataSource,
    *,
    remaining: int | None = None,
    limit: int | None = None,
    reset_at=None,
    decrement: int = 1,
) -> None:
    """
    Update quota after an API response.
    Prefer provider `remaining`/`limit` headers when given; else decrement locally.
    """
    now = timezone.now()
    if limit is not None:
        source.quota_max = limit
    if remaining is not None:
        source.quota_remaining = max(0, remaining)
    elif source.quota_remaining is not None:
        source.quota_remaining = max(0, source.quota_remaining - decrement)
    if reset_at is not None:
        source.quota_reset_at = reset_at
    source.quota_refreshed_at = now
    mark_from_remaining(source)
    source.save(
        update_fields=[
            "quota_max",
            "quota_remaining",
            "quota_reset_at",
            "quota_refreshed_at",
            "quota_status",
            "updated_at",
        ]
    )
    logger.info(
        "Quota updated %s remaining=%s status=%s",
        source.slug,
        source.quota_remaining,
        source.quota_status,
    )
