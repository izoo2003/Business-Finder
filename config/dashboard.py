"""Operator dashboard context for Django admin index (Phase 8)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from acquisition.models import AcquisitionDecision, HarvestRun
from phones.models import PhoneRecord
from sources.models import DataSource
from sources.quota import usable_remaining


def build_dashboard_context() -> dict:
    now = timezone.now()
    day_ago = now - timedelta(hours=24)
    two_days_ago = now - timedelta(hours=48)
    week_ago = now - timedelta(days=7)

    sources = list(DataSource.objects.order_by("priority", "name"))
    quota_rows = []
    for src in sources:
        quota_rows.append(
            {
                "name": src.name,
                "slug": src.slug,
                "is_active": src.is_active,
                "quota_status": src.quota_status,
                "quota_remaining": src.quota_remaining,
                "quota_max": src.quota_max,
                "usable": usable_remaining(src),
                "quota_reset_at": src.quota_reset_at,
                "last_successful_run_at": src.last_successful_run_at,
                "window_type": src.window_type,
            }
        )

    runs_24h = HarvestRun.objects.filter(started_at__gte=day_ago)
    runs_7d = HarvestRun.objects.filter(started_at__gte=week_ago)
    runs_prev_24h = HarvestRun.objects.filter(
        started_at__gte=two_days_ago, started_at__lt=day_ago
    )

    def harvest_summary(qs):
        return {
            "total": qs.count(),
            "saved": qs.aggregate(s=Sum("saved"))["s"] or 0,
            "updated": qs.aggregate(s=Sum("updated"))["s"] or 0,
            "success": qs.filter(status=HarvestRun.Status.SUCCESS).count(),
            "failed": qs.filter(status=HarvestRun.Status.FAILED).count(),
            "skipped": qs.filter(status=HarvestRun.Status.SKIPPED).count(),
        }

    harvest_24h = harvest_summary(runs_24h)
    harvest_7d = harvest_summary(runs_7d)

    per_source_yield = list(
        runs_7d.values("source__name", "source__slug")
        .annotate(
            runs=Count("id"),
            saved=Sum("saved"),
            updated=Sum("updated"),
            failed=Count("id", filter=Q(status=HarvestRun.Status.FAILED)),
        )
        .order_by("-saved")
    )

    valid_phones = PhoneRecord.objects.filter(
        validation_status=PhoneRecord.ValidationStatus.VALID
    )
    phone_total = valid_phones.count()
    by_state = list(
        valid_phones.exclude(state="")
        .values("state")
        .annotate(n=Count("id"))
        .order_by("-n")[:10]
    )
    by_source = list(
        valid_phones.values("source__name", "source__slug")
        .annotate(n=Count("id"))
        .order_by("-n")[:10]
    )

    alerts = _build_alerts(
        quota_rows=quota_rows,
        runs_24h=runs_24h,
        saved_24h=harvest_24h["saved"],
        saved_prev_24h=runs_prev_24h.aggregate(s=Sum("saved"))["s"] or 0,
    )

    last_decisions = list(
        AcquisitionDecision.objects.select_related("chosen_source").order_by("-created_at")[:8]
    )

    return {
        "ops_quota_rows": quota_rows,
        "ops_harvest_24h": harvest_24h,
        "ops_harvest_7d": harvest_7d,
        "ops_per_source_yield": per_source_yield,
        "ops_phone_total": phone_total,
        "ops_by_state": by_state,
        "ops_by_source": by_source,
        "ops_alerts": alerts,
        "ops_last_decisions": last_decisions,
    }


def _build_alerts(*, quota_rows, runs_24h, saved_24h: int, saved_prev_24h: int) -> list[dict]:
    alerts: list[dict] = []

    for row in quota_rows:
        if not row["is_active"]:
            continue
        if row["quota_status"] in (
            DataSource.QuotaStatus.LOW,
            DataSource.QuotaStatus.EXHAUSTED,
        ):
            level = (
                "error"
                if row["quota_status"] == DataSource.QuotaStatus.EXHAUSTED
                else "warning"
            )
            alerts.append(
                {
                    "level": level,
                    "title": f"Quota {row['quota_status']}: {row['name']}",
                    "detail": (
                        f"Remaining {row['quota_remaining']} / {row['quota_max']} "
                        f"(usable after buffer: {row['usable']})."
                    ),
                }
            )

    failed = list(
        runs_24h.filter(status=HarvestRun.Status.FAILED)
        .select_related("source")
        .order_by("-started_at")[:5]
    )
    if failed:
        lines = []
        for run in failed:
            slug = run.source.slug if run.source_id else "none"
            snippet = (run.error or "")[:120]
            lines.append(f"{slug} @ {run.started_at:%Y-%m-%d %H:%M} — {snippet}")
        alerts.append(
            {
                "level": "error",
                "title": f"API / harvest failures ({len(failed)} shown, last 24h)",
                "detail": " | ".join(lines),
            }
        )

    if saved_prev_24h >= 5 and saved_24h < (saved_prev_24h * 0.5):
        alerts.append(
            {
                "level": "warning",
                "title": "Yield drop detected",
                "detail": (
                    f"Saved last 24h: {saved_24h}; previous 24h: {saved_prev_24h} "
                    f"(below 50% of prior)."
                ),
            }
        )

    return alerts
