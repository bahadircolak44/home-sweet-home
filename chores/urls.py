from django.urls import path

from . import views

app_name = "chores"

urlpatterns = [
    path("", views.session_index, name="session_index"),
    path("new/", views.session_create, name="session_create"),
    path("<int:session_id>/", views.session_detail, name="session_detail"),
    path("<int:session_id>/edit/", views.session_edit, name="session_edit"),
    path("<int:session_id>/complete/", views.session_complete, name="session_complete"),
    path("<int:session_id>/delete/", views.session_delete, name="session_delete"),
    path("history/", views.history, name="history"),
    path("history/<int:session_id>/", views.history_detail, name="history_detail"),
    path("<int:session_id>/tasks/add/", views.task_add, name="task_add"),
    path(
        "<int:session_id>/quick-add/<int:template_id>/",
        views.task_quick_add,
        name="task_quick_add",
    ),
    path(
        "<int:session_id>/completed-tasks/add/",
        views.completed_task_add,
        name="completed_task_add",
    ),
    path(
        "<int:session_id>/completed-tasks/remove/",
        views.completed_task_remove,
        name="completed_task_remove",
    ),
    path("tasks/<int:task_id>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<int:task_id>/toggle/", views.task_toggle, name="task_toggle"),
    path("tasks/<int:task_id>/delete/", views.task_delete, name="task_delete"),
    path("quick-list/", views.quick_list, name="quick_list"),
    path("quick-list/new/", views.template_create, name="template_create"),
    path("quick-list/<int:template_id>/edit/", views.template_edit, name="template_edit"),
    path(
        "quick-list/<int:template_id>/toggle/",
        views.template_toggle_active,
        name="template_toggle_active",
    ),
    path(
        "quick-list/<int:template_id>/delete/",
        views.template_delete,
        name="template_delete",
    ),
]
