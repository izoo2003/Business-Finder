"""Celery tasks for phone enrichment (Phase 6)."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from phones.enrichment.service import enrich_record
from phones.models import PhoneRecord

logger = logging.getLogger("phones")


@shared_task(name="phones.tasks.enrich_phone_record", bind=True, max_retries=2)
def enrich_phone_record(self, phone_id: int) -> dict:
    try:
        record = PhoneRecord.objects.get(pk=phone_id)
    except PhoneRecord.DoesNotExist:
        logger.warning("enrich_phone_record: phone id=%s not found", phone_id)
        return {"ok": False, "reason": "not_found", "phone_id": phone_id}

    enrich_record(record)
    record.refresh_from_db()
    return {
        "ok": True,
        "phone_id": phone_id,
        "e164": record.e164,
        "enrichment_status": record.enrichment_status,
    }


@shared_task(name="phones.tasks.enrich_pending_batch")
def enrich_pending_batch(limit: int = 25) -> dict:
    """
    Enrich pending / offline_only / stale records (Beat + management command).
    Processes sequentially so DialCode quota is respected per call.
    """
    limit = max(1, min(int(limit), 100))
    stale_days = getattr(settings, "ENRICHMENT_STALE_DAYS", 30)
    stale_before = timezone.now() - timedelta(days=stale_days)

    qs = (
        PhoneRecord.objects.filter(validation_status=PhoneRecord.ValidationStatus.VALID)
        .filter(
            Q(
                enrichment_status__in=[
                    PhoneRecord.EnrichmentStatus.PENDING,
                    PhoneRecord.EnrichmentStatus.OFFLINE_ONLY,
                    PhoneRecord.EnrichmentStatus.FAILED,
                ]
            )
            | Q(enriched_at__isnull=True)
            | Q(enriched_at__lt=stale_before)
        )
        .order_by("enriched_at", "id")
    )

    ids = list(qs.values_list("id", flat=True)[:limit])
    results = []
    for pk in ids:
        # Call synchronously inside the batch worker to avoid stampeding DialCode.
        result = enrich_phone_record(pk)
        results.append(result)

    logger.info("enrich_pending_batch processed=%s", len(results))
    return {"processed": len(results), "results": results}
