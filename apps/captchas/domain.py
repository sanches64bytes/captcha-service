from enum import StrEnum
from typing import Any, TypedDict


class CaptchaTaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskError(TypedDict):
    code: str
    message: str


class CaptchaTaskData(TypedDict):
    task_id: str
    status: str
    captcha_type: str
    api_key_id: int | None
    payload: dict[str, Any]
    provider_task_id: str | None
    result: dict[str, Any] | None
    error: TaskError | None
    created_at: str
    updated_at: str
    expires_at: float
