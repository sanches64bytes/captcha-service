from typing import Any

from ninja import Schema


class TaskCreateSchema(Schema):
    captcha_type: str
    data: dict[str, Any]


class TaskCreatedSchema(Schema):
    task_id: str
    status: str


class TaskErrorSchema(Schema):
    code: str
    message: str


class TaskDetailSchema(Schema):
    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error: TaskErrorSchema | None = None


class ErrorResponseSchema(Schema):
    detail: str
