from django.urls import path

from api import auth_views, key_views, phone_views, scraper_views, usage_views

urlpatterns = [
    path("auth/csrf/", auth_views.csrf),
    path("auth/login/", auth_views.login_view),
    path("auth/logout/", auth_views.logout_view),
    path("auth/me/", auth_views.me),
    path("scraper/status/", scraper_views.status_view),
    path("scraper/start/", scraper_views.start_view),
    path("scraper/stop/", scraper_views.stop_view),
    path("scraper/orchestration/", scraper_views.orchestration_view),
    path("phones/", phone_views.phone_list),
    path("phones/filters/", phone_views.phone_filters),
    path("phones/export.csv", phone_views.phone_export),
    path("phones/<int:pk>/", phone_views.phone_detail),
    path("usage/", usage_views.usage_view),
    path("alerts/", usage_views.alerts_view),
    path("keys/", key_views.key_list),
    path("keys/<slug:slug>/", key_views.key_rotate),
]
