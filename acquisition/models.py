"""Acquisition orchestration models (Phase 7)."""

from django.db import models
from django.utils import timezone


class AcquisitionCursor(models.Model):
    """Persisted pagination state for a source + city + category query."""

    source = models.ForeignKey(
        "sources.DataSource",
        on_delete=models.CASCADE,
        related_name="acquisition_cursors",
    )
    city = models.CharField(max_length=128)
    category = models.CharField(max_length=128)
    cursor_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text='e.g. {"offset": 50} or {"page_token": "..."}',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "acquisition cursor"
        verbose_name_plural = "acquisition cursors"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "city", "category"],
                name="acquisition_cursor_source_city_category_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source.slug} {self.city}/{self.category}"


class HarvestRun(models.Model):
    """Per-cycle acquisition metrics for health / quota burn visibility."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    source = models.ForeignKey(
        "sources.DataSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="harvest_runs",
    )
    city = models.CharField(max_length=128, blank=True)
    category = models.CharField(max_length=128, blank=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SUCCESS,
        db_index=True,
    )
    fetched = models.PositiveIntegerField(default=0)
    saved = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    skipped_invalid = models.PositiveIntegerField(default=0)
    quota_remaining_before = models.PositiveIntegerField(null=True, blank=True)
    quota_remaining_after = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    cursor_before = models.JSONField(default=dict, blank=True)
    cursor_after = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "harvest run"
        verbose_name_plural = "harvest runs"
        indexes = [
            models.Index(fields=["started_at", "status"], name="harvest_started_status_idx"),
        ]

    def __str__(self) -> str:
        slug = self.source.slug if self.source_id else "none"
        return f"{self.status} {slug} {self.city}/{self.category} @ {self.started_at}"


class AcquisitionDecision(models.Model):
    """Audit log for each orchestration tick (selected + skipped sources)."""

    class Outcome(models.TextChoices):
        SELECTED = "selected", "Selected"
        SKIPPED_CYCLE = "skipped_cycle", "Skipped cycle"
        RAN = "ran", "Ran"
        FAILED = "failed", "Failed"

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    chosen_source = models.ForeignKey(
        "sources.DataSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acquisition_decisions",
    )
    city = models.CharField(max_length=128, blank=True)
    category = models.CharField(max_length=128, blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, db_index=True)
    skipped = models.JSONField(
        default=list,
        blank=True,
        help_text='List of {"slug": "...", "reason": "..."} for ineligible sources.',
    )
    harvest_run = models.ForeignKey(
        HarvestRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decisions",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "acquisition decision"
        verbose_name_plural = "acquisition decisions"

    def __str__(self) -> str:
        slug = self.chosen_source.slug if self.chosen_source_id else "none"
        return f"{self.outcome} {slug} {self.city}/{self.category} @ {self.created_at}"


class OrchestrationState(models.Model):
    """Singleton round-robin pointers for city/category rotation."""

    singleton_id = models.PositiveSmallIntegerField(default=1, unique=True)
    city_index = models.PositiveIntegerField(default=0)
    category_index = models.PositiveIntegerField(default=0)
    cities = models.JSONField(
        default=list,
        blank=True,
        help_text="US cities to rotate through. Edited from the Scraper UI.",
    )
    categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Business types to rotate through. Edited from the Scraper UI.",
    )
    scraper_enabled = models.BooleanField(
        default=False,
        help_text="When False, Beat and the loop task do not collect. Start/Stop from the UI.",
    )
    session_started_at = models.DateTimeField(null=True, blank=True)
    session_saved = models.PositiveIntegerField(default=0)
    session_updated = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "orchestration state"
        verbose_name_plural = "orchestration state"

    def __str__(self) -> str:
        running = "on" if self.scraper_enabled else "off"
        return f"{running} city_idx={self.city_index} category_idx={self.category_index}"

    @classmethod
    def get_solo(cls) -> "OrchestrationState":
        obj, _ = cls.objects.get_or_create(singleton_id=1)
        return obj
