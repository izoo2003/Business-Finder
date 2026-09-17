import logging
import os

from django.db import models
from django.utils.text import slugify

logger = logging.getLogger("sources")


class DataSource(models.Model):
    """Source Registry entry for APIs and authorized websites."""

    class SourceType(models.TextChoices):
        API = "api", "API"
        WEBSITE = "website", "Website"

    class WindowType(models.TextChoices):
        DAILY = "daily", "Daily"
        MONTHLY = "monthly", "Monthly"
        PER_SKU = "per_sku", "Per SKU"
        SOFT = "soft", "Soft (politeness limits)"

    class QuotaStatus(models.TextChoices):
        HEALTHY = "healthy", "Healthy"
        LOW = "low", "Low"
        EXHAUSTED = "exhausted", "Exhausted"
        ERROR = "error", "Error"

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128, unique=True)
    source_type = models.CharField(
        max_length=16,
        choices=SourceType.choices,
        default=SourceType.API,
    )
    priority = models.PositiveIntegerField(
        default=100,
        help_text="Lower number = higher priority when scheduling.",
    )
    is_active = models.BooleanField(default=True)

    api_key_env_var = models.CharField(
        max_length=128,
        blank=True,
        help_text="Environment variable name that holds the API key (e.g. YELP_API_KEY).",
    )
    credential_notes = models.TextField(
        blank=True,
        help_text="How credentials are obtained; never store raw secrets here.",
    )
    api_key_ciphertext = models.TextField(
        blank=True,
        help_text="Fernet-encrypted API key pasted in the operator UI. Preferred over env.",
    )
    api_key_hint = models.CharField(
        max_length=4,
        blank=True,
        help_text="Last four characters of the stored key for display only.",
    )

    quota_max = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Max free calls/units in the current window. Null for soft-only sources.",
    )
    quota_remaining = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Remaining free calls/units after safety buffer accounting.",
    )
    window_type = models.CharField(
        max_length=16,
        choices=WindowType.choices,
        default=WindowType.DAILY,
    )
    quota_reset_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the current quota window resets.",
    )
    quota_refreshed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time quota counters were refreshed from headers or calculation.",
    )
    safety_buffer_percent = models.PositiveSmallIntegerField(
        default=10,
        help_text="Percent of quota_max left untouched (typically 5–10).",
    )
    quota_status = models.CharField(
        max_length=16,
        choices=QuotaStatus.choices,
        default=QuotaStatus.HEALTHY,
    )

    last_successful_run_at = models.DateTimeField(null=True, blank=True)
    allowed_params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Allowed query parameters (cities, categories, radius, pagination).",
    )
    data_quality_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "name"]
        verbose_name = "data source"
        verbose_name_plural = "data sources"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_api_key(self) -> str | None:
        """Prefer an operator-pasted encrypted key, then the environment variable."""
        if self.api_key_ciphertext:
            from sources.crypto import decrypt_api_key

            value = decrypt_api_key(self.api_key_ciphertext)
            if value:
                return value
            logger.warning("Stored API key for %s could not be decrypted", self.slug)

        if not self.api_key_env_var:
            return None
        value = os.environ.get(self.api_key_env_var, "").strip()
        return value or None

    def key_origin(self) -> str:
        """Where the live key comes from: stored, env, or missing."""
        if self.api_key_ciphertext and self.get_api_key():
            return "stored"
        if self.api_key_env_var and os.environ.get(self.api_key_env_var, "").strip():
            return "env"
        if self.get_api_key():
            return "stored"
        return "missing"
