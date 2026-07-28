import os
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [
        value.strip() for value in os.getenv(name, default).split(",") if value.strip()
    ]


def _normalized_email(value):
    return value.strip().lower()


def _google_legacy_user_map(value):
    mapping = {}
    usernames = set()
    for entry in (item.strip() for item in value.split(",") if item.strip()):
        if entry.count(":") != 1:
            raise ImproperlyConfigured(
                "GOOGLE_LEGACY_USER_MAP entries must use email:username."
            )
        raw_email, raw_username = entry.split(":", 1)
        email = _normalized_email(raw_email)
        username = raw_username.strip()
        if not email or "@" not in email or not username:
            raise ImproperlyConfigured(
                "GOOGLE_LEGACY_USER_MAP entries must use a valid email and username."
            )
        if email in mapping:
            raise ImproperlyConfigured(
                "GOOGLE_LEGACY_USER_MAP contains a duplicate email."
            )
        if username in usernames:
            raise ImproperlyConfigured(
                "GOOGLE_LEGACY_USER_MAP contains a duplicate username."
            )
        mapping[email] = username
        usernames.add(username)
    return mapping


SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-local-development-key")
DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "households.apps.HouseholdsConfig",
    "push_notifications.apps.PushNotificationsConfig",
    "shopping.apps.ShoppingConfig",
    "chores.apps.ChoresConfig",
    "talk_later.apps.TalkLaterConfig",
    "google_integration.apps.GoogleIntegrationConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "home_sweet_home.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "libraries": {
                "shopping_extras": "shopping.templatetags.shopping_extras",
            },
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "home_sweet_home.wsgi.application"
ASGI_APPLICATION = "home_sweet_home.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL is required.")
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=60,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Europe/Amsterdam")
USE_I18N = True
USE_TZ = True

# Functions Framework reserves ``/static/`` for Flask's own static-file route.
# Use a different prefix so requests reach Django and WhiteNoise.
STATIC_URL = "/assets/"
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles"))
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
URLIZE_ASSUME_HTTPS = True

PASSWORD_LOGIN_ENABLED = env_bool("PASSWORD_LOGIN_ENABLED", True)
GOOGLE_OAUTH_ENABLED = env_bool("GOOGLE_OAUTH_ENABLED", False)
GOOGLE_CALENDAR_ENABLED = env_bool("GOOGLE_CALENDAR_ENABLED", False)
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
GOOGLE_ALLOWED_EMAILS = tuple(
    dict.fromkeys(_normalized_email(value) for value in env_list("GOOGLE_ALLOWED_EMAILS"))
)
GOOGLE_LEGACY_USER_MAP = _google_legacy_user_map(
    os.getenv("GOOGLE_LEGACY_USER_MAP", "")
)
GOOGLE_TOKEN_ENCRYPTION_KEY = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "").strip()
GOOGLE_CALENDAR_EVENT_DURATION_MINUTES = int(
    os.getenv("GOOGLE_CALENDAR_EVENT_DURATION_MINUTES", "30")
)

if GOOGLE_CALENDAR_EVENT_DURATION_MINUTES <= 0:
    raise ImproperlyConfigured(
        "GOOGLE_CALENDAR_EVENT_DURATION_MINUTES must be a positive integer."
    )

if GOOGLE_CALENDAR_ENABLED and not GOOGLE_OAUTH_ENABLED:
    raise ImproperlyConfigured("Google Calendar requires Google OAuth to be enabled.")

if GOOGLE_OAUTH_ENABLED:
    required_google_settings = {
        "GOOGLE_OAUTH_CLIENT_ID": GOOGLE_OAUTH_CLIENT_ID,
        "GOOGLE_OAUTH_CLIENT_SECRET": GOOGLE_OAUTH_CLIENT_SECRET,
        "GOOGLE_OAUTH_REDIRECT_URI": GOOGLE_OAUTH_REDIRECT_URI,
        "GOOGLE_TOKEN_ENCRYPTION_KEY": GOOGLE_TOKEN_ENCRYPTION_KEY,
    }
    missing_google_settings = [
        name for name, value in required_google_settings.items() if not value
    ]
    if missing_google_settings:
        raise ImproperlyConfigured(
            "Google OAuth is enabled but these settings are missing: "
            + ", ".join(missing_google_settings)
            + "."
        )
    parsed_redirect_uri = urlparse(GOOGLE_OAUTH_REDIRECT_URI)
    if not parsed_redirect_uri.scheme or not parsed_redirect_uri.netloc:
        raise ImproperlyConfigured("GOOGLE_OAUTH_REDIRECT_URI must be an absolute URL.")
    if not GOOGLE_ALLOWED_EMAILS:
        raise ImproperlyConfigured(
            "GOOGLE_ALLOWED_EMAILS must not be empty when Google OAuth is enabled."
        )
    try:
        Fernet(GOOGLE_TOKEN_ENCRYPTION_KEY.encode())
    except (TypeError, ValueError) as error:
        raise ImproperlyConfigured(
            "GOOGLE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
        ) from error

PUSH_NOTIFICATIONS_ENABLED = env_bool("PUSH_NOTIFICATIONS_ENABLED", False)
TALK_LATER_REMINDER_JOB_TOKEN = os.getenv("TALK_LATER_REMINDER_JOB_TOKEN", "").strip()
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "").strip()
_vapid_private_key_path = os.getenv("VAPID_PRIVATE_KEY_PATH", "").strip()
VAPID_PRIVATE_KEY_PATH = (
    Path(_vapid_private_key_path)
    if _vapid_private_key_path and Path(_vapid_private_key_path).is_absolute()
    else BASE_DIR / _vapid_private_key_path
    if _vapid_private_key_path
    else None
)

if PUSH_NOTIFICATIONS_ENABLED:
    missing_vapid_settings = [
        name
        for name, value in {
            "VAPID_PUBLIC_KEY": VAPID_PUBLIC_KEY,
            "VAPID_PRIVATE_KEY_PATH": _vapid_private_key_path,
            "VAPID_SUBJECT": VAPID_SUBJECT,
        }.items()
        if not value
    ]
    if missing_vapid_settings:
        raise ImproperlyConfigured(
            "Web Push is enabled but these settings are missing: "
            + ", ".join(missing_vapid_settings)
            + "."
        )
    if not VAPID_PRIVATE_KEY_PATH.is_file():
        raise ImproperlyConfigured(
            "VAPID_PRIVATE_KEY_PATH must point to a readable private key file."
        )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_oauth_callback": {
            "()": "home_sweet_home.logging_filters.RedactOAuthCallbackFilter",
        }
    },
    "formatters": {
        "django.server": {
            "()": "django.utils.log.ServerFormatter",
            "format": "[{server_time}] {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "django_server": {
            "class": "logging.StreamHandler",
            "formatter": "django.server",
            "filters": ["redact_oauth_callback"],
        },
    },
    "loggers": {
        "django.server": {
            "handlers": ["django_server"],
            "level": "INFO",
            "propagate": False,
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
