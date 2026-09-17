from django.db import models
from django.utils import timezone


class PhoneRecord(models.Model):
    """Permanent storage for a unique US business phone number with provenance."""

    class ValidationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VALID = "valid", "Valid"
        INVALID = "invalid", "Invalid"

    class EnrichmentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        OFFLINE_ONLY = "offline_only", "Offline only"
        ENRICHED = "enriched", "Enriched"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    e164 = models.CharField(
        max_length=16,
        unique=True,
        help_text="Normalized international format, e.g. +15125551234.",
    )
    national_format = models.CharField(
        max_length=32,
        blank=True,
        help_text="National display format, e.g. (512) 555-1234.",
    )
    raw_phone = models.CharField(
        max_length=64,
        blank=True,
        help_text="Original phone text as received from the source.",
    )
    area_code = models.CharField(max_length=3, blank=True, db_index=True)
    state = models.CharField(max_length=2, blank=True, db_index=True)

    business_name = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=512, blank=True)
    city = models.CharField(max_length=128, blank=True, db_index=True)
    postal_code = models.CharField(max_length=16, blank=True)
    category = models.CharField(max_length=128, blank=True)

    source = models.ForeignKey(
        "sources.DataSource",
        on_delete=models.PROTECT,
        related_name="phone_records",
    )
    source_record_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="Provider-specific place/POI id when available.",
    )
    source_url = models.URLField(blank=True, max_length=1024)
    source_query = models.CharField(
        max_length=512,
        blank=True,
        help_text="Query or page that produced this record.",
    )
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Original source payload for audit.",
    )

    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    validation_status = models.CharField(
        max_length=16,
        choices=ValidationStatus.choices,
        default=ValidationStatus.PENDING,
        db_index=True,
    )

    enrichment_status = models.CharField(
        max_length=16,
        choices=EnrichmentStatus.choices,
        default=EnrichmentStatus.PENDING,
        db_index=True,
    )
    line_type = models.CharField(
        max_length=32,
        blank=True,
        help_text="e.g. mobile, fixed_line, toll_free, voip, unknown.",
    )
    carrier = models.CharField(
        max_length=128,
        blank=True,
        help_text="Often empty for US NANP from DialCode.",
    )
    risk_level = models.CharField(
        max_length=32,
        blank=True,
        help_text="Mapped from DialCode risk.scam_risk.",
    )
    risk_signals = models.JSONField(default=list, blank=True)
    enrichment_geo = models.CharField(
        max_length=255,
        blank=True,
        help_text="Confirmed geography hints (area name, timezone).",
    )
    enriched_at = models.DateTimeField(null=True, blank=True)
    enrichment_raw = models.JSONField(
        default=dict,
        blank=True,
        help_text="DialCode (or other) enrichment payload for audit.",
    )
    enrichment_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at", "e164"]
        verbose_name = "phone record"
        verbose_name_plural = "phone records"
        indexes = [
            models.Index(fields=["e164"], name="phones_e164_idx"),
            models.Index(fields=["area_code", "state"], name="phones_area_state_idx"),
            models.Index(fields=["source", "last_seen_at"], name="phones_source_seen_idx"),
        ]

    def __str__(self) -> str:
        label = self.business_name or "Unknown business"
        return f"{self.e164} - {label}"

    def save(self, *args, **kwargs):
        if self.pk is None and self.first_seen_at is None:
            self.first_seen_at = timezone.now()
        if self.last_seen_at is None:
            self.last_seen_at = timezone.now()
        super().save(*args, **kwargs)
