from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("acquisition", "0002_phase9_audit_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="orchestrationstate",
            name="scraper_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When False, Beat and the loop task do not collect. Start/Stop from the UI.",
            ),
        ),
        migrations.AddField(
            model_name="orchestrationstate",
            name="session_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orchestrationstate",
            name="session_saved",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="orchestrationstate",
            name="session_updated",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="orchestrationstate",
            name="last_error",
            field=models.TextField(blank=True),
        ),
    ]
