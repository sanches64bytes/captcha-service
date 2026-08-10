from uuid import uuid4

from django.utils.translation import gettext as _
from ninja import Router

from apps.authentication.auth import APIKeyAuthenticationError, authenticate_request
from apps.captchas.api.schemas import (
    ErrorResponseSchema,
    TaskCreatedSchema,
    TaskCreateSchema,
    TaskDetailSchema,
)
from apps.captchas.quota import ThreadLimitExceeded, ThreadQuotaService
from apps.captchas.repository import CaptchaTaskNotFoundError, CaptchaTaskRepository
from apps.captchas.services.captchaai.exceptions import CaptchaAIConfigurationError
from apps.captchas.services.captchaai.solvers import get_solver
from apps.captchas.tasks import process_captcha

captchas_router = Router()


@captchas_router.post(
    "/",
    response={
        202: TaskCreatedSchema,
        401: ErrorResponseSchema,
        429: ErrorResponseSchema,
        422: ErrorResponseSchema,
        503: ErrorResponseSchema,
    },
)
def create_task(request, payload: TaskCreateSchema):
    try:
        api_key = authenticate_request(request)
    except APIKeyAuthenticationError as error:
        return 401, {"detail": str(error)}

    data = dict(payload.data)
    try:
        get_solver(payload.captcha_type).build_submission(data)
    except CaptchaAIConfigurationError as error:
        return 422, {"detail": str(error)}

    quota = ThreadQuotaService()
    try:
        quota.reserve(api_key.pk, api_key.max_threads)
    except ThreadLimitExceeded as error:
        return 429, {"detail": str(error)}

    task_id = str(uuid4())
    repository = CaptchaTaskRepository()
    try:
        repository.create(task_id, payload.captcha_type, data, api_key_id=api_key.pk)
    except Exception:
        quota.release(task_id, api_key.pk)
        raise
    try:
        process_captcha.delay(task_id)
    except Exception:  # noqa: BLE001 - broker clients expose different exceptions
        repository.set_failed(
            task_id,
            {
                "code": "queue_unavailable",
                "message": _("A tarefa não pôde ser enviada para processamento."),
            },
        )
        quota.release(task_id, api_key.pk)
        return 503, {"detail": _("O processamento está temporariamente indisponível.")}
    return 202, {"task_id": task_id, "status": "processing"}


@captchas_router.get(
    "/{task_id}/",
    response={
        200: TaskDetailSchema,
        401: ErrorResponseSchema,
        404: ErrorResponseSchema,
    },
)
def get_task(request, task_id: str):
    try:
        api_key = authenticate_request(request)
    except APIKeyAuthenticationError as error:
        return 401, {"detail": str(error)}
    try:
        task = CaptchaTaskRepository().get(task_id)
    except CaptchaTaskNotFoundError:
        return 404, {"detail": _("Tarefa não encontrada ou expirada.")}
    if task.get("api_key_id") != api_key.pk:
        return 404, {"detail": _("Tarefa não encontrada ou expirada.")}

    public_status = "processing" if task["status"] == "pending" else task["status"]
    response = {"task_id": task["task_id"], "status": public_status}
    if task["status"] == "completed":
        response["result"] = task["result"]
    elif task["status"] == "failed":
        response["error"] = task["error"]
    return 200, response
