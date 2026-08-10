from __future__ import annotations

import json
import time
from secrets import token_hex
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils.translation import gettext as _

from apps.captchas.services.captchaai.exceptions import (
    CaptchaAIConfigurationError,
    CaptchaAIError,
    CaptchaAIHTTPError,
    CaptchaAIInvalidResponseError,
    CaptchaAIProviderError,
    CaptchaAITaskNotReady,
    CaptchaAITemporaryError,
    CaptchaAITimeoutError,
    CaptchaAIUnsolvableError,
)

if TYPE_CHECKING:
    from apps.captchas.services.captchaai.solvers import CaptchaAIFile

CONFIGURATION_ERRORS = {
    "ERROR_WRONG_USER_KEY",
    "ERROR_KEY_DOES_NOT_EXIST",
    "ERROR_PAGEURL",
    "ERROR_BAD_PARAMETERS",
}
TEMPORARY_ERRORS = {"ERROR_SERVER_ERROR", "ERROR_INTERNAL_SERVER_ERROR"}


class CaptchaAIClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://ocr.captchaai.com",
        request_timeout: float = 30.0,
        poll_interval: float = 5.0,
        task_timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise CaptchaAIConfigurationError(
                _("CAPTCHAAI_API_KEY não está configurada.")
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.poll_interval = poll_interval
        self.task_timeout = task_timeout

    def submit(
        self,
        payload: dict[str, Any],
        http_method: str = "POST",
        files: dict[str, CaptchaAIFile] | None = None,
    ) -> str:
        response = self._request("in.php", payload, http_method, files=files)
        if response.get("status") != 1:
            self._raise_provider_error(response.get("request"))
        task_id = response.get("request")
        if not isinstance(task_id, (str, int)):
            raise CaptchaAIInvalidResponseError(
                _("O CaptchaAI não retornou o ID da tarefa.")
            )
        return str(task_id)

    def get_result(self, provider_task_id: str) -> dict[str, Any]:
        response = self._request(
            "res.php",
            {"action": "get", "id": provider_task_id},
            "GET",
        )
        if response.get("status") != 1:
            self._raise_provider_error(response.get("request"))
        return response

    def wait_result(self, provider_task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.task_timeout
        while True:
            try:
                return self.get_result(provider_task_id)
            except CaptchaAITaskNotReady:
                if time.monotonic() >= deadline:
                    raise CaptchaAITimeoutError(
                        _("A tarefa %(task_id)s do CaptchaAI excedeu o tempo limite.")
                        % {"task_id": provider_task_id}
                    ) from None
                time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))

    def extract_solution(self, response: dict[str, Any]) -> dict[str, Any]:
        solution = response.get("result") or response.get("request")
        if not isinstance(solution, str) or not solution:
            raise CaptchaAIInvalidResponseError(
                _("O CaptchaAI não retornou uma solução.")
            )
        result: dict[str, Any] = {"solution": solution}
        if isinstance(response.get("user_agent"), str):
            result["user_agent"] = response["user_agent"]
        return result

    def _request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        http_method: str,
        *,
        files: dict[str, CaptchaAIFile] | None = None,
    ) -> dict[str, Any]:
        data = {"key": self.api_key, "json": 1, **payload}
        url = f"{self.base_url}/{endpoint}"
        if http_method.upper() == "GET":
            if files:
                raise CaptchaAIConfigurationError(
                    _("Submissões GET não podem conter arquivos.")
                )
            encoded = urlencode(data).encode()
            request = Request(f"{url}?{encoded.decode()}", method="GET")
        elif files:
            encoded, content_type = self._encode_multipart(data, files)
            request = Request(
                url,
                data=encoded,
                headers={"Content-Type": content_type},
                method="POST",
            )
        else:
            encoded = urlencode(data).encode()
            request = Request(url, data=encoded, method="POST")
        try:
            with urlopen(request, timeout=self.request_timeout) as response:
                body = response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            raise CaptchaAIHTTPError(
                _("A requisição HTTP ao CaptchaAI falhou: %(error)s") % {"error": error}
            ) from error
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise CaptchaAIInvalidResponseError(
                _("O CaptchaAI retornou JSON inválido.")
            ) from error
        if not isinstance(parsed, dict):
            raise CaptchaAIInvalidResponseError(
                _("O CaptchaAI retornou uma resposta inválida.")
            )
        return parsed

    def _encode_multipart(
        self,
        data: dict[str, Any],
        files: dict[str, CaptchaAIFile],
    ) -> tuple[bytes, str]:
        boundary = f"captchaai-{token_hex(16)}"
        chunks: list[bytes] = []

        def add(value: str) -> None:
            chunks.append(value.encode("utf-8"))

        for name, value in data.items():
            add(f"--{boundary}\r\n")
            add(f'Content-Disposition: form-data; name="{name}"\r\n\r\n')
            add(f"{value}\r\n")
        for name, file in files.items():
            add(f"--{boundary}\r\n")
            disposition = f'Content-Disposition: form-data; name="{name}"'
            if file.filename is not None:
                disposition += f'; filename="{file.filename}"'
            add(f"{disposition}\r\n")
            add(f"Content-Type: {file.content_type}\r\n\r\n")
            content = (
                file.content.encode("utf-8")
                if isinstance(file.content, str)
                else file.content
            )
            chunks.extend((content, b"\r\n"))
        add(f"--{boundary}--\r\n")
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

    def _raise_provider_error(self, value: Any) -> None:
        if not isinstance(value, str):
            raise CaptchaAIInvalidResponseError(
                _("O CaptchaAI retornou um erro inválido.")
            )
        if value == "CAPCHA_NOT_READY":
            raise CaptchaAITaskNotReady(value)
        if value in CONFIGURATION_ERRORS:
            raise CaptchaAIConfigurationError(value)
        if value in TEMPORARY_ERRORS:
            raise CaptchaAITemporaryError(value)
        if value == "ERROR_CAPTCHA_UNSOLVABLE":
            raise CaptchaAIUnsolvableError(value)
        raise CaptchaAIProviderError(value)


def error_payload(error: Exception) -> dict[str, str]:
    if isinstance(error, CaptchaAIError):
        return {"code": error.code, "message": str(error)}
    return {"code": "unexpected_error", "message": _("Ocorreu um erro inesperado.")}
