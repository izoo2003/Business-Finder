from django.contrib import admin, messages

from phones.csv_export import build_phone_csv_response

from .models import PhoneRecord


@admin.register(PhoneRecord)
class PhoneRecordAdmin(admin.ModelAdmin):
    date_hierarchy = "last_seen_at"
    list_display = (
        "e164",
        "national_format",
        "business_name",
        "city",
        "state",
        "area_code",
        "source",
        "validation_status",
        "enrichment_status",
        "line_type",
        "risk_level",
        "last_seen_at",
    )
    list_filter = (
        "source",
        "state",
        "area_code",
        "validation_status",
        "enrichment_status",
        "line_type",
        "risk_level",
        ("last_seen_at", admin.DateFieldListFilter),
        ("first_seen_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "e164",
        "national_format",
        "business_name",
        "city",
        "raw_phone",
        "carrier",
        "category",
        "postal_code",
        "source_record_id",
    )
    readonly_fields = (
        "first_seen_at",
        "created_at",
        "updated_at",
        "enriched_at",
        "enrichment_raw",
        "enrichment_error",
    )
    autocomplete_fields = ("source",)
    actions = ["delete_selected", "export_selected_csv"]
    actions_on_top = True
    actions_on_bottom = True
    actions_selection_counter = True

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            action, name, _label = actions["delete_selected"]
            actions["delete_selected"] = (
                action,
                name,
                "Delete selected phone numbers",
            )
        return actions

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff

    @admin.action(description="Export selected as CSV")
    def export_selected_csv(self, request, queryset):
        qs = queryset.select_related("source").order_by(
            "state", "city", "business_name", "e164"
        )
        count = qs.count()
        response = build_phone_csv_response(qs, filename_prefix="phone_records")
        self.message_user(
            request,
            f"Exported {count} phone record(s) to CSV.",
            messages.SUCCESS,
        )
        return response

    fieldsets = (
        (
            "Number",
            {
                "fields": (
                    "e164",
                    "national_format",
                    "raw_phone",
                    "area_code",
                    "state",
                    "validation_status",
                )
            },
        ),
        (
            "Business",
            {
                "fields": (
                    "business_name",
                    "address",
                    "city",
                    "postal_code",
                    "category",
                )
            },
        ),
        (
            "Enrichment",
            {
                "fields": (
                    "enrichment_status",
                    "line_type",
                    "carrier",
                    "risk_level",
                    "risk_signals",
                    "enrichment_geo",
                    "enriched_at",
                    "enrichment_raw",
                    "enrichment_error",
                )
            },
        ),
        (
            "Provenance",
            {
                "fields": (
                    "source",
                    "source_record_id",
                    "source_url",
                    "source_query",
                    "raw_payload",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "first_seen_at",
                    "last_seen_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
