from django.core.management.base import BaseCommand

from acquisition.cli_utils import command_error_from_exc
from acquisition.runner import FetchError, run_source_fetch


class Command(BaseCommand):
    help = "Fetch places with phones from Foursquare and save PhoneRecords."

    def add_arguments(self, parser):
        parser.add_argument("--city", required=True)
        parser.add_argument("--category", default="restaurant")
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        self.stdout.write(
            f"Searching Foursquare: {options['category']} in {options['city']}..."
        )
        try:
            result = run_source_fetch(
                "foursquare",
                city=options["city"],
                category=options["category"],
                limit=options["limit"],
                persist_cursor=True,
            )
        except FetchError as exc:
            raise command_error_from_exc(exc) from exc

        stats = result.stats
        source = result.source
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. fetched={stats.fetched} saved={stats.saved} "
                f"updated={stats.updated} skipped={stats.skipped} "
                f"quota_remaining={source.quota_remaining} status={source.quota_status}"
            )
        )
