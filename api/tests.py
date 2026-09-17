from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from acquisition.models import OrchestrationState
from phones.models import PhoneRecord
from sources.crypto import decrypt_api_key, encrypt_api_key, last4
from sources.key_rotation import rotate_api_key
from sources.models import DataSource


User = get_user_model()


class OperatorApiTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="operator",
            password="pass-word-12",
            is_staff=True,
        )
        self.regular = User.objects.create_user(
            username="visitor",
            password="pass-word-12",
            is_staff=False,
        )
        self.source = DataSource.objects.create(
            name="Geoapify Places",
            slug="geoapify",
            api_key_env_var="GEOAPIFY_API_KEY",
            quota_max=3000,
            quota_remaining=10,
            quota_status=DataSource.QuotaStatus.EXHAUSTED,
            window_type=DataSource.WindowType.DAILY,
        )
        self.osm = DataSource.objects.create(
            name="OpenStreetMap / Overpass",
            slug="openstreetmap",
            api_key_env_var="",
            window_type=DataSource.WindowType.SOFT,
        )
        PhoneRecord.objects.create(
            e164="+15125550100",
            national_format="(512) 555-0100",
            business_name="Test Cafe",
            city="Austin",
            state="TX",
            category="cafe",
            source=self.source,
            validation_status=PhoneRecord.ValidationStatus.VALID,
        )

    def test_login_requires_staff(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "visitor", "password": "pass-word-12"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_login_and_me(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "operator", "password": "pass-word-12"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["username"], "operator")

    def test_phones_require_auth(self):
        response = self.client.get("/api/phones/")
        self.assertEqual(response.status_code, 403)

    def test_phone_list_and_detail(self):
        self.client.force_login(self.staff)
        listing = self.client.get("/api/phones/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        row = listing.data["results"][0]
        self.assertEqual(row["business"], "Test Cafe")
        self.assertEqual(row["state"], "TX")
        detail = self.client.get(f"/api/phones/{row['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["city"], "Austin")
        self.assertNotIn("raw_payload", detail.data)

    def test_get_api_key_prefers_ciphertext(self):
        self.source.api_key_ciphertext = encrypt_api_key("stored-key-9999")
        self.source.save(update_fields=["api_key_ciphertext"])
        with patch.dict("os.environ", {"GEOAPIFY_API_KEY": "env-key-0000"}):
            self.assertEqual(self.source.get_api_key(), "stored-key-9999")

    def test_rotate_key_resets_quota(self):
        with patch("sources.key_rotation.verify_api_key", return_value=(True, "ok")):
            result = rotate_api_key(self.source, "brand-new-key-1234", verify=True)
        self.source.refresh_from_db()
        self.assertTrue(result["verified"])
        self.assertEqual(decrypt_api_key(self.source.api_key_ciphertext), "brand-new-key-1234")
        self.assertEqual(self.source.api_key_hint, last4("brand-new-key-1234"))
        self.assertEqual(self.source.quota_remaining, 3000)
        self.assertEqual(self.source.quota_status, DataSource.QuotaStatus.HEALTHY)
        self.assertTrue(self.source.is_active)

    def test_rotate_endpoint(self):
        self.client.force_login(self.staff)
        with patch("sources.key_rotation.verify_api_key", return_value=(True, "ok")):
            response = self.client.post(
                "/api/keys/geoapify/",
                {"api_key": "pasted-key-abcd"},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["has_key"])
        self.assertEqual(response.data["key_hint"], "abcd")
        self.assertNotIn("api_key", response.data)
        self.assertNotIn("ciphertext", str(response.data).lower())

    def test_keys_page_hides_google_places(self):
        DataSource.objects.create(
            name="Google Places",
            slug="google-places",
            api_key_env_var="GOOGLE_PLACES_API_KEY",
            priority=20,
        )
        self.client.force_login(self.staff)
        response = self.client.get("/api/keys/")
        self.assertEqual(response.status_code, 200)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertNotIn("google-places", slugs)
        self.assertIn("geoapify", slugs)

    def test_keys_connection_labels(self):
        DataSource.objects.create(
            name="Foursquare Places",
            slug="foursquare",
            api_key_env_var="FOURSQUARE_API_KEY",
            priority=30,
        )
        DataSource.objects.create(
            name="DialCode",
            slug="dialcode",
            api_key_env_var="DIALCODE_API_KEY",
            priority=90,
        )
        self.source.api_key_ciphertext = encrypt_api_key("geo-live-key-a7b5")
        self.source.save(update_fields=["api_key_ciphertext"])

        self.client.force_login(self.staff)
        with patch.dict("os.environ", {"FOURSQUARE_API_KEY": "fsq-test-key-xxxx"}, clear=False):
            response = self.client.get("/api/keys/")
        self.assertEqual(response.status_code, 200)
        by_slug = {row["slug"]: row for row in response.data["results"]}
        self.assertTrue(by_slug["geoapify"]["connected"])
        self.assertEqual(by_slug["geoapify"]["connection_label"], "Connected")
        self.assertTrue(by_slug["foursquare"]["connected"])
        self.assertTrue(by_slug["openstreetmap"]["connected"])
        self.assertFalse(by_slug["dialcode"]["connected"])
        self.assertEqual(by_slug["dialcode"]["connection_label"], "Not connected")

    def test_rotate_makes_pasted_key_live_over_env(self):
        """Pasted Keys-page value must be what acquisition clients use."""
        self.client.force_login(self.staff)
        with (
            patch("sources.key_rotation.verify_api_key", return_value=(True, "ok")),
            patch.dict("os.environ", {"GEOAPIFY_API_KEY": "old-env-key-0000"}),
        ):
            response = self.client.post(
                "/api/keys/geoapify/",
                {"api_key": "brand-new-pasted-9999"},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.source.refresh_from_db()
            self.assertEqual(self.source.get_api_key(), "brand-new-pasted-9999")
            self.assertEqual(self.source.key_origin(), "stored")
            self.assertEqual(response.data["key_origin"], "stored")
            self.assertEqual(response.data["key_hint"], "9999")

    def test_osm_rejects_key(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            "/api/keys/openstreetmap/",
            {"api_key": "should-not-work"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_scraper_start_stop(self):
        self.client.force_login(self.staff)
        with (
            patch("acquisition.tasks.run_scraper_loop.delay") as delay,
            patch("acquisition.scraper_control.worker_online", return_value=True),
            patch("acquisition.scraper_control.redis_online", return_value=True),
        ):
            start = self.client.post("/api/scraper/start/", format="json")
            delay.assert_called_once()
        self.assertEqual(start.status_code, 200)
        self.assertTrue(start.data["running"])
        self.assertTrue(OrchestrationState.get_solo().scraper_enabled)

        with (
            patch("acquisition.scraper_control.worker_online", return_value=True),
            patch("acquisition.scraper_control.redis_online", return_value=True),
        ):
            stop = self.client.post("/api/scraper/stop/", format="json")
        self.assertEqual(stop.status_code, 200)
        self.assertFalse(stop.data["running"])
        self.assertFalse(OrchestrationState.get_solo().scraper_enabled)

    def test_orchestration_filters_update_and_status(self):
        from acquisition.scheduler import orchestration_categories, orchestration_cities

        self.client.force_login(self.staff)
        with (
            patch("acquisition.scraper_control.worker_online", return_value=True),
            patch("acquisition.scraper_control.redis_online", return_value=True),
        ):
            response = self.client.put(
                "/api/scraper/orchestration/",
                {
                    "cities": ["Chicago", " Miami ", "Chicago"],
                    "categories": ["Pharmacy", "hotel", "pharmacy"],
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cities"], ["Chicago", "Miami"])
        self.assertEqual(response.data["categories"], ["pharmacy", "hotel"])

        state = OrchestrationState.get_solo()
        self.assertEqual(state.cities, ["Chicago", "Miami"])
        self.assertEqual(state.categories, ["pharmacy", "hotel"])
        self.assertEqual(orchestration_cities(), ["Chicago", "Miami"])
        self.assertEqual(orchestration_categories(), ["pharmacy", "hotel"])

        with (
            patch("acquisition.scraper_control.worker_online", return_value=True),
            patch("acquisition.scraper_control.redis_online", return_value=True),
        ):
            status = self.client.get("/api/scraper/status/")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.data["cities"], ["Chicago", "Miami"])
        self.assertEqual(status.data["categories"], ["pharmacy", "hotel"])

    def test_orchestration_rejects_empty_lists(self):
        self.client.force_login(self.staff)
        response = self.client.put(
            "/api/scraper/orchestration/",
            {"cities": [], "categories": ["cafe"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("city", response.data["detail"].lower())

        response = self.client.put(
            "/api/scraper/orchestration/",
            {"cities": ["Austin"], "categories": []},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("business", response.data["detail"].lower())

    def test_usage_plain_english(self):
        self.client.force_login(self.staff)
        response = self.client.get("/api/usage/")
        self.assertEqual(response.status_code, 200)
        slugs = {row["slug"] for row in response.data["sources"]}
        self.assertIn("geoapify", slugs)
        geo = next(row for row in response.data["sources"] if row["slug"] == "geoapify")
        self.assertIn("free lookups", geo["plain_english"])
