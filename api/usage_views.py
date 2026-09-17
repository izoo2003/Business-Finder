"""Quota usage and operator alerts."""

from __future__ import annotations

from config.dashboard import build_dashboard_context
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from api.copy import (
    isoformat,
    plain_english,
    status_label,
    used_percent,
    window_label,
)
from api.permissions import IsStaffUser
from phones.models import PhoneRecord
from sources.crypto import last4
from sources.models import DataSource
from sources.provider_guides import guide_for
from sources.quota import usable_remaining


def _source_usage(source: DataSource) -> dict:
    guide = guide_for(source.slug)
    key = source.get_api_key()
    needs_key = bool(guide["needs_key"] or source.api_key_env_var)
    return {
        "slug": source.slug,
        "name": source.name,
        "is_active": source.is_active,
        "quota_status": source.quota_status,
        "quota_status_label": status_label(source.quota_status),
        "remaining": source.quota_remaining,
        "max": source.quota_max,
        "usable": usable_remaining(source),
        "used_percent": used_percent(source),
        "window_type": source.window_type,
        "window_label": window_label(source),
        "reset_at": isoformat(source.quota_reset_at),
        "last_successful_run_at": isoformat(source.last_successful_run_at),
        "plain_english": plain_english(source),
        "needs_key": needs_key,
        "has_key": bool(key) if needs_key else True,
        "key_origin": source.key_origin() if needs_key else "none",
        "key_hint": source.api_key_hint or last4(key),
    }


def _operator_alerts() -> list[dict]:
    alerts: list[dict] = []
    dash = build_dashboard_context()
    for row in dash["ops_quota_rows"]:
        if not row["is_active"]:
            continue
        status = row["quota_status"]
        if status == DataSource.QuotaStatus.EXHAUSTED:
            alerts.append(
                {
                    "level": "error",
                    "title": f"{row['name']} is out of free lookups",
                    "detail": "Add a new API key on the Keys page so collection can keep going.",
                    "href": "/keys",
                    "slug": row["slug"],
                }
            )
        elif status == DataSource.QuotaStatus.LOW:
            alerts.append(
                {
                    "level": "warning",
                    "title": f"{row['name']} is running low",
                    "detail": "You still have some lookups left. Have a backup key ready.",
                    "href": "/keys",
                    "slug": row["slug"],
                }
            )
        elif status == DataSource.QuotaStatus.ERROR:
            alerts.append(
                {
                    "level": "warning",
                    "title": f"{row['name']} paused after an error",
                    "detail": "It will retry on its own. If this keeps happening, paste a fresh key.",
                    "href": "/keys",
                    "slug": row["slug"],
                }
            )
    for alert in dash["ops_alerts"]:
        if str(alert.get("title", "")).startswith("Quota"):
            continue
        if str(alert.get("title", "")).startswith("API"):
            alerts.append(
                {
                    "level": "error",
                    "title": "A collection run failed",
                    "detail": "Check the Scraper page for the last error. Keys may need to be renewed.",
                    "href": "/scraper",
                    "slug": None,
                }
            )
            break
        if str(alert.get("title", "")).startswith("Yield"):
            alerts.append(
                {
                    "level": "warning",
                    "title": "Fewer numbers than yesterday",
                    "detail": "Collection slowed down. Check Usage and Keys.",
                    "href": "/usage",
                    "slug": None,
                }
            )
    return alerts


@api_view(["GET"])
@permission_classes([IsStaffUser])
def usage_view(request: Request) -> Response:
    sources = [_source_usage(src) for src in DataSource.objects.order_by("priority", "name")]
    dash = build_dashboard_context()
    return Response(
        {
            "phone_total": PhoneRecord.objects.count(),
            "harvest_24h": dash["ops_harvest_24h"],
            "harvest_7d": dash["ops_harvest_7d"],
            "sources": sources,
            "alerts": _operator_alerts(),
        }
    )


@api_view(["GET"])
@permission_classes([IsStaffUser])
def alerts_view(request: Request) -> Response:
    return Response({"alerts": _operator_alerts()})
