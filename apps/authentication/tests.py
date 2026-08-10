from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.authentication.auth import APIKeyAuthenticationError, authenticate_request
from apps.authentication.models import Key


class AuthenticationTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

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
