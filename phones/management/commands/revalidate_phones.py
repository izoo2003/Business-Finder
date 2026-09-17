from django.core.management.base import BaseCommand

from phones.models import PhoneRecord
from phones.normalization import normalize_us_phone


class Command(BaseCommand):
    help = (
        "Re-run Phase 4 normalization on existing PhoneRecords. "
        "Valid numbers get national_format/area_code/state/valid; "
        "failures are marked invalid (rows kept for audit)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-pending",
            action="store_true",
            help="Only process records with validation_status=pending",
        )

    def handle(self, *args, **options):
        qs = PhoneRecord.objects.all().order_by("id")
        if options["only_pending"]:
            qs = qs.filter(validation_status=PhoneRecord.ValidationStatus.PENDING)

        total = qs.count()
        valid_count = 0
        invalid_count = 0
        unchanged_e164 = 0

        self.stdout.write(f"Revalidating {total} phone record(s)...")

        for record in qs.iterator():
            raw = (record.raw_phone or "").strip() or record.e164
            result = normalize_us_phone(raw)
            if result is None and record.e164:
                result = normalize_us_phone(record.e164)

            if result is None:
                record.validation_status = PhoneRecord.ValidationStatus.INVALID
                record.save(update_fields=["validation_status", "updated_at"])
                invalid_count += 1
                self.stdout.write(self.style.WARNING(f"Invalid: {record.e164}"))
                continue

            fields = [
                "national_format",
                "area_code",
                "state",
                "validation_status",
                "updated_at",
            ]
            record.national_format = result.national_format
            record.area_code = result.area_code
            if result.state:
                record.state = result.state
            record.validation_status = PhoneRecord.ValidationStatus.VALID

            if record.e164 != result.e164:
                # Rare: e164 key change — only if no conflict
                if PhoneRecord.objects.filter(e164=result.e164).exclude(pk=record.pk).exists():
                    self.stdout.write(
                        self.style.ERROR(
                            f"Cannot rename {record.e164} -> {result.e164} (conflict); marked valid on old key"
                        )
                    )
                else:
                    record.e164 = result.e164
                    fields.append("e164")
            else:
                unchanged_e164 += 1

            record.save(update_fields=fields)
            valid_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. valid={valid_count} invalid={invalid_count} "
                f"(e164 unchanged on {unchanged_e164} of valid set). Total walked={total}."
            )
        )
