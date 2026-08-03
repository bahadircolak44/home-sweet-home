from django.urls import path

from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("commands/text/", views.text_command, name="text_command"),
    path("commands/audio/", views.audio_command, name="audio_command"),
    path("commands/<uuid:command_id>/confirm/", views.confirm, name="confirm"),
    path("commands/<uuid:command_id>/cancel/", views.cancel, name="cancel"),
]
