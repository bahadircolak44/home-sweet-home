from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from shopping.forms import HomeAuthenticationForm

urlpatterns = [
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
    path("", include("shopping.urls")),
]

handler403 = "shopping.views.error_403"
handler404 = "shopping.views.error_404"
handler500 = "shopping.views.error_500"
