"""Programmatic acquisition fetch API shared by CLI and Celery (Phase 7)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from acquisition.secrets_safe import safe_error_message
from acquisition.foursquare import FoursquareClient
from acquisition.geoapify import GeoapifyClient
from acquisition.google_places import GooglePlacesClient
from acquisition.ingest import IngestStats, ingest_candidates, ingest_pois
from acquisition.locationiq import LocationIQClient
from acquisition.models import AcquisitionCursor
from acquisition.overpass import OverpassClient, resolve_category_tag
from acquisition.search_result import ClientSearchResult
from acquisition.tomtom import TomTomClient
from acquisition.yelp import YelpClient
from sources.models import DataSource
from sources.quota import QuotaDenied, mark_source_error, require_preflight

logger = logging.getLogger("acquisition")

ACQUISITION_SLUGS = frozenset(
    {
        "openstreetmap",
        "geoapify",
        "locationiq",
        "tomtom",
        "foursquare",
        "google-places",
        "yelp",
    }
)

# Min usable calls required before starting a fetch.
MIN_CALLS = {
    "openstreetmap": 1,
    "geoapify": 2,
    "locationiq": 2,
    "tomtom": 2,
    "foursquare": 1,
    "google-places": 1,
    "yelp": 1,
}


class FetchError(Exception):
    """Raised when a source fetch cannot complete."""


@dataclass
class FetchResult:
    source: DataSource
    city: str
    category: str
    stats: IngestStats
    cursor_before: dict[str, Any]
    cursor_after: dict[str, Any] | None
    quota_remaining_before: int | None
    quota_remaining_after: int | None


def normalize_city(city: str) -> str:
    return city.strip()


def normalize_category(category: str) -> str:
    return category.strip().lower()


def run_source_fetch(
    slug: str,
    *,
    city: str,
    category: str,
    limit: int = 25,
    resume: dict[str, Any] | None = None,
    country: str = "USA",
    osm_tag: str | None = None,
    persist_cursor: bool = True,
) -> FetchResult:
    """
    Run one acquisition fetch for an active source.
    When persist_cursor is True, load/save AcquisitionCursor for the query key.
    """
    if limit < 1:
        raise FetchError("limit must be >= 1")

    city = normalize_city(city)
    category = normalize_category(category)

    try:
        source = DataSource.objects.get(slug=slug, is_active=True)
    except DataSource.DoesNotExist as exc:
        raise FetchError(
            f"Active source '{slug}' not found. Run: python manage.py seed_sources"
        ) from exc

    is_website = source.source_type == DataSource.SourceType.WEBSITE
    if slug not in ACQUISITION_SLUGS and not is_website:
        raise FetchError(f"Unknown acquisition source slug: {slug}")

    if not is_website and not city:
        raise FetchError("city is required")

    try:
        require_preflight(source, min_calls=MIN_CALLS.get(slug, 1))
    except QuotaDenied as exc:
        raise FetchError(safe_error_message(exc)) from exc

    if (
        not is_website
        and slug != "openstreetmap"
        and source.api_key_env_var
        and not source.get_api_key()
    ):
        raise FetchError(
            f"Missing API key for {source.name}. Set {source.api_key_env_var} in .env."
        )

    if is_website:
        from acquisition.authorized_crawl import AuthorizedCrawlError, crawl_authorized_source

        quota_before = source.quota_remaining
        try:
            stats = crawl_authorized_source(
                source,
                city=city or "",
                category=category or "website",
                limit=limit,
            )
        except AuthorizedCrawlError as exc:
            raise FetchError(safe_error_message(exc)) from exc
        except Exception as exc:
            mark_source_error(source)
            raise FetchError(
                safe_error_message(f"authorized crawl failed: {exc}")
            ) from exc
        source.refresh_from_db()
        return FetchResult(
            source=source,
            city=city or "",
            category=category or "website",
            stats=stats,
            cursor_before={},
            cursor_after=None,
            quota_remaining_before=quota_before,
            quota_remaining_after=source.quota_remaining,
        )

    cursor_before: dict[str, Any] = {}
    if resume is not None:
        cursor_before = dict(resume)
    elif persist_cursor:
        existing = AcquisitionCursor.objects.filter(
            source=source, city=city.lower(), category=category
        ).first()
        if existing and existing.cursor_payload:
            cursor_before = dict(existing.cursor_payload)

    quota_before = source.quota_remaining
    source_query = f"{slug} city={city} category={category}"

    try:
        if slug == "openstreetmap":
            stats, next_cursor = _run_overpass(
                source=source,
                city=city,
                category=category,
                limit=limit,
                country=country,
                osm_tag=osm_tag,
                source_query=source_query,
            )
        else:
            search = _dispatch_search(
                slug,
                source=source,
                city=city,
                category=category,
                limit=limit,
                resume=cursor_before or None,
            )
            stats = ingest_candidates(
                search.candidates,
                source=source,
                city_hint=city,
                category_label=category,
                source_query=source_query,
                limit=limit,
            )
            next_cursor = search.next_cursor
    except FetchError:
        raise
    except Exception as exc:
        # Auth errors on TomTom should not mark ERROR (same as CLI).
        msg = safe_error_message(exc)
        if slug == "tomtom" and ("401" in msg or "Unauthorized" in msg):
            raise FetchError(safe_error_message(f"{slug} request failed: {exc}")) from exc
        mark_source_error(source)
        raise FetchError(safe_error_message(f"{slug} request failed: {exc}")) from exc

    if persist_cursor:
        _persist_cursor(source, city, category, next_cursor)

    source.refresh_from_db()
    return FetchResult(
        source=source,
        city=city,
        category=category,
        stats=stats,
        cursor_before=cursor_before,
        cursor_after=next_cursor,
        quota_remaining_before=quota_before,
        quota_remaining_after=source.quota_remaining,
    )


def _run_overpass(
    *,
    source: DataSource,
    city: str,
    category: str,
    limit: int,
    country: str,
    osm_tag: str | None,
    source_query: str,
) -> tuple[IngestStats, None]:
    try:
        tag_key, tag_value = resolve_category_tag(category, osm_tag)
    except ValueError as exc:
        raise FetchError(safe_error_message(exc)) from exc

    client = OverpassClient()
    try:
        bbox = client.resolve_city_bbox(city, country=country)
        pois = client.fetch_pois(bbox, tag_key, tag_value)
    except Exception as exc:
        raise FetchError(
            safe_error_message(f"Overpass/Nominatim failed: {exc}")
        ) from exc

    stats = ingest_pois(
        pois,
        source=source,
        city_hint=city,
        category_label=f"{tag_key}={tag_value}",
        source_query=source_query,
        limit=limit,
    )
    return stats, None


def _persist_cursor(
    source: DataSource,
    city: str,
    category: str,
    next_cursor: dict[str, Any] | None,
) -> None:
    key_city = city.lower()
    key_category = category.lower()
    if next_cursor:
        AcquisitionCursor.objects.update_or_create(
            source=source,
            city=key_city,
            category=key_category,
            defaults={"cursor_payload": next_cursor},
        )
    else:
        AcquisitionCursor.objects.filter(
            source=source, city=key_city, category=key_category
        ).delete()


def _dispatch_search(
    slug: str,
    *,
    source: DataSource,
    city: str,
    category: str,
    limit: int,
    resume: dict[str, Any] | None,
) -> ClientSearchResult:
    if slug == "geoapify":
        client = GeoapifyClient(source.get_api_key() or "")
        candidates = client.search(
            city=city, category=category, source=source, limit=limit
        )
        return ClientSearchResult(candidates=candidates, next_cursor=None)
    if slug == "locationiq":
        client = LocationIQClient(source.get_api_key() or "")
        candidates = client.search(
            city=city, category=category, source=source, limit=limit
        )
        return ClientSearchResult(candidates=candidates, next_cursor=None)
    if slug == "tomtom":
        client = TomTomClient(source.get_api_key() or "")
        candidates = client.search(
            city=city, category=category, source=source, limit=limit
        )
        return ClientSearchResult(candidates=candidates, next_cursor=None)
    if slug == "foursquare":
        client = FoursquareClient(source.get_api_key() or "")
        return client.search(
            city=city,
            category=category,
            source=source,
            limit=limit,
            resume=resume,
        )
    if slug == "google-places":
        client = GooglePlacesClient(source.get_api_key() or "")
        return client.search(
            city=city,
            category=category,
            source=source,
            limit=limit,
            resume=resume,
        )
    if slug == "yelp":
        yelp_cat = category if category.endswith("s") else category
        client = YelpClient(source.get_api_key() or "")
        return client.search(
            location=f"{city}, USA",
            categories=yelp_cat,
            source=source,
            limit=limit,
            resume=resume,
        )
    raise FetchError(f"Unsupported slug: {slug}")
