"""Ingest BusinessCandidates into PhoneRecord using Phase 4 normalization."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from acquisition.candidates import BusinessCandidate
from acquisition.overpass import OverpassPOI
from phones.models import PhoneRecord
from phones.normalization import normalize_us_phone
from sources.models import DataSource

logger = logging.getLogger("acquisition")


def _enqueue_enrichment(phone_id: int) -> None:
    """Fire Celery enrichment after the ingest transaction commits."""
    try:
        from phones.tasks import enrich_phone_record

        enrich_phone_record.delay(phone_id)
    except Exception:  # noqa: BLE001 — ingest must not fail if broker is down
        logger.exception("Failed to enqueue enrichment for phone id=%s", phone_id)


@dataclass
class IngestStats:
    fetched: int = 0
    saved: int = 0
    updated: int = 0
    skipped: int = 0


def poi_to_candidate(poi: OverpassPOI) -> BusinessCandidate:
    return BusinessCandidate(
        raw_phone=poi.phone_raw,
        business_name=poi.name or "Unknown",
        address=poi.address,
        city=poi.city,
        state=poi.state,
        postal_code=poi.postal_code,
        category=poi.category,
        source_record_id=poi.source_record_id,
        source_url=poi.source_url,
        raw_payload={
            "osm_type": poi.osm_type,
            "osm_id": poi.osm_id,
            "tags": poi.tags,
            "lat": poi.lat,
            "lon": poi.lon,
        },
    )


def ingest_candidates(
    candidates: list[BusinessCandidate],
    *,
    source: DataSource,
    city_hint: str,
    category_label: str,
    source_query: str,
    limit: int = 25,
) -> IngestStats:
    stats = IngestStats(fetched=len(candidates))
    now = timezone.now()

    for candidate in candidates:
        if stats.saved + stats.updated >= limit:
            break

        raw = candidate.raw_phone
        normalized = normalize_us_phone(raw)
        if not normalized:
            stats.skipped += 1
            logger.info(
                "Skip invalid/non-US phone %r for %s",
                raw,
                candidate.source_record_id,
            )
            continue

        state = normalized.state or (
            candidate.state[:2].upper() if candidate.state else ""
        )
        defaults = {
            "national_format": normalized.national_format,
            "raw_phone": raw[:64],
            "area_code": normalized.area_code,
            "state": state,
            "business_name": (candidate.business_name or "Unknown")[:255],
            "address": (candidate.address or "")[:512],
            "city": (candidate.city or city_hint)[:128],
            "postal_code": (candidate.postal_code or "")[:16],
            "category": (candidate.category or category_label)[:128],
            "source": source,
            "source_record_id": (candidate.source_record_id or "")[:128],
            "source_url": (candidate.source_url or "")[:1024],
            "source_query": source_query[:512],
            "raw_payload": candidate.raw_payload or {},
            "validation_status": PhoneRecord.ValidationStatus.VALID,
            "enrichment_status": PhoneRecord.EnrichmentStatus.PENDING,
            "last_seen_at": now,
        }

        with transaction.atomic():
            obj, created = PhoneRecord.objects.get_or_create(
                e164=normalized.e164,
                defaults={**defaults, "first_seen_at": now},
            )
            if created:
                stats.saved += 1
                logger.info("Created %s (%s)", normalized.e164, obj.business_name)
                phone_id = obj.pk
                transaction.on_commit(lambda pk=phone_id: _enqueue_enrichment(pk))
            else:
                obj.last_seen_at = now
                obj.national_format = normalized.national_format
                obj.area_code = normalized.area_code
                if normalized.state:
                    obj.state = normalized.state
                obj.validation_status = PhoneRecord.ValidationStatus.VALID
                if not obj.business_name and defaults["business_name"]:
                    obj.business_name = defaults["business_name"]
                if city_hint and not obj.city:
                    obj.city = city_hint[:128]
                obj.save(
                    update_fields=[
                        "last_seen_at",
                        "national_format",
                        "area_code",
                        "state",
                        "validation_status",
                        "business_name",
                        "city",
                        "updated_at",
                    ]
                )
                stats.updated += 1
                logger.info("Updated last_seen for %s", normalized.e164)

    source.last_successful_run_at = now
    source.save(update_fields=["last_successful_run_at", "updated_at"])
    logger.info(
        "Ingest done: fetched=%s saved=%s updated=%s skipped=%s",
        stats.fetched,
        stats.saved,
        stats.updated,
        stats.skipped,
    )
    return stats


def ingest_pois(
    pois: list[OverpassPOI],
    *,
    source: DataSource,
    city_hint: str,
    category_label: str,
    source_query: str,
    limit: int = 25,
) -> IngestStats:
    """Backward-compatible OSM wrapper around ingest_candidates."""
    return ingest_candidates(
        [poi_to_candidate(p) for p in pois],
        source=source,
        city_hint=city_hint,
        category_label=category_label,
        source_query=source_query,
        limit=limit,
    )
