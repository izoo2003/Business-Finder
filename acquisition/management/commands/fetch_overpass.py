from django.core.management.base import BaseCommand

from acquisition.cli_utils import command_error_from_exc
from acquisition.runner import FetchError, run_source_fetch


class Command(BaseCommand):
    help = (
        "Fetch POIs with phone numbers from OpenStreetMap Overpass "
        "for a US city/category and save them as PhoneRecords."
    )

    def add_arguments(self, parser):
        parser.add_argument("--city", required=True, help="US city name, e.g. Austin")
        parser.add_argument(
            "--category",
            default="restaurant",
            help="Mapped category (restaurant, cafe, fast_food, pharmacy, ...)",
        )
        parser.add_argument(
            "--osm-tag",
            default=None,
            help="Override OSM tag as key=value, e.g. amenity=restaurant",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Max phone records to create/update (default 25)",
        )
        parser.add_argument(
            "--country",
            default="USA",
            help="Country hint for Nominatim (default USA)",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            f"Fetching Overpass: {options['category']} in {options['city']}..."
        )
        try:
            result = run_source_fetch(
                "openstreetmap",
                city=options["city"],
                category=options["category"],
                limit=options["limit"],
                country=options["country"].strip(),
                osm_tag=options["osm_tag"],
                persist_cursor=False,
            )
        except FetchError as exc:
            raise command_error_from_exc(exc) from exc

        stats = result.stats
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. fetched={stats.fetched} saved={stats.saved} "
                f"updated={stats.updated} skipped={stats.skipped}"
            )
        )
