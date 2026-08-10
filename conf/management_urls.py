from django.urls import path

from apps.authentication.management_views import (
    dashboard,
    deactivate_user,
    delete_key,
    documentation,
    renew_key,
    sign_in,
    sign_out,
    user_management,
)

urlpatterns = [
    path("login/", sign_in, name="management-login"),
    path("logout/", sign_out, name="management-logout"),
    path("", dashboard, name="management-dashboard"),
    path("docs/", documentation, name="management-docs"),
    path("keys/<int:key_id>/renew/", renew_key, name="management-renew-key"),
    path("keys/<int:key_id>/delete/", delete_key, name="management-delete-key"),
    path("users/", user_management, name="management-users"),
    path(
        "users/<int:user_id>/deactivate/",
        deactivate_user,
        name="management-deactivate-user",
    ),
]
