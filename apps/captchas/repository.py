import math
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext as _

from apps.captchas.domain import CaptchaTaskData, CaptchaTaskStatus, TaskError


class CaptchaTaskNotFoundError(Exception):
    """Raised when a task is absent or has expired."""


class CaptchaTaskStateError(Exception):
    """Raised when an invalid or concurrent state transition is attempted."""


class CaptchaTaskRepository:
    key_prefix = "captcha:task:"
    index_prefix = "captcha:task-index:"
    lock_prefix = "captcha:task-lock:"

    def __init__(self, ttl: int | None = None) -> None:
        self.ttl = ttl or settings.CAPTCHA_TASK_TTL

    def create(
        self,
        task_id: str,
        captcha_type: str,
        payload: dict[str, Any],
        api_key_id: int | None = None,
    ) -> CaptchaTaskData:
        now = datetime.now(UTC).isoformat()
        task: CaptchaTaskData = {
            "task_id": task_id,
            "status": CaptchaTaskStatus.PENDING,
            "captcha_type": captcha_type,
            "api_key_id": api_key_id,
            "payload": payload,
            "provider_task_id": None,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "expires_at": time.time() + self.ttl,
        }
        if not cache.add(self._key(task_id), task, timeout=self.ttl):
            raise CaptchaTaskStateError(
                _("A tarefa %(task_id)s já existe.") % {"task_id": task_id}
            )
        self._add_to_index(task["api_key_id"], task_id)
        return task

    def get(self, task_id: str) -> CaptchaTaskData:
        task = cache.get(self._key(task_id))
        if task is None:
            raise CaptchaTaskNotFoundError(task_id)
        return task

    def set_processing(
        self, task_id: str, provider_task_id: str | None = None
    ) -> CaptchaTaskData:
        changes: dict[str, Any] = {"status": CaptchaTaskStatus.PROCESSING}
        if provider_task_id is not None:
            changes["provider_task_id"] = provider_task_id
        return self._update(
            task_id,
            allowed={CaptchaTaskStatus.PENDING, CaptchaTaskStatus.PROCESSING},
            **changes,
        )

    def set_completed(self, task_id: str, result: dict[str, Any]) -> CaptchaTaskData:
        return self._update(
            task_id,
            allowed={CaptchaTaskStatus.PROCESSING},
            status=CaptchaTaskStatus.COMPLETED,
            result=result,
            error=None,
        )

    def set_failed(self, task_id: str, error: TaskError) -> CaptchaTaskData:
        return self._update(
            task_id,
            allowed={CaptchaTaskStatus.PENDING, CaptchaTaskStatus.PROCESSING},
            status=CaptchaTaskStatus.FAILED,
            error=error,
        )

    def _update(
        self,
        task_id: str,
        *,
        allowed: set[CaptchaTaskStatus],
        **changes: Any,
    ) -> CaptchaTaskData:
        with self._lock(task_id):
            task = self.get(task_id)
            if task["status"] not in allowed:
                raise CaptchaTaskStateError(
                    _(
                        "Não é possível atualizar a tarefa %(task_id)s "
                        "a partir do estado %(status)s."
                    )
                    % {"task_id": task_id, "status": task["status"]}
                )
            updated = {**task, **changes, "updated_at": datetime.now(UTC).isoformat()}
            remaining_ttl = math.ceil(task["expires_at"] - time.time())
            if remaining_ttl <= 0:
                cache.delete(self._key(task_id))
                raise CaptchaTaskNotFoundError(task_id)
            cache.set(self._key(task_id), updated, timeout=remaining_ttl)
            if updated["status"] in {
                CaptchaTaskStatus.COMPLETED,
                CaptchaTaskStatus.FAILED,
            }:
                self._remove_from_index(updated.get("api_key_id"), task_id)
            return updated  # type: ignore[return-value]

    def running_for_key(self, api_key_id: int) -> list[CaptchaTaskData]:
        task_ids = cache.get(self._index_key(api_key_id), []) or []
        running: list[CaptchaTaskData] = []
        valid_ids: list[str] = []
        for task_id in task_ids:
            try:
                task = self.get(task_id)
            except CaptchaTaskNotFoundError:
                continue
            valid_ids.append(task_id)
            if task["status"] in {
                CaptchaTaskStatus.PENDING,
                CaptchaTaskStatus.PROCESSING,
            }:
                running.append(task)
        cache.set(self._index_key(api_key_id), valid_ids, timeout=self.ttl)
        return running

    @contextmanager
    def _lock(self, task_id: str) -> Iterator[None]:
        lock_key = f"{self.lock_prefix}{task_id}"
        acquired = False
        for _attempt in range(20):
            if cache.add(lock_key, "1", timeout=5):
                acquired = True
                break
            time.sleep(0.01)
        if not acquired:
            raise CaptchaTaskStateError(
                _("A tarefa %(task_id)s está sendo atualizada.") % {"task_id": task_id}
            )
        try:
            yield
        finally:
            cache.delete(lock_key)

    def _key(self, task_id: str) -> str:
        return f"{self.key_prefix}{task_id}"

    def _add_to_index(self, api_key_id: int | None, task_id: str) -> None:
        if api_key_id is None:
            return
        task_ids = cache.get(self._index_key(api_key_id), []) or []
        if task_id not in task_ids:
            task_ids.append(task_id)
        cache.set(self._index_key(api_key_id), task_ids, timeout=self.ttl)

    def _remove_from_index(self, api_key_id: int | None, task_id: str) -> None:
        if api_key_id is None:
            return
        task_ids = cache.get(self._index_key(api_key_id), []) or []
        cache.set(
            self._index_key(api_key_id),
            [item for item in task_ids if item != task_id],
            timeout=self.ttl,
        )

    def _index_key(self, api_key_id: int) -> str:
        return f"{self.index_prefix}{api_key_id}"
