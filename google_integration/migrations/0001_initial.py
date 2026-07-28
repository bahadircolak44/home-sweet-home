from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="GoogleAccountConnection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("google_subject", models.CharField(max_length=255, unique=True)),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("email_verified", models.BooleanField(default=False)),
                ("encrypted_refresh_token", models.TextField(blank=True, default="")),
                ("granted_scopes", models.JSONField(default=list)),
                ("connected_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                ("last_calendar_success_at", models.DateTimeField(blank=True, null=True)),
                ("reauthorization_required", models.BooleanField(default=False)),
                ("last_error", models.TextField(blank=True, default="")),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="google_account_connection",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="googleaccountconnection",
            index=models.Index(
                fields=["email_verified", "reauthorization_required"],
                name="google_conn_state_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="googleaccountconnection",
            index=models.Index(
                fields=["last_calendar_success_at"],
                name="google_conn_success_idx",
            ),
        ),
    ]
