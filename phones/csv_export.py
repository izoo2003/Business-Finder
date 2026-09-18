"""Shared CSV helpers for Excel-friendly phone exports."""

from __future__ import annotations

import csv
from datetime import datetime
from typing import Iterable

from django.http import HttpResponse
from django.utils import timezone

from phones.models import PhoneRecord

# Friendly column titles for spreadsheet apps (Excel / Sheets / Numbers).
EXPORT_HEADERS = [
    "Phone",
    "E.164",
    "Business",
    "Address",
    "City",
    "State",
    "ZIP",
    "Category",
    "Source",
    "Line type",
    "First seen",
    "Last seen",
]


def _as_excel_text(value: str | None) -> str:
    """Prefix so Excel keeps phone numbers as text, not scientific notation."""
    text = (value or "").strip()
    if not text:
        return ""
    return f"\t{text}"


def _format_when(value: datetime | None) -> str:
    if value is None:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def phone_export_row(row: PhoneRecord) -> list[str]:
    return [
        _as_excel_text(row.national_format or row.e164),
        _as_excel_text(row.e164),
        row.business_name or "",
        row.address or "",
        row.city or "",
        row.state or "",
        row.postal_code or "",
        row.category or "",
        row.source.name if row.source_id else "",
        row.line_type or "",
        _format_when(row.first_seen_at),
        _format_when(row.last_seen_at),
    ]


def build_phone_csv_response(
    rows: Iterable[PhoneRecord],
    *,
    filename_prefix: str = "phone_numbers",
) -> HttpResponse:
    stamp = timezone.now().strftime("%Y-%m-%d_%H%M")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{filename_prefix}_{stamp}.csv"'
    )
    # UTF-8 BOM so Excel on Windows detects encoding correctly.
    response.write("\ufeff")
    writer = csv.writer(response, dialect="excel", lineterminator="\r\n")
    writer.writerow(EXPORT_HEADERS)
    for row in rows:
        writer.writerow(phone_export_row(row))
    return response
