from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class TokenEncryptionError(Exception):
    """Raised without exposing token material when token encryption is unavailable."""


def _fernet():
    try:
        return Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode())
    except (AttributeError, TypeError, ValueError) as error:
        raise TokenEncryptionError("Google token encryption is unavailable.") from error


def encrypt_refresh_token(refresh_token):
    if not refresh_token:
        return ""
    try:
        return _fernet().encrypt(refresh_token.encode()).decode()
    except (AttributeError, UnicodeError) as error:
        raise TokenEncryptionError("Google token encryption is unavailable.") from error


def decrypt_refresh_token(encrypted_refresh_token):
    if not encrypted_refresh_token:
        raise TokenEncryptionError("Google Calendar needs to be reconnected.")
    try:
        return _fernet().decrypt(encrypted_refresh_token.encode()).decode()
    except (InvalidToken, UnicodeError, AttributeError) as error:
        raise TokenEncryptionError("Google Calendar needs to be reconnected.") from error
