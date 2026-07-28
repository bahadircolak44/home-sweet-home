from django.urls import path

from . import views

app_name = "google_integration"

urlpatterns = [
    path("start/", views.start, name="start"),
    path("callback/", views.callback, name="callback"),
    path("reconnect/", views.reconnect, name="reconnect"),
    path("status/", views.status, name="status"),
    path("disconnect/", views.disconnect, name="disconnect"),
]
