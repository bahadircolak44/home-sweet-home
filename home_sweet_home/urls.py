from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from google_integration.views import HomeLoginView
from shopping import views as shopping_views
from talk_later import views as talk_later_views

urlpatterns = [
    path("", shopping_views.dashboard, name="home"),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        HomeLoginView.as_view(),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/google/", include("google_integration.urls")),
    path("service-worker.js", shopping_views.service_worker, name="service_worker"),
    path("groceries/", include("shopping.urls")),
    path("chores/", include("chores.urls")),
    path("talk-later/", include("talk_later.urls")),
    path("assistant/", include("ai_assistant.urls")),
    path(
        "internal/talk-later/process-reminders/",
        talk_later_views.process_reminders,
        name="talk_later_process_reminders",
    ),
    path("notifications/", include("push_notifications.urls")),
]

handler403 = "shopping.views.error_403"
handler404 = "shopping.views.error_404"
handler500 = "shopping.views.error_500"
