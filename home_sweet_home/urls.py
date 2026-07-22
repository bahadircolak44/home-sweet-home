from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from shopping.forms import HomeAuthenticationForm
from shopping import views as shopping_views

urlpatterns = [
    path("", shopping_views.dashboard, name="home"),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            authentication_form=HomeAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("service-worker.js", shopping_views.service_worker, name="service_worker"),
    path("groceries/", include("shopping.urls")),
]

handler403 = "shopping.views.error_403"
handler404 = "shopping.views.error_404"
handler500 = "shopping.views.error_500"
