import time
from collections.abc import Iterator
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext as _


class ThreadLimitExceeded(Exception):
    """Raised when an API key has no available processing thread."""


class ThreadQuotaService:
    count_prefix = "captcha:threads:"
    lock_prefix = "captcha:threads-lock:"
    release_prefix = "captcha:threads-released:"

    def reserve(self, key_id: int, max_threads: int) -> None:
        if max_threads < 1:
            raise ThreadLimitExceeded(_("A chave não possui threads disponíveis."))
        with self._lock(key_id):
            count = int(cache.get(self._count_key(key_id)) or 0)
            if count >= max_threads:
                raise ThreadLimitExceeded(
                    _("O limite de threads da chave de API foi atingido.")
                )
            cache.set(
                self._count_key(key_id),
                count + 1,
                timeout=settings.CAPTCHA_TASK_TTL,
            )

    def release(self, task_id: str, key_id: int | None) -> None:
        if key_id is None:
            return
        with self._lock(key_id):
            if not cache.add(
                f"{self.release_prefix}{task_id}",
                "1",
                timeout=settings.CAPTCHA_TASK_TTL,
            ):
                return
            count = int(cache.get(self._count_key(key_id)) or 0)
            if count <= 1:
                cache.delete(self._count_key(key_id))
            else:
                cache.set(
                    self._count_key(key_id),
                    count - 1,
                    timeout=settings.CAPTCHA_TASK_TTL,
                )

    @contextmanager
    def _lock(self, key_id: int) -> Iterator[None]:
        lock_key = f"{self.lock_prefix}{key_id}"
        for _attempt in range(20):
            if cache.add(lock_key, "1", timeout=5):
                break
            time.sleep(0.01)
        else:
            raise ThreadLimitExceeded(
                _("Não foi possível verificar as threads disponíveis.")
            )
        try:
            yield
        finally:
            cache.delete(lock_key)

    def _count_key(self, key_id: int) -> str:
        return f"{self.count_prefix}{key_id}"
