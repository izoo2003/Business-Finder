"""Select next eligible acquisition source and city/category target."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from acquisition.models import (
    AcquisitionCursor,
    AcquisitionDecision,
    HarvestRun,
    OrchestrationState,
)
from acquisition.runner import (
    ACQUISITION_SLUGS,
    MIN_CALLS,
    FetchError,
    FetchResult,
    run_source_fetch,
)
from acquisition.secrets_safe import safe_error_message
from sources.models import DataSource
from sources.quota import ensure_quota_reset, preflight_ok

logger = logging.getLogger("acquisition")

EXCLUDED_SLUGS = frozenset({"dialcode"})


@dataclass
class CyclePlan:
    source: DataSource | None
    city: str
    category: str
    reason: str = ""
    skipped: list[dict] = field(default_factory=list)


def orchestration_cities() -> list[str]:
    state = OrchestrationState.get_solo()
    stored = state.cities if isinstance(state.cities, list) else []
    cleaned = [str(c).strip() for c in stored if str(c).strip()]
    if cleaned:
        return cleaned
    raw = getattr(settings, "ORCHESTRATION_CITIES", None)
    if isinstance(raw, (list, tuple)) and raw:
        return [str(c).strip() for c in raw if str(c).strip()]
    return ["Austin", "Dallas", "Houston", "San Antonio"]


def orchestration_categories() -> list[str]:
    state = OrchestrationState.get_solo()
    stored = state.categories if isinstance(state.categories, list) else []
    cleaned = [str(c).strip().lower() for c in stored if str(c).strip()]
    if cleaned:
        return cleaned
    raw = getattr(settings, "ORCHESTRATION_CATEGORIES", None)
    if isinstance(raw, (list, tuple)) and raw:
        return [str(c).strip().lower() for c in raw if str(c).strip()]
    return ["restaurant", "cafe"]


def orchestration_limit() -> int:
    return int(getattr(settings, "ORCHESTRATION_LIMIT", 25))


def evaluate_sources() -> tuple[list[DataSource], list[dict]]:
    """Return (eligible sources, skipped [{slug, reason}])."""
    sources = list(
        DataSource.objects.filter(is_active=True, slug__in=ACQUISITION_SLUGS)
        .exclude(slug__in=EXCLUDED_SLUGS)
        # Rotate: least-recently successful first (never-run ahead), then quality priority.
        .order_by(F("last_successful_run_at").asc(nulls_first=True), "priority", "id")
    )
    # Also record inactive acquisition sources that were considered out of rotation.
    inactive = DataSource.objects.filter(
        is_active=False, slug__in=ACQUISITION_SLUGS
    ).exclude(slug__in=EXCLUDED_SLUGS)
    skipped: list[dict] = [
        {"slug": s.slug, "reason": "source is inactive"} for s in inactive
    ]

    eligible: list[DataSource] = []
    for source in sources:
        ensure_quota_reset(source)
        source.refresh_from_db()
        ok, reason = preflight_ok(source, min_calls=MIN_CALLS.get(source.slug, 1))
        if not ok:
            logger.info("Skip %s: %s", source.slug, reason)
            skipped.append({"slug": source.slug, "reason": reason})
            continue
        if source.slug != "openstreetmap" and source.api_key_env_var and not source.get_api_key():
            reason = "missing API key"
            logger.info("Skip %s: %s", source.slug, reason)
            skipped.append({"slug": source.slug, "reason": reason})
            continue
        eligible.append(source)
    return eligible, skipped


def eligible_sources() -> list[DataSource]:
    eligible, _ = evaluate_sources()
    return eligible


def next_city_category(*, advance: bool = True) -> tuple[str, str]:
    cities = orchestration_cities()
    categories = orchestration_categories()
    state = OrchestrationState.get_solo()
    city = cities[state.city_index % len(cities)]
    category = categories[state.category_index % len(categories)]
    if advance:
        next_cat = state.category_index + 1
        next_city = state.city_index
        if next_cat >= len(categories):
            next_cat = 0
            next_city = (state.city_index + 1) % len(cities)
        state.category_index = next_cat
        state.city_index = next_city
        state.save(update_fields=["city_index", "category_index", "updated_at"])
    return city, category


def plan_cycle(*, advance_rotation: bool = True) -> CyclePlan:
    city, category = next_city_category(advance=advance_rotation)
    sources, skipped = evaluate_sources()
    if not sources:
        return CyclePlan(
            source=None,
            city=city,
            category=category,
            reason="no eligible acquisition sources (inactive, exhausted, error, or missing key)",
            skipped=skipped,
        )
    return CyclePlan(
        source=sources[0],
        city=city,
        category=category,
        reason="ok",
        skipped=skipped,
    )


def _record_decision(
    *,
    plan: CyclePlan,
    outcome: str,
    harvest_run: HarvestRun | None = None,
    notes: str = "",
) -> AcquisitionDecision:
    return AcquisitionDecision.objects.create(
        chosen_source=plan.source,
        city=plan.city,
        category=plan.category,
        outcome=outcome,
        skipped=plan.skipped or [],
        harvest_run=harvest_run,
        notes=notes or plan.reason or "",
    )


def scraper_is_enabled() -> bool:
    return bool(OrchestrationState.get_solo().scraper_enabled)


def execute_cycle(
    *,
    dry_run: bool = False,
    limit: int | None = None,
    force: bool = False,
) -> HarvestRun:
    """
    One orchestration tick: pick source + target, optionally fetch, write HarvestRun.
    dry_run plans without advancing rotation or calling APIs.
    When the operator Stop button is used, Beat ticks no-op unless force=True (CLI).
    """
    started = timezone.now()
    if not dry_run and not force and not scraper_is_enabled():
        return HarvestRun(
            source=None,
            city="",
            category="",
            started_at=started,
            finished_at=timezone.now(),
            status=HarvestRun.Status.SKIPPED,
            error="scraper is stopped",
        )

    plan = plan_cycle(advance_rotation=not dry_run)

    if dry_run:
        return HarvestRun(
            source=plan.source,
            city=plan.city,
            category=plan.category,
            started_at=started,
            finished_at=timezone.now(),
            status=HarvestRun.Status.SKIPPED if not plan.source else HarvestRun.Status.SUCCESS,
            error=plan.reason if not plan.source else "dry_run",
        )

    if not plan.source:
        run = HarvestRun.objects.create(
            source=None,
            city=plan.city,
            category=plan.category,
            started_at=started,
            finished_at=timezone.now(),
            status=HarvestRun.Status.SKIPPED,
            error=plan.reason,
        )
        _record_decision(
            plan=plan,
            outcome=AcquisitionDecision.Outcome.SKIPPED_CYCLE,
            harvest_run=run,
            notes=plan.reason,
        )
        logger.info("Acquisition cycle skipped: %s", plan.reason)
        return run

    _record_decision(plan=plan, outcome=AcquisitionDecision.Outcome.SELECTED)

    run_limit = limit if limit is not None else orchestration_limit()
    quota_before = plan.source.quota_remaining
    cursor_before: dict = {}

    existing = AcquisitionCursor.objects.filter(
        source=plan.source,
        city=plan.city.lower(),
        category=plan.category.lower(),
    ).first()
    if existing:
        cursor_before = dict(existing.cursor_payload or {})

    try:
        result: FetchResult = run_source_fetch(
            plan.source.slug,
            city=plan.city,
            category=plan.category,
            limit=run_limit,
            persist_cursor=True,
        )
    except FetchError as exc:
        plan.source.refresh_from_db()
        run = HarvestRun.objects.create(
            source=plan.source,
            city=plan.city,
            category=plan.category,
            started_at=started,
            finished_at=timezone.now(),
            status=HarvestRun.Status.FAILED,
            quota_remaining_before=quota_before,
            quota_remaining_after=plan.source.quota_remaining,
            cursor_before=cursor_before,
            error=safe_error_message(exc, max_len=4000),
        )
        _record_decision(
            plan=plan,
            outcome=AcquisitionDecision.Outcome.FAILED,
            harvest_run=run,
            notes=safe_error_message(exc, max_len=2000),
        )
        logger.exception("Acquisition cycle failed for %s", plan.source.slug)
        return run

    stats = result.stats
    run = HarvestRun.objects.create(
        source=result.source,
        city=result.city,
        category=result.category,
        started_at=started,
        finished_at=timezone.now(),
        status=HarvestRun.Status.SUCCESS,
        fetched=stats.fetched,
        saved=stats.saved,
        updated=stats.updated,
        skipped_invalid=stats.skipped,
        quota_remaining_before=result.quota_remaining_before,
        quota_remaining_after=result.quota_remaining_after,
        cursor_before=result.cursor_before or {},
        cursor_after=result.cursor_after or {},
    )
    _record_decision(
        plan=plan,
        outcome=AcquisitionDecision.Outcome.RAN,
        harvest_run=run,
        notes=f"saved={stats.saved} updated={stats.updated}",
    )
    logger.info(
        "Acquisition cycle ok source=%s city=%s category=%s saved=%s updated=%s",
        result.source.slug,
        result.city,
        result.category,
        stats.saved,
        stats.updated,
    )
    return run
