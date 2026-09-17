"""List sources and rotate API keys from the operator UI."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from api.copy import isoformat, plain_english, status_label
from api.permissions import IsStaffUser
from sources.crypto import last4
from sources.key_rotation import KeyRotationError, rotate_api_key
from sources.models import DataSource
from sources.provider_guides import guide_for

# Not shown on the Keys desk (no operator key rotation for these).
KEYS_PAGE_EXCLUDED_SLUGS = frozenset({"google-places"})


def _key_card(source: DataSource) -> dict:
    guide = guide_for(source.slug)
    needs_key = bool(guide["needs_key"] or source.api_key_env_var)
    key = source.get_api_key()
    origin = "none"
    if needs_key:
        origin = source.key_origin()
    # OSM needs no key; keyed sources are connected when a live key is present.
    if source.slug == "openstreetmap":
        connected = True
    elif needs_key:
        connected = bool(key)
    else:
        connected = False
    return {
        "slug": source.slug,
        "name": source.name,
        "needs_key": needs_key,
        "has_key": bool(key) if needs_key else True,
        "connected": connected,
        "connection_label": "Connected" if connected else "Not connected",
        "key_origin": origin,
        "key_hint": (source.api_key_hint or last4(key)) if needs_key else "",
        "is_active": source.is_active,
        "quota_status": source.quota_status,
        "quota_status_label": status_label(source.quota_status),
        "plain_english": plain_english(source),
        "signup_url": guide["signup_url"],
        "steps": guide["steps"],
        "warning": guide["warning"],
        "reset_at": isoformat(source.quota_reset_at),
    }


@api_view(["GET"])
@permission_classes([IsStaffUser])
def key_list(request: Request) -> Response:
    sources = (
        DataSource.objects.exclude(slug__in=KEYS_PAGE_EXCLUDED_SLUGS)
        .order_by("priority", "name")
    )
    return Response({"results": [_key_card(src) for src in sources]})


@api_view(["POST"])
@permission_classes([IsStaffUser])
def key_rotate(request: Request, slug: str) -> Response:
    if slug in KEYS_PAGE_EXCLUDED_SLUGS:
        return Response({"detail": "Source not found."}, status=HTTP_404_NOT_FOUND)
    try:
        source = DataSource.objects.get(slug=slug)
    except DataSource.DoesNotExist:
        return Response({"detail": "Source not found."}, status=HTTP_404_NOT_FOUND)
    raw = str(request.data.get("api_key") or "")
    try:
        result = rotate_api_key(source, raw, verify=True)
    except KeyRotationError as exc:
        return Response({"detail": str(exc)}, status=HTTP_400_BAD_REQUEST)
    source.refresh_from_db()
    payload = _key_card(source)
    payload.update(result)
    return Response(payload)
