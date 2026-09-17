from django.apps import AppConfig


class AcquisitionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "acquisition"
    verbose_name = "Acquisition"

    def ready(self) -> None:
        import acquisition.tasks  # noqa: F401
