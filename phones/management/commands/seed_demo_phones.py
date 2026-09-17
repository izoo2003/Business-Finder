from django.core.management.base import BaseCommand
from django.utils import timezone

from phones.models import PhoneRecord
from sources.models import DataSource


DEMO_PHONES = [
    {
        "e164": "+15125550101",
        "national_format": "(512) 555-0101",
        "raw_phone": "512-555-0101",
        "area_code": "512",
        "state": "TX",
        "business_name": "Demo Taco House",
        "address": "100 Congress Ave",
        "city": "Austin",
        "postal_code": "78701",
        "category": "restaurant",
        "source_query": "demo seed: restaurants in Austin",
        "raw_payload": {"demo": True, "note": "Phase 2 sample record"},
    },
    {
        "e164": "+15125550102",
        "national_format": "(512) 555-0102",
        "raw_phone": "(512) 555-0102 ext 12",
        "area_code": "512",
        "state": "TX",
        "business_name": "Demo Plumbing Co",
        "address": "200 Lamar Blvd",
        "city": "Austin",
        "postal_code": "78704",
        "category": "plumber",
        "source_query": "demo seed: plumbers in Austin",
        "raw_payload": {"demo": True, "note": "Phase 2 sample record"},
    },
    {
        "e164": "+12125550103",
        "national_format": "(212) 555-0103",
        "raw_phone": "+1 212 555 0103",
        "area_code": "212",
        "state": "NY",
        "business_name": "Demo Dental Clinic",
        "address": "350 5th Ave",
        "city": "New York",
        "postal_code": "10118",
        "category": "dentist",
        "source_query": "demo seed: dentists in New York",
        "raw_payload": {"demo": True, "note": "Phase 2 sample record"},
    },
]


class Command(BaseCommand):
    help = "Insert a few demo PhoneRecord rows linked to OpenStreetMap for Phase 2 verification."

    def handle(self, *args, **options):
        try:
            source = DataSource.objects.get(slug="openstreetmap")
        except DataSource.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    "OpenStreetMap source not found. Run: python manage.py seed_sources"
                )
            )
            return

        now = timezone.now()
        created_count = 0
        skipped_count = 0

        for payload in DEMO_PHONES:
            defaults = {
                **payload,
                "source": source,
                "validation_status": PhoneRecord.ValidationStatus.PENDING,
                "first_seen_at": now,
                "last_seen_at": now,
            }
            obj, created = PhoneRecord.objects.get_or_create(
                e164=payload["e164"],
                defaults=defaults,
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created: {obj}"))
            else:
                skipped_count += 1
                self.stdout.write(self.style.WARNING(f"Already exists: {obj.e164}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {created_count}, skipped {skipped_count}. "
                f"Total phone records: {PhoneRecord.objects.count()}."
            )
        )
