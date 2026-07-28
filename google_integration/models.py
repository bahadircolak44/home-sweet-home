from django.conf import settings
from django.db import models


class GoogleAccountConnection(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="google_account_connection",
    )
    google_subject = models.CharField(max_length=255, unique=True)
    email = models.EmailField(max_length=254, db_index=True)
    email_verified = models.BooleanField(default=False)
    encrypted_refresh_token = models.TextField(blank=True, default="")
    granted_scopes = models.JSONField(default=list)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_calendar_success_at = models.DateTimeField(null=True, blank=True)
    reauthorization_required = models.BooleanField(default=False)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(
                fields=["email_verified", "reauthorization_required"],
                name="google_conn_state_idx",
            ),
            models.Index(fields=["last_calendar_success_at"], name="google_conn_success_idx"),
        ]

    def __str__(self):
        return f"Google connection for {self.user}"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        self.last_error = self.last_error[:500]
        return super().save(*args, **kwargs)

    @property
    def has_refresh_token(self):
        return bool(self.encrypted_refresh_token)
