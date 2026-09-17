"""
URL configuration for the Phone Collection Agent.
"""

from types import MethodType

from django.contrib import admin
from django.urls import include, path

from config.dashboard import build_dashboard_context

admin.site.site_header = "Phone Collection Agent"
admin.site.site_title = "Phone Agent Admin"
admin.site.index_title = "Operations dashboard"
admin.site.index_template = "admin/index.html"


def _ops_index(self, request, extra_context=None):
    context = build_dashboard_context()
    if extra_context:
        context.update(extra_context)
    return admin.AdminSite.index(self, request, context)


admin.site.index = MethodType(_ops_index, admin.site)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
