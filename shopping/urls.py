from django.urls import path

from . import views

app_name = "shopping"

urlpatterns = [
    path("", views.active_lists, name="active_lists"),
    path("lists/new/", views.list_create, name="list_create"),
    path("lists/<int:list_id>/", views.list_detail, name="list_detail"),
    path("lists/<int:list_id>/edit/", views.list_edit, name="list_edit"),
    path("lists/<int:list_id>/delete/", views.list_delete, name="list_delete"),
    path("lists/<int:list_id>/complete/", views.list_complete, name="list_complete"),
    path("lists/<int:list_id>/items/add/", views.item_add, name="item_add"),
    path("items/<int:item_id>/edit/", views.item_edit, name="item_edit"),
    path("items/<int:item_id>/toggle/", views.item_toggle, name="item_toggle"),
    path("items/<int:item_id>/delete/", views.item_delete, name="item_delete"),
    path("history/", views.history, name="history"),
    path("history/<int:list_id>/", views.history_detail, name="history_detail"),
]
