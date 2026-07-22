from .base import *  # noqa: F403
from .base import env_bool, env_list

DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "192.168.68.120")
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
LOGGING["loggers"] = {  # noqa: F405
    "django": {"handlers": ["console"], "level": "INFO", "propagate": False}
}
