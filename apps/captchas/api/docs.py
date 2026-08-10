from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from ninja import Router

from apps.authentication.auth import APIKeyAuthenticationError, authenticate_api_key

docs_router = Router()


@docs_router.get("/docs/", auth=None)
def captcha_docs(request, api_key: str | None = None) -> HttpResponse:
    """Renderiza a documentação somente para uma chave de API válida."""
    provided_key = request.headers.get("X-API-Key")
    if not provided_key:
        authorization = request.headers.get("Authorization", "")
        scheme, _separator, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            provided_key = token.strip()
    provided_key = provided_key or api_key

    try:
        key = authenticate_api_key(provided_key)
    except APIKeyAuthenticationError as error:
        return HttpResponse(str(error), status=401, content_type="text/plain")

    return render(
        request,
        "captchas/api_docs.html",
        {
            "title": _("Documentação da API de CAPTCHAs"),
            "key_threads": key.max_threads,
        },
    )
