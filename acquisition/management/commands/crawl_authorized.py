"""Crawl a company-authorized website DataSource (Phase 9)."""

from django.core.management.base import BaseCommand, CommandError

from acquisition.authorized_crawl import AuthorizedCrawlError, crawl_authorized_source
from acquisition.cli_utils import command_error_from_exc
from sources.models import DataSource


class Command(BaseCommand):
    help = (
        "Crawl an authorized website source (source_type=website, "
        "allowed_params.authorized=true). Refuses unauthorized sources."
    )

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True, help="DataSource slug")
        parser.add_argument("--city", default="", help="Optional city hint for records")
        parser.add_argument("--category", default="website")
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--max-pages", type=int, default=5)

    def handle(self, *args, **options):
        slug = options["slug"].strip()
        try:
            source = DataSource.objects.get(slug=slug)
        except DataSource.DoesNotExist as exc:
            raise CommandError(f"Source '{slug}' not found") from exc

        self.stdout.write(f"Crawling authorized source {slug}...")
        try:
            stats = crawl_authorized_source(
                source,
                city=options["city"],
                category=options["category"],
                limit=options["limit"],
                max_pages=options["max_pages"],
            )
        except AuthorizedCrawlError as exc:
            raise command_error_from_exc(exc) from exc
        except Exception as exc:
            raise command_error_from_exc(exc) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. fetched={stats.fetched} saved={stats.saved} "
                f"updated={stats.updated} skipped={stats.skipped}"
            )
        )
