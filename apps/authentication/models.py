import secrets
from functools import partial

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as _


class Key(models.Model):
    api_key = models.CharField(
        default=partial(secrets.token_urlsafe, 32),
        max_length=128,
        db_index=True,
        unique=True
    )
    max_threads = models.PositiveSmallIntegerField(default=1)
    expires_at = models.DateTimeField(null=True, blank=True)
    

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Proprietário"),
        related_name="api_keys",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("Chave")
        verbose_name_plural = _("Chaves")

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        

        now = timezone.now()
        return self.expires_at <= now
