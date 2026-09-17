from django.core.management.base import BaseCommand

from sources.models import DataSource


DEFAULT_SOURCES = [
    {
        "name": "Yelp Fusion",
        "slug": "yelp",
        "source_type": DataSource.SourceType.API,
        "priority": 10,
        "is_active": False,
        "api_key_env_var": "YELP_API_KEY",
        "credential_notes": "Set YELP_API_KEY in .env. Currently inactive — use Geoapify/TomTom/LocationIQ.",
        "quota_max": 500,
        "quota_remaining": 500,
        "window_type": DataSource.WindowType.DAILY,
        "safety_buffer_percent": 10,
        "quota_status": DataSource.QuotaStatus.HEALTHY,
        "allowed_params": {
            "location": True,
            "categories": True,
            "radius": True,
            "pagination": "offset",
        },
        "data_quality_notes": "High-quality structured business records (optional if key works).",
    },
    {
        "name": "Geoapify Places",
        "slug": "geoapify",
        "source_type": DataSource.SourceType.API,
        "priority": 12,
        "is_active": True,
        "api_key_env_var": "GEOAPIFY_API_KEY",
        "credential_notes": "Set GEOAPIFY_API_KEY in .env.",
        "quota_max": 3000,
        "quota_remaining": 3000,
        "window_type": DataSource.WindowType.DAILY,
        "safety_buffer_percent": 10,
        "quota_status": DataSource.QuotaStatus.HEALTHY,
        "allowed_params": {"categories": True, "circle": True},
        "data_quality_notes": "Places + optional place-details for phone/contact.",
    },
    {
        "name": "LocationIQ",
        "slug": "locationiq",
        "source_type": DataSource.SourceType.API,
        "priority": 15,
        "is_active": True,
        "api_key_env_var": "LOCATIONIQ_API_KEY",
        "credential_notes": "Set LOCATIONIQ_API_KEY in .env.",
        "quota_max": 5000,
        "quota_remaining": 5000,
        "window_type": DataSource.WindowType.DAILY,
        "safety_buffer_percent": 10,
        "quota_status": DataSource.QuotaStatus.HEALTHY,
        "allowed_params": {"nearby": True, "tag": True},
        "data_quality_notes": "OSM-backed nearby search; phone coverage varies.",
    },
    {
        "name": "TomTom Search",
        "slug": "tomtom",
        "source_type": DataSource.SourceType.API,
        "priority": 18,
        "is_active": True,
        "api_key_env_var": "MYTOMTOM_API_KEY",
        "credential_notes": "Set MYTOMTOM_API_KEY in .env (TomTom developer key).",
        "quota_max": 2500,
        "quota_remaining": 2500,
        "window_type": DataSource.WindowType.DAILY,
        "safety_buffer_percent": 10,
        "quota_status": DataSource.QuotaStatus.HEALTHY,
        "allowed_params": {"poiSearch": True, "countrySet": "US"},
        "data_quality_notes": "POI search often includes phone numbers.",
    },
    {
        "name": "Google Places",
        "slug": "google-places",
        "source_type": DataSource.SourceType.API,
        "priority": 20,
        "is_active": False,
        "api_key_env_var": "GOOGLE_PLACES_API_KEY",
        "credential_notes": "Inactive — not used by Phone Desk. Prefer Geoapify/TomTom/LocationIQ/Foursquare.",
        "quota_max": 1000,
        "quota_remaining": 1000,
        "window_type": DataSource.WindowType.PER_SKU,
        "safety_buffer_percent": 10,
        "quota_status": DataSource.QuotaStatus.HEALTHY,
        "allowed_params": {
            "text_search": True,
            "nearby_search": True,
            "place_details": True,
            "pagination": "next_page_token",
        },
        "data_quality_notes": "Highest completeness; phone/contact often higher-cost SKUs.",
    },
    {
        "name": "Foursquare Places",
        "slug": "foursquare",
        "source_type": DataSource.SourceType.API,
        "priority": 30,
        "api_key_env_var": "FOURSQUARE_API_KEY",
        "credential_notes": "Set FOURSQUARE_API_KEY (Service/Server key) in .env.",
        "quota_max": 500,
        "quota_remaining": 500,
        "window_type": DataSource.WindowType.MONTHLY,
        "safety_buffer_percent": 10,
        "quota_status": DataSource.QuotaStatus.HEALTHY,
        "allowed_params": {
            "near": True,
            "categories": True,
            "pagination": "cursor",
        },
        "data_quality_notes": "Similar to Yelp; phones often on Pro endpoints.",
    },
    {
        "name": "OpenStreetMap / Overpass",
        "slug": "openstreetmap",
        "source_type": DataSource.SourceType.API,
        "priority": 40,
        "api_key_env_var": "",
        "credential_notes": "No API key required. Respect public instance politeness limits.",
        "quota_max": None,
        "quota_remaining": None,
        "window_type": DataSource.WindowType.SOFT,
        "safety_buffer_percent": 0,
        "quota_status": DataSource.QuotaStatus.HEALTHY,
        "allowed_params": {
            "area": True,
            "tags": ["phone", "contact:phone"],
            "amenities": True,
            "shops": True,
        },
        "data_quality_notes": "Free high-volume source; phone coverage incomplete but usable.",
    },
    {
        "name": "DialCode",
        "slug": "dialcode",
        "source_type": DataSource.SourceType.API,
        "priority": 90,
        "is_active": True,
        "api_key_env_var": "DIALCODE_API_KEY",
        "credential_notes": (
            "Set DIALCODE_API_KEY in .env (free key at dialcode.app). "
            "Enrichment only — not used for acquisition."
        ),
        "quota_max": 1000,
        "quota_remaining": 1000,
        "window_type": DataSource.WindowType.MONTHLY,
        "safety_buffer_percent": 10,
        "quota_status": DataSource.QuotaStatus.HEALTHY,
        "allowed_params": {"phone_lookup": True},
        "data_quality_notes": (
            "Free 1k lookups/month: line type, risk/scam signals, geography. "
            "US carrier often null (NANP)."
        ),
    },
]


class Command(BaseCommand):
    help = "Seed API data sources into the Source Registry."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for payload in DEFAULT_SOURCES:
            obj, created = DataSource.objects.update_or_create(
                slug=payload["slug"],
                defaults=payload,
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created: {obj.name}"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"Updated: {obj.name}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {created_count}, updated {updated_count}. "
                f"Total sources: {DataSource.objects.count()}."
            )
        )
