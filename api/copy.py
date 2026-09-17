"""Plain-English quota copy for non-technical operators."""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from django.utils.timesince import timeuntil

from sources.models import DataSource
from sources.quota import usable_remaining


def window_label(source: DataSource) -> str:
    if source.window_type == DataSource.WindowType.SOFT:
        return "always"
    if source.window_type == DataSource.WindowType.DAILY:
        return "today"
    return "this month"


def reset_phrase(source: DataSource) -> str:
    reset_at = source.quota_reset_at
    if not reset_at:
        return ""
    now = timezone.now()
    if reset_at <= now:
        return "A new batch of free lookups should be available now."
    return f"More free lookups arrive {timeuntil(reset_at, now)}."


def status_label(status: str) -> str:
    return {
        DataSource.QuotaStatus.HEALTHY: "Plenty left",
        DataSource.QuotaStatus.LOW: "Running low",
        DataSource.QuotaStatus.EXHAUSTED: "Out of free lookups",
        DataSource.QuotaStatus.ERROR: "Paused after an error",
    }.get(status, status)


def used_percent(source: DataSource) -> int | None:
    if not source.quota_max or source.quota_remaining is None:
        return None
    used = max(0, source.quota_max - source.quota_remaining)
    return min(100, int(round(100 * used / source.quota_max)))


def plain_english(source: DataSource) -> str:
    name = source.name
    if source.window_type == DataSource.WindowType.SOFT:
        return (
            f"{name} is free to use. We go slowly so the public map service stays happy."
        )
    remaining = source.quota_remaining
    maximum = source.quota_max
    window = window_label(source)
    reset = reset_phrase(source)
    if source.quota_status == DataSource.QuotaStatus.EXHAUSTED:
        return (
            f"{name} is out of free lookups {window}. "
            f"Add a new key on the Keys page. {reset}"
        ).strip()
    if source.quota_status == DataSource.QuotaStatus.ERROR:
        return (
            f"{name} hit an error and is paused for a bit. "
            "It will try again on its own, or you can paste a fresh key."
        )
    if remaining is None or not maximum:
        return f"{name} is ready to use."
    usable = usable_remaining(source)
    extra = f" {reset}" if reset else ""
    if source.quota_status == DataSource.QuotaStatus.LOW:
        return (
            f"{name}: {remaining:,} of {maximum:,} free lookups left {window}. "
            f"That is getting low (about {usable:,} still usable).{extra}"
        )
    return (
        f"{name}: {remaining:,} of {maximum:,} free lookups left {window}.{extra}"
    )


def isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.isoformat()
