from django.db import migrations, models


def seed_cities_categories(apps, schema_editor):
    OrchestrationState = apps.get_model("acquisition", "OrchestrationState")
    from django.conf import settings

    cities = list(getattr(settings, "ORCHESTRATION_CITIES", None) or [])
    categories = list(getattr(settings, "ORCHESTRATION_CATEGORIES", None) or [])
    if not cities:
        cities = ["Austin", "Dallas", "Houston", "San Antonio"]
    if not categories:
        categories = ["restaurant", "cafe"]

    for state in OrchestrationState.objects.all():
        changed = False
        if not state.cities:
            state.cities = cities
            changed = True
        if not state.categories:
            state.categories = categories
            changed = True
        if changed:
            state.save(update_fields=["cities", "categories"])


def unseed_cities_categories(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("acquisition", "0003_scraper_control"),
    ]

    operations = [
        migrations.AddField(
            model_name="orchestrationstate",
            name="cities",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="US cities to rotate through. Edited from the Scraper UI.",
            ),
        ),
        migrations.AddField(
            model_name="orchestrationstate",
            name="categories",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Business types to rotate through. Edited from the Scraper UI.",
            ),
        ),
        migrations.RunPython(seed_cities_categories, unseed_cities_categories),
    ]
