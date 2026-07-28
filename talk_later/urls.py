from django.urls import path

from . import views

app_name = "talk_later"

urlpatterns = [
    path("", views.topic_index, name="topic_index"),
    path("new/", views.topic_create, name="topic_create"),
    path("<int:topic_id>/", views.topic_detail, name="topic_detail"),
    path("<int:topic_id>/edit/", views.topic_edit, name="topic_edit"),
    path("<int:topic_id>/toggle/", views.topic_toggle, name="topic_toggle"),
    path("<int:topic_id>/delete/", views.topic_delete, name="topic_delete"),
    path("<int:topic_id>/calendar/retry/", views.topic_calendar_retry, name="topic_calendar_retry"),
]
