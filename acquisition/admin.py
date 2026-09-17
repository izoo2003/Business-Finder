from django.contrib import admin

from .models import (
    AcquisitionCursor,
    AcquisitionDecision,
    HarvestRun,
    OrchestrationState,
)


@admin.register(HarvestRun)
class HarvestRunAdmin(admin.ModelAdmin):
    date_hierarchy = "started_at"
    list_display = (
        "started_at",
        "status",
        "source",
        "city",
        "category",
        "fetched",
        "saved",
        "updated",
        "skipped_invalid",
        "quota_remaining_before",
        "quota_remaining_after",
    )
    list_filter = (
        "status",
        "source",
        "city",
        "category",
        ("started_at", admin.DateFieldListFilter),
    )
    search_fields = ("city", "category", "error")
    readonly_fields = (
        "source",
        "city",
        "category",
        "started_at",
        "finished_at",
        "status",
        "fetched",
        "saved",
        "updated",
        "skipped_invalid",
        "quota_remaining_before",
        "quota_remaining_after",
        "error",
        "cursor_before",
        "cursor_after",
    )
    ordering = ("-started_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AcquisitionDecision)
class AcquisitionDecisionAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = (
        "created_at",
        "outcome",
        "chosen_source",
        "city",
        "category",
        "harvest_run",
    )
    list_filter = ("outcome", "chosen_source", ("created_at", admin.DateFieldListFilter))
    search_fields = ("city", "category", "notes")
    readonly_fields = (
        "created_at",
        "chosen_source",
        "city",
        "category",
        "outcome",
        "skipped",
        "harvest_run",
        "notes",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AcquisitionCursor)
class AcquisitionCursorAdmin(admin.ModelAdmin):
    list_display = ("source", "city", "category", "updated_at")
    list_filter = ("source",)
    search_fields = ("city", "category")
    readonly_fields = ("updated_at",)


@admin.register(OrchestrationState)
class OrchestrationStateAdmin(admin.ModelAdmin):
    list_display = (
        "singleton_id",
        "city_index",
        "category_index",
        "scraper_enabled",
        "updated_at",
    )
    readonly_fields = ("updated_at",)
    fields = (
        "singleton_id",
        "cities",
        "categories",
        "city_index",
        "category_index",
        "scraper_enabled",
        "session_started_at",
        "session_saved",
        "session_updated",
        "last_error",
        "updated_at",
    )
