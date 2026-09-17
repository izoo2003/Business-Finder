from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sources", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="datasource",
            name="api_key_ciphertext",
            field=models.TextField(
                blank=True,
                help_text="Fernet-encrypted API key pasted in the operator UI. Preferred over env.",
            ),
        ),
        migrations.AddField(
            model_name="datasource",
            name="api_key_hint",
            field=models.CharField(
                blank=True,
                help_text="Last four characters of the stored key for display only.",
                max_length=4,
            ),
        ),
    ]
