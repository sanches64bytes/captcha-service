from django.contrib import admin

from apps.authentication.models import Key


@admin.register(Key)
class KeyAdmin(admin.ModelAdmin):
    ...
