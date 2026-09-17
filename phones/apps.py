from django.apps import AppConfig


class PhonesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "phones"

    def ready(self) -> None:
        # Ensure Celery shared_task handlers register with the app.
        import phones.tasks  # noqa: F401

