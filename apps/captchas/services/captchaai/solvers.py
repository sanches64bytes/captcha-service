import base64
import binascii
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from django.utils.translation import gettext as _

from apps.captchas.services.captchaai.exceptions import (
    CaptchaAIConfigurationError,
    CaptchaAIInvalidResponseError,
)


@dataclass(frozen=True)
class CaptchaAIFile:
    content: bytes | str
    filename: str | None = None
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class CaptchaAISubmission:
    payload: dict[str, Any]
    http_method: str = "POST"
    files: dict[str, CaptchaAIFile] = field(default_factory=dict)


class CaptchaSolver(Protocol):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission: ...

    def parse_result(self, response: dict[str, Any]) -> dict[str, Any]: ...


def _required(data: dict[str, Any], *fields: str) -> None:
    missing = [field for field in fields if data.get(field) in (None, "")]
    if missing:
        raise CaptchaAIConfigurationError(
            _("Os campos obrigatórios do CAPTCHA não foram informados: %(fields)s.")
            % {"fields": ", ".join(missing)}
        )


def _pick(data: dict[str, Any], *fields: str) -> dict[str, Any]:
    return {field: data[field] for field in fields if data.get(field) is not None}


def _raw_solution(response: dict[str, Any]) -> str:
    solution = response.get("result") or response.get("request")
    if not isinstance(solution, str) or not solution:
        raise CaptchaAIInvalidResponseError(_("O CaptchaAI não retornou uma solução."))
    return solution


def _with_metadata(response: dict[str, Any], solution: Any) -> dict[str, Any]:
    result = {"solution": solution}
    if isinstance(response.get("user_agent"), str):
        result["user_agent"] = response["user_agent"]
    return result


def _decode_image(data: dict[str, Any]) -> CaptchaAIFile:
    _required(data, "body")
    encoded = data["body"]
    if not isinstance(encoded, str):
        raise CaptchaAIConfigurationError(_("body deve ser uma string Base64."))
    if encoded.startswith("data:"):
        try:
            header, encoded = encoded.split(",", 1)
        except ValueError as error:
            raise CaptchaAIConfigurationError(
                _("A data URI da imagem é inválida.")
            ) from error
        content_type = header.removeprefix("data:").split(";", 1)[0]
    else:
        content_type = str(data.get("content_type", "image/png"))
    if content_type not in {"image/jpeg", "image/png", "image/gif"}:
        raise CaptchaAIConfigurationError(_("A imagem deve ser JPEG, PNG ou GIF."))
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise CaptchaAIConfigurationError("body contains invalid Base64.") from error
    if not 100 <= len(content) <= 100 * 1024:
        raise CaptchaAIConfigurationError(
            _("O tamanho da imagem deve estar entre 100 bytes e 100 KB.")
        )
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}[
        content_type
    ]
    filename = str(data.get("filename", f"captcha.{extension}"))
    if any(character in filename for character in ('"', "\r", "\n")):
        raise CaptchaAIConfigurationError(
            _("O nome do arquivo contém caracteres inválidos.")
        )
    return CaptchaAIFile(content, filename, content_type)


class TokenSolver:
    def parse_result(self, response: dict[str, Any]) -> dict[str, Any]:
        return _with_metadata(response, _raw_solution(response))


class NormalCaptchaSolver(TokenSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        payload = {"method": "post", **_pick(data, "regsense", "numeric")}
        return CaptchaAISubmission(payload, files={"file": _decode_image(data)})


class GridImageSolver(TokenSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "grid_size", "img_type", "instructions")
        payload = {
            "method": "post",
            **_pick(data, "grid_size", "img_type", "instructions"),
        }
        return CaptchaAISubmission(payload, files={"file": _decode_image(data)})

    def parse_result(self, response: dict[str, Any]) -> dict[str, Any]:
        try:
            cells = json.loads(_raw_solution(response))
            if not isinstance(cells, list):
                raise TypeError
            cells = [int(cell) for cell in cells]
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise CaptchaAIInvalidResponseError(
                _("O CaptchaAI retornou uma solução de grade inválida.")
            ) from error
        return {"solution": cells}


class RecaptchaV2Solver(TokenSolver):
    def __init__(self, *, invisible: bool = False, enterprise: bool = False) -> None:
        self.invisible = invisible
        self.enterprise = enterprise

    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "googlekey", "pageurl")
        payload = {
            "method": "userrecaptcha",
            **_pick(data, "googlekey", "pageurl", "action"),
        }
        if self.invisible:
            payload["invisible"] = 1
        if self.enterprise:
            payload["enterprise"] = 1
        return CaptchaAISubmission(payload)


class RecaptchaV3Solver(TokenSolver):
    def __init__(self, *, enterprise: bool = False) -> None:
        self.enterprise = enterprise

    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "googlekey", "pageurl", "action")
        payload = {
            "method": "userrecaptcha",
            "version": "v3",
            **_pick(data, "googlekey", "pageurl", "action"),
        }
        if self.enterprise:
            payload["enterprise"] = 1
        return CaptchaAISubmission(payload)


class GeeTestV3Solver(TokenSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "gt", "challenge", "pageurl")
        return CaptchaAISubmission(
            {
                "method": "geetest",
                **_pick(data, "gt", "challenge", "pageurl", "api_server"),
            },
            http_method="GET",
        )

    def parse_result(self, response: dict[str, Any]) -> dict[str, Any]:
        try:
            solution = json.loads(_raw_solution(response))
            if not isinstance(solution, dict):
                raise TypeError
            parsed = {
                field: str(solution[field])
                for field in ("challenge", "validate", "seccode")
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise CaptchaAIInvalidResponseError(
                _("O CaptchaAI retornou uma solução GeeTest inválida.")
            ) from error
        return {"solution": parsed}


class TurnstileSolver(TokenSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "sitekey", "pageurl")
        return CaptchaAISubmission(
            {"method": "turnstile", **_pick(data, "sitekey", "pageurl")},
            http_method="GET",
        )


class CloudflareChallengeSolver(TokenSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "pageurl")
        return CaptchaAISubmission(
            {
                "method": "cloudflare_challenge",
                **_pick(data, "pageurl", "proxy", "proxytype", "user_agent"),
            }
        )


class BLSCaptchaSolver(GridImageSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "instructions", "images")
        images = data["images"]
        if not isinstance(images, list) or len(images) != 9:
            raise CaptchaAIConfigurationError(
                _("images deve conter exatamente 9 itens.")
            )
        files: dict[str, CaptchaAIFile] = {}
        for index, image in enumerate(images, start=1):
            if not isinstance(image, str) or not image.startswith("data:"):
                raise CaptchaAIConfigurationError(
                    _("Cada imagem BLS deve ser uma data URI Base64.")
                )
            try:
                header, encoded = image.split(",", 1)
                if ";base64" not in header:
                    raise ValueError
                base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as error:
                raise CaptchaAIConfigurationError(
                    _("Cada imagem BLS deve ser uma data URI Base64 válida.")
                ) from error
            files[f"image_base64_{index}"] = CaptchaAIFile(image)
        return CaptchaAISubmission(
            {"method": "bls", "instructions": data["instructions"]},
            files=files,
        )


class CaptchaFoxSolver(TokenSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "sitekey", "pageurl")
        return CaptchaAISubmission(
            {
                "method": "captchafox",
                **_pick(data, "sitekey", "pageurl", "proxy", "proxytype"),
            }
        )


class FriendlyCaptchaSolver(TokenSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "sitekey", "pageurl")
        return CaptchaAISubmission(
            {"method": "friendly_captcha", **_pick(data, "sitekey", "pageurl")},
            http_method="GET",
        )


class LeminSolver(TokenSolver):
    def build_submission(self, data: dict[str, Any]) -> CaptchaAISubmission:
        _required(data, "captcha_id", "pageurl")
        return CaptchaAISubmission(
            {
                "method": "lemin",
                **_pick(data, "captcha_id", "pageurl", "div_id"),
            },
            http_method="GET",
        )


SOLVERS: dict[str, CaptchaSolver] = {
    "normal": NormalCaptchaSolver(),
    "grid": GridImageSolver(),
    "recaptcha_v2": RecaptchaV2Solver(),
    "recaptcha_v2_invisible": RecaptchaV2Solver(invisible=True),
    "recaptcha_v2_callback": RecaptchaV2Solver(),
    "recaptcha_v2_enterprise": RecaptchaV2Solver(enterprise=True),
    "recaptcha_v3": RecaptchaV3Solver(),
    "recaptcha_v3_enterprise": RecaptchaV3Solver(enterprise=True),
    "geetest_v3": GeeTestV3Solver(),
    "turnstile": TurnstileSolver(),
    "cloudflare_challenge": CloudflareChallengeSolver(),
    "bls": BLSCaptchaSolver(),
    "captchafox": CaptchaFoxSolver(),
    "friendly_captcha": FriendlyCaptchaSolver(),
    "lemin": LeminSolver(),
}


def get_solver(captcha_type: str) -> CaptchaSolver:
    try:
        return SOLVERS[captcha_type]
    except KeyError as error:
        supported = ", ".join(sorted(SOLVERS))
        raise CaptchaAIConfigurationError(
            _("captcha_type não suportado. Valores aceitos: %(supported)s.")
            % {"supported": supported}
        ) from error
