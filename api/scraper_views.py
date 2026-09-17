"""Start / stop / status for the operator scraper."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from acquisition.scraper_control import (
    scraper_status,
    start_scraper,
    stop_scraper,
    update_orchestration,
)
from api.copy import isoformat
from api.permissions import IsStaffUser


def _json_status() -> dict:
    payload = scraper_status()
    payload["session_started_at"] = isoformat(payload.get("session_started_at"))
    current = payload.get("current")
    if current:
        current["started_at"] = isoformat(current.get("started_at"))
        current["finished_at"] = isoformat(current.get("finished_at"))
    for run in payload.get("recent_runs") or []:
        run["started_at"] = isoformat(run.get("started_at"))
        run["finished_at"] = isoformat(run.get("finished_at"))
    return payload


@api_view(["GET"])
@permission_classes([IsStaffUser])
def status_view(request: Request) -> Response:
    return Response(_json_status())


@api_view(["POST"])
@permission_classes([IsStaffUser])
def start_view(request: Request) -> Response:
    start_scraper()
    payload = _json_status()
    if not payload["worker_online"] or not payload["redis_online"]:
        payload["detail"] = (
            "Collection is marked as running, but the background worker is offline. "
            "Start Redis and the worker so numbers can be collected."
        )
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsStaffUser])
def stop_view(request: Request) -> Response:
    stop_scraper()
    return Response(_json_status())


@api_view(["PUT"])
@permission_classes([IsStaffUser])
def orchestration_view(request: Request) -> Response:
    try:
        update_orchestration(
            cities=request.data.get("cities"),
            categories=request.data.get("categories"),
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response(_json_status())
