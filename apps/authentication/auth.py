from django.utils.translation import gettext as _

from apps.authentication.models import Key


class APIKeyAuthenticationError(Exception):
    """Raised when an API key is missing, invalid, or expired."""


def get_api_key_from_request(request) -> str | None:
    value = request.headers.get("X-API-Key")
    if value:
        return value.strip()

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def authenticate_request(request) -> Key:
    raw_key = get_api_key_from_request(request)
    return authenticate_api_key(raw_key)


def authenticate_api_key(raw_key: str | None) -> Key:
    if not raw_key:
        raise APIKeyAuthenticationError(_("Informe uma chave de API."))
    try:
        key = Key.objects.get(api_key=raw_key)
    except Key.DoesNotExist as error:
        raise APIKeyAuthenticationError(_("A chave de API é inválida.")) from error
    if key.is_expired():
        raise APIKeyAuthenticationError(_("A chave de API expirou."))
    return key
