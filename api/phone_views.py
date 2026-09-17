"""Phone list, detail, filters, and CSV export."""

from __future__ import annotations

import csv

from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_404_NOT_FOUND

from api.copy import isoformat
from api.permissions import IsStaffUser
from phones.models import PhoneRecord
from sources.models import DataSource


class PhonePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def _filtered_phones(request: Request) -> QuerySet[PhoneRecord]:
    qs = PhoneRecord.objects.select_related("source").all()
    search = str(request.query_params.get("q") or "").strip()
    state = str(request.query_params.get("state") or "").strip().upper()
    city = str(request.query_params.get("city") or "").strip()
    source = str(request.query_params.get("source") or "").strip()
    if search:
        qs = qs.filter(
            Q(e164__icontains=search)
            | Q(national_format__icontains=search)
            | Q(business_name__icontains=search)
            | Q(city__icontains=search)
            | Q(category__icontains=search)
        )
    if state:
        qs = qs.filter(state=state)
    if city:
        qs = qs.filter(city__iexact=city)
    if source:
        qs = qs.filter(source__slug=source)
    return qs


def _list_item(row: PhoneRecord) -> dict:
    return {
        "id": row.pk,
        "phone": row.national_format or row.e164,
        "e164": row.e164,
        "business": row.business_name or "Unknown business",
        "city": row.city,
        "state": row.state,
        "category": row.category,
        "source": row.source.name if row.source_id else "",
        "source_slug": row.source.slug if row.source_id else "",
        "line_type": row.line_type,
        "last_seen_at": isoformat(row.last_seen_at),
    }


def _detail(row: PhoneRecord) -> dict:
    payload = _list_item(row)
    payload.update(
        {
            "address": row.address,
            "postal_code": row.postal_code,
            "area_code": row.area_code,
            "raw_phone": row.raw_phone,
            "source_url": row.source_url,
            "source_query": row.source_query,
            "validation": row.get_validation_status_display(),
            "enrichment": row.get_enrichment_status_display(),
            "carrier": row.carrier,
            "risk_level": row.risk_level,
            "geography": row.enrichment_geo,
            "first_seen_at": isoformat(row.first_seen_at),
            "enriched_at": isoformat(row.enriched_at),
        }
    )
    return payload


@api_view(["GET"])
@permission_classes([IsStaffUser])
def phone_list(request: Request) -> Response:
    qs = _filtered_phones(request)
    paginator = PhonePagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response([_list_item(row) for row in page])


@api_view(["GET"])
@permission_classes([IsStaffUser])
def phone_detail(request: Request, pk: int) -> Response:
    try:
        row = PhoneRecord.objects.select_related("source").get(pk=pk)
    except PhoneRecord.DoesNotExist:
        return Response({"detail": "Number not found."}, status=HTTP_404_NOT_FOUND)
    return Response(_detail(row))


@api_view(["GET"])
@permission_classes([IsStaffUser])
def phone_filters(request: Request) -> Response:
    states = list(
        PhoneRecord.objects.exclude(state="")
        .values_list("state", flat=True)
        .distinct()
        .order_by("state")
    )
    cities = list(
        PhoneRecord.objects.exclude(city="")
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")[:200]
    )
    sources = list(
        DataSource.objects.order_by("priority", "name").values("slug", "name")
    )
    return Response({"states": states, "cities": cities, "sources": sources})


@api_view(["GET"])
@permission_classes([IsStaffUser])
def phone_export(request: Request) -> HttpResponse:
    qs = _filtered_phones(request)
    response = HttpResponse(content_type="text/csv")
    stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    response["Content-Disposition"] = f'attachment; filename="phone_numbers_{stamp}.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "phone",
            "business",
            "address",
            "city",
            "state",
            "category",
            "source",
            "line_type",
            "last_seen",
        ]
    )
    for row in qs.iterator():
        writer.writerow(
            [
                row.national_format or row.e164,
                row.business_name,
                row.address,
                row.city,
                row.state,
                row.category,
                row.source.name if row.source_id else "",
                row.line_type,
                row.last_seen_at.isoformat() if row.last_seen_at else "",
            ]
        )
    return response
