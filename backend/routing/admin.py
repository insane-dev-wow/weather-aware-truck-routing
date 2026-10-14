from django.contrib import admin

from .models import RoutePlan


@admin.register(RoutePlan)
class RoutePlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "origin",
        "destination",
        "load_lbs",
        "sample_interval_miles",
        "recommended_route",
        "created_at",
    )
    list_filter = ("sample_interval_miles", "recommended_route")
    search_fields = ("origin", "destination")
    date_hierarchy = "created_at"
    readonly_fields = ("result", "created_at")
