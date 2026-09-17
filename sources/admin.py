from django.contrib import admin, messages

from .models import DataSource


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "source_type",
        "priority",
        "is_active",
        "quota_status",
        "quota_remaining",
        "quota_max",
        "window_type",
        "api_key_env_var",
        "last_successful_run_at",
    )
    list_editable = ("is_active",)
    list_display_links = ("name",)
    list_filter = ("source_type", "is_active", "quota_status", "window_type")
    search_fields = ("name", "slug", "api_key_env_var")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "quota_refreshed_at", "api_key_hint")
    actions = ["pause_selected_sources", "resume_selected_sources"]

    @admin.action(description="Pause selected sources")
    def pause_selected_sources(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Paused {updated} source(s). Scheduler and enrichment will skip them.",
            messages.WARNING,
        )

    @admin.action(description="Resume selected sources")
    def resume_selected_sources(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Resumed {updated} source(s).",
            messages.SUCCESS,
        )

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "name",
                    "slug",
                    "source_type",
                    "priority",
                    "is_active",
                )
            },
        ),
        (
            "Credentials",
            {
                "fields": ("api_key_env_var", "api_key_hint", "credential_notes"),
                "description": "Paste keys in the operator UI. Only the last four characters are shown here.",
            },
        ),
        (
            "Quota",
            {
                "fields": (
                    "quota_max",
                    "quota_remaining",
                    "window_type",
                    "quota_reset_at",
                    "quota_refreshed_at",
                    "safety_buffer_percent",
                    "quota_status",
                )
            },
        ),
        (
            "Operations",
            {
                "fields": (
                    "last_successful_run_at",
                    "allowed_params",
                    "data_quality_notes",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
