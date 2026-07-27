from django.urls import path

from . import views

app_name = "push_notifications"

urlpatterns = [
    path("subscribe/", views.subscribe, name="subscribe"),
    path("unsubscribe/", views.unsubscribe, name="unsubscribe"),
    path("test/", views.test_notification, name="test"),
]
