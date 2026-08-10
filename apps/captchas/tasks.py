from celery import shared_task
from django.conf import settings

from apps.captchas.quota import ThreadQuotaService
from apps.captchas.repository import (
    CaptchaTaskNotFoundError,
    CaptchaTaskRepository,
    CaptchaTaskStateError,
)
from apps.captchas.services.captchaai.client import CaptchaAIClient, error_payload
from apps.captchas.services.captchaai.solvers import get_solver


def build_captchaai_client() -> CaptchaAIClient:
    return CaptchaAIClient(
        settings.CAPTCHAAI_API_KEY,
        base_url=settings.CAPTCHAAI_BASE_URL,
        request_timeout=settings.CAPTCHAAI_REQUEST_TIMEOUT,
        poll_interval=settings.CAPTCHAAI_POLL_INTERVAL,
        task_timeout=settings.CAPTCHAAI_TASK_TIMEOUT,
    )


@shared_task(name="captchas.process_captcha")
def process_captcha(task_id: str) -> None:
    repository = CaptchaTaskRepository()
    quota = ThreadQuotaService()
    try:
        task = repository.set_processing(task_id)
        solver = get_solver(task["captcha_type"])
        submission = solver.build_submission(task["payload"])
        client = build_captchaai_client()
        provider_task_id = client.submit(
            submission.payload,
            http_method=submission.http_method,
            files=submission.files,
        )
        repository.set_processing(task_id, provider_task_id)
        provider_result = client.wait_result(provider_task_id)
        completed = repository.set_completed(
            task_id, solver.parse_result(provider_result)
        )
        quota.release(task_id, completed["api_key_id"])
    except CaptchaTaskNotFoundError:
        return
    except Exception as error:  # noqa: BLE001 - task state must survive unknown failures
        try:
            failed = repository.set_failed(task_id, error_payload(error))
            quota.release(task_id, failed["api_key_id"])
        except CaptchaTaskNotFoundError, CaptchaTaskStateError:
            return
