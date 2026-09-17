"""Manually enrich pending / stale phone records (Phase 6)."""

from django.core.management.base import BaseCommand

from phones.tasks import enrich_pending_batch


class Command(BaseCommand):
    help = "Enrich pending, offline-only, failed, or stale phone records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Max records to process (default 25).",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            help="Enqueue Celery batch task instead of running inline.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if options["run_async"]:
            result = enrich_pending_batch.delay(limit=limit)
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued enrich_pending_batch task_id={result.id} limit={limit}")
            )
            return

        summary = enrich_pending_batch(limit=limit)
        processed = summary.get("processed", 0)
        self.stdout.write(self.style.SUCCESS(f"Enriched {processed} record(s)."))
        for item in summary.get("results") or []:
            self.stdout.write(
                f"  id={item.get('phone_id')} e164={item.get('e164')} "
                f"status={item.get('enrichment_status')}"
            )
