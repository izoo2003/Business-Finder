"""Apply offline + DialCode enrichment to a PhoneRecord."""

from __future__ import annotations

import logging

from django.utils import timezone

from phones.enrichment.dialcode import DialCodeClient
from phones.enrichment.offline import enrich_offline
from phones.models import PhoneRecord
from sources.models import DataSource
from sources.quota import QuotaDenied, preflight_ok, require_preflight

logger = logging.getLogger("phones")

DIALCODE_SLUG = "dialcode"


def enrich_record(record: PhoneRecord) -> PhoneRecord:
    """
    Run offline enrichment always; DialCode when source is active and has quota.
    Updates and saves the record; returns the refreshed instance.
    """
    now = timezone.now()
    update_fields = [
        "enrichment_status",
        "line_type",
        "carrier",
        "risk_level",
        "risk_signals",
        "enrichment_geo",
        "enriched_at",
        "enrichment_raw",
        "enrichment_error",
        "updated_at",
    ]

    offline = enrich_offline(record.e164)
    if not offline:
        record.enrichment_status = PhoneRecord.EnrichmentStatus.FAILED
        record.enrichment_error = "Offline parse failed for E.164"
        record.enriched_at = now
        record.save(update_fields=update_fields)
        return record

    record.national_format = offline.national_format
    record.line_type = offline.line_type
    if offline.area_code and not record.area_code:
        record.area_code = offline.area_code
        update_fields.append("area_code")
    if offline.state and not record.state:
        record.state = offline.state
        update_fields.append("state")
    record.enrichment_geo = offline.enrichment_geo
    update_fields.append("national_format")

    dial_source = _load_dialcode_source()
    if dial_source is None:
        record.enrichment_status = PhoneRecord.EnrichmentStatus.OFFLINE_ONLY
        record.enrichment_error = "DialCode source not registered"
        record.enriched_at = now
        record.save(update_fields=update_fields)
        return record

    api_key = dial_source.get_api_key()
    if not api_key:
        record.enrichment_status = PhoneRecord.EnrichmentStatus.OFFLINE_ONLY
        record.enrichment_error = "DIALCODE_API_KEY not set"
        record.enriched_at = now
        record.save(update_fields=update_fields)
        return record

    ok, reason = preflight_ok(dial_source, min_calls=1)
    if not ok:
        record.enrichment_status = PhoneRecord.EnrichmentStatus.OFFLINE_ONLY
        record.enrichment_error = f"DialCode skipped: {reason}"
        record.enriched_at = now
        record.save(update_fields=update_fields)
        return record

    try:
        require_preflight(dial_source, min_calls=1)
        client = DialCodeClient(api_key)
        result = client.lookup(record.e164, source=dial_source)
    except QuotaDenied as exc:
        record.enrichment_status = PhoneRecord.EnrichmentStatus.OFFLINE_ONLY
        record.enrichment_error = str(exc)
        record.enriched_at = now
        record.save(update_fields=update_fields)
        return record
    except Exception as exc:  # noqa: BLE001 — persist failure on record
        logger.exception("DialCode lookup failed for %s", record.e164)
        record.enrichment_status = PhoneRecord.EnrichmentStatus.FAILED
        record.enrichment_error = str(exc)[:2000]
        record.enriched_at = now
        record.save(update_fields=update_fields)
        return record

    if result.line_type:
        record.line_type = result.line_type
    if result.carrier:
        record.carrier = result.carrier
    if result.risk_level:
        record.risk_level = result.risk_level
    record.risk_signals = result.risk_signals or []
    if result.enrichment_geo:
        record.enrichment_geo = result.enrichment_geo
    record.enrichment_raw = result.raw
    record.enrichment_error = ""
    record.enrichment_status = PhoneRecord.EnrichmentStatus.ENRICHED
    record.enriched_at = now
    record.save(update_fields=update_fields)
    logger.info(
        "Enriched %s status=%s line_type=%s risk=%s",
        record.e164,
        record.enrichment_status,
        record.line_type,
        record.risk_level,
    )
    return record


def _load_dialcode_source() -> DataSource | None:
    try:
        return DataSource.objects.get(slug=DIALCODE_SLUG)
    except DataSource.DoesNotExist:
        return None
