from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from acquisition.scheduler import evaluate_sources, plan_cycle
from sources.models import DataSource


class SourceRotationTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.geo = DataSource.objects.create(
            name="Geoapify Places",
            slug="geoapify",
            priority=12,
            is_active=True,
            api_key_env_var="GEOAPIFY_API_KEY",
            quota_max=3000,
            quota_remaining=2900,
            window_type=DataSource.WindowType.DAILY,
            last_successful_run_at=now,
        )
        self.liq = DataSource.objects.create(
            name="LocationIQ",
            slug="locationiq",
            priority=15,
            is_active=True,
            api_key_env_var="LOCATIONIQ_API_KEY",
            quota_max=5000,
            quota_remaining=5000,
            window_type=DataSource.WindowType.DAILY,
            last_successful_run_at=now - timedelta(days=1),
        )
        self.fsq = DataSource.objects.create(
            name="Foursquare Places",
            slug="foursquare",
            priority=30,
            is_active=True,
            api_key_env_var="FOURSQUARE_API_KEY",
            quota_max=500,
            quota_remaining=500,
            window_type=DataSource.WindowType.MONTHLY,
            last_successful_run_at=None,
        )

    def test_never_run_source_selected_before_recent_geoapify(self):
        with (
            self.settings(
                # Ensure env keys resolve for get_api_key during evaluate
            ),
        ):
            # Patch get_api_key via ciphertext-free env
            import os

            os.environ["GEOAPIFY_API_KEY"] = "geo-test-key"
            os.environ["LOCATIONIQ_API_KEY"] = "liq-test-key"
            os.environ["FOURSQUARE_API_KEY"] = "fsq-test-key"

            eligible, _ = evaluate_sources()
            self.assertEqual(
                [s.slug for s in eligible],
                ["foursquare", "locationiq", "geoapify"],
            )
            plan = plan_cycle(advance_rotation=False)
            self.assertEqual(plan.source.slug, "foursquare")
