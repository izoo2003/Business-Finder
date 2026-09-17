"""Manually trigger one acquisition orchestration cycle (Phase 7)."""

from django.core.management.base import BaseCommand

from acquisition.scheduler import execute_cycle, plan_cycle


class Command(BaseCommand):
    help = "Run one autonomous acquisition cycle (or dry-run the plan)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print next source and city/category without calling APIs.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Override ORCHESTRATION_LIMIT for this run.",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            help="Enqueue Celery task instead of running inline.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            plan = plan_cycle(advance_rotation=False)
            if plan.source:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Would run source={plan.source.slug} "
                        f"priority={plan.source.priority} "
                        f"city={plan.city} category={plan.category} "
                        f"quota_remaining={plan.source.quota_remaining} "
                        f"status={plan.source.quota_status}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"No eligible source. city={plan.city} category={plan.category}. "
                        f"Reason: {plan.reason}"
                    )
                )
            return

        if options["run_async"]:
            from acquisition.tasks import run_acquisition_cycle

            result = run_acquisition_cycle.delay(limit=options["limit"])
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued run_acquisition_cycle task_id={result.id}")
            )
            return

        run = execute_cycle(dry_run=False, limit=options["limit"], force=True)
        slug = run.source.slug if run.source_id else "none"
        self.stdout.write(
            self.style.SUCCESS(
                f"HarvestRun id={run.pk} status={run.status} source={slug} "
                f"city={run.city} category={run.category} "
                f"fetched={run.fetched} saved={run.saved} updated={run.updated} "
                f"skipped={run.skipped_invalid}"
            )
        )
        if run.error:
            self.stdout.write(self.style.WARNING(f"error={run.error[:500]}"))
