from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.authentication.auth import APIKeyAuthenticationError, authenticate_request
from apps.authentication.models import Key
from apps.captchas.repository import CaptchaTaskRepository

TEST_CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=TEST_CACHES, CAPTCHA_TASK_TTL=1800)
class AuthenticationTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        cache.clear()

    def test_authenticates_active_key(self) -> None:
        key = Key.objects.create(api_key="active-key", max_threads=2)
        request = self.factory.get("/", HTTP_X_API_KEY=key.api_key)

        self.assertEqual(authenticate_request(request), key)

    def test_rejects_missing_key(self) -> None:
        with self.assertRaises(APIKeyAuthenticationError):
            authenticate_request(self.factory.get("/"))

    def test_rejects_expired_key(self) -> None:
        key = Key.objects.create(
            api_key="expired-key",
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        with self.assertRaises(APIKeyAuthenticationError):
            authenticate_request(self.factory.get("/", HTTP_X_API_KEY=key.api_key))

    def test_regular_user_can_view_management_dashboard(self) -> None:
        user = User.objects.create_user("client", password="strong-password-123")
        key = Key.objects.create(api_key="client-key", owner=user)
        CaptchaTaskRepository().create(
            "managed-task",
            "turnstile",
            {"sitekey": "site", "pageurl": "https://example.test"},
            api_key_id=key.pk,
        )
        self.client.login(username="client", password="strong-password-123")

        response = self.client.get("/manage/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "client-key")
        self.assertContains(response, "managed-task")
        self.assertNotContains(response, "Usuários cadastrados")

    def test_regular_user_cannot_manage_keys(self) -> None:
        user = User.objects.create_user("client", password="strong-password-123")
        key = Key.objects.create(api_key="client-key", owner=user)
        self.client.login(username="client", password="strong-password-123")

        response = self.client.post(f"/manage/keys/{key.pk}/delete/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Key.objects.filter(pk=key.pk).exists())

    def test_superuser_can_create_admin_and_deactivate_user(self) -> None:
        User.objects.create_superuser(
            "root", password="strong-password-123", email="root@example.com"
        )
        client_user = User.objects.create_user("client", password="strong-password-123")
        self.client.login(username="root", password="strong-password-123")

        response = self.client.post(
            "/manage/users/",
            {
                "username": "admin-two",
                "email": "admin@example.com",
                "password": "another-strong-password-123",
                "password_confirmation": "another-strong-password-123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(username="admin-two").is_staff)
        response = self.client.post(f"/manage/users/{client_user.pk}/deactivate/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.get(pk=client_user.pk).is_active)
