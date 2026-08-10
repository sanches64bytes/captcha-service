import base64
import time
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.authentication.models import Key
from apps.captchas.quota import ThreadLimitExceeded, ThreadQuotaService
from apps.captchas.repository import (
    CaptchaTaskNotFoundError,
    CaptchaTaskRepository,
)
from apps.captchas.services.captchaai.client import CaptchaAIClient
from apps.captchas.services.captchaai.exceptions import CaptchaAIUnsolvableError
from apps.captchas.services.captchaai.solvers import SOLVERS, get_solver
from apps.captchas.tasks import process_captcha

TEST_CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=TEST_CACHES, CAPTCHA_TASK_TTL=1800)
class TaskAPITests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = Client()
        self.api_key = Key.objects.create(api_key="test-key", max_threads=1)
        self.headers = {"HTTP_X_API_KEY": self.api_key.api_key}

    @patch("apps.captchas.api.routes.process_captcha.delay")
    def test_create_task_stores_pending_task_and_dispatches_worker(
        self, delay: Mock
    ) -> None:
        response = self.client.post(
            "/api/v1/tasks/",
            data={
                "captcha_type": "recaptcha_v2",
                "data": {
                    "googlekey": "site-key",
                    "pageurl": "https://example.test/captcha",
                },
            },
            content_type="application/json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "processing")
        task = CaptchaTaskRepository().get(body["task_id"])
        self.assertEqual(task["status"], "pending")
        self.assertIsNone(task["result"])
        delay.assert_called_once_with(body["task_id"])

    @patch("apps.captchas.api.routes.process_captcha.delay")
    def test_get_pending_task(self, delay: Mock) -> None:
        task_id = self._create_task()

        response = self.client.get(f"/api/v1/tasks/{task_id}/", **self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], task_id)
        self.assertEqual(response.json()["status"], "processing")

    def test_get_unknown_task_returns_404(self) -> None:
        response = self.client.get("/api/v1/tasks/unknown/", **self.headers)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"], "Tarefa não encontrada ou expirada."
        )

    def test_create_task_requires_api_key(self) -> None:
        response = self.client.post(
            "/api/v1/tasks/",
            data={
                "captcha_type": "turnstile",
                "data": {"sitekey": "key", "pageurl": "https://example.test"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    @patch("apps.captchas.api.routes.process_captcha.delay")
    def test_task_cannot_be_read_with_another_api_key(self, delay: Mock) -> None:
        task_id = self._create_task()
        another_key = Key.objects.create(api_key="another-key", max_threads=1)

        response = self.client.get(
            f"/api/v1/tasks/{task_id}/",
            HTTP_X_API_KEY=another_key.api_key,
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_captcha_payload_returns_422(self) -> None:
        response = self.client.post(
            "/api/v1/tasks/",
            data={"captcha_type": "recaptcha_v3", "data": {"googlekey": "key"}},
            content_type="application/json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 422)

    @patch("apps.captchas.api.routes.process_captcha.delay")
    def test_queue_failure_marks_task_as_failed(self, delay: Mock) -> None:
        delay.side_effect = ConnectionError("broker unavailable")

        with patch("apps.captchas.api.routes.uuid4", return_value="queue-task"):
            response = self.client.post(
                "/api/v1/tasks/",
                data={
                    "captcha_type": "turnstile",
                    "data": {
                        "sitekey": "site-key",
                        "pageurl": "https://example.test",
                    },
                },
                content_type="application/json",
                **self.headers,
            )

        self.assertEqual(response.status_code, 503)
        task = CaptchaTaskRepository().get("queue-task")
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["error"]["code"], "queue_unavailable")

    @patch("apps.captchas.api.routes.process_captcha.delay")
    def test_thread_limit_returns_429(self, delay: Mock) -> None:
        first = self.client.post(
            "/api/v1/tasks/",
            data={
                "captcha_type": "turnstile",
                "data": {"sitekey": "key", "pageurl": "https://example.test"},
            },
            content_type="application/json",
            **self.headers,
        )
        second = self.client.post(
            "/api/v1/tasks/",
            data={
                "captcha_type": "turnstile",
                "data": {"sitekey": "key", "pageurl": "https://example.test"},
            },
            content_type="application/json",
            **self.headers,
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 429)

    def _create_task(self) -> str:
        with patch("apps.captchas.api.routes.process_captcha.delay"):
            response = self.client.post(
                "/api/v1/tasks/",
                data={
                    "captcha_type": "recaptcha_v2",
                    "data": {
                        "googlekey": "site-key",
                        "pageurl": "https://example.test",
                    },
                },
                content_type="application/json",
                **self.headers,
            )
        return response.json()["task_id"]


@override_settings(CACHES=TEST_CACHES, CAPTCHA_TASK_TTL=1800)
class TaskRepositoryTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_task_expires_after_configured_ttl(self) -> None:
        repository = CaptchaTaskRepository(ttl=1)
        repository.create("expiring", "recaptcha_v2", {})

        time.sleep(1.05)

        with self.assertRaises(CaptchaTaskNotFoundError):
            repository.get("expiring")

    def test_update_preserves_original_expiration(self) -> None:
        repository = CaptchaTaskRepository(ttl=30)
        created = repository.create("ttl", "recaptcha_v2", {})

        updated = repository.set_processing("ttl")

        self.assertEqual(updated["expires_at"], created["expires_at"])


@override_settings(CACHES=TEST_CACHES, CAPTCHA_TASK_TTL=1800)
class ThreadQuotaTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.quota = ThreadQuotaService()

    def test_release_allows_new_reservation(self) -> None:
        self.quota.reserve(10, 1)
        with self.assertRaises(ThreadLimitExceeded):
            self.quota.reserve(10, 1)

        self.quota.release("task-10", 10)
        self.quota.reserve(10, 1)


@override_settings(CACHES=TEST_CACHES, CAPTCHA_TASK_TTL=1800)
class ProcessCaptchaTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.api_key = Key.objects.create(api_key="worker-key", max_threads=1)
        self.repository = CaptchaTaskRepository()
        self.repository.create(
            "task-1",
            "recaptcha_v2",
            {"googlekey": "site-key", "pageurl": "https://example.test"},
            api_key_id=self.api_key.pk,
        )

    @patch("apps.captchas.tasks.build_captchaai_client")
    def test_worker_transitions_through_processing_and_completes(
        self, build_client: Mock
    ) -> None:
        client = build_client.return_value

        def submit(*args, **kwargs):
            task = self.repository.get("task-1")
            self.assertEqual(task["status"], "processing")
            return "provider-123"

        client.submit.side_effect = submit
        client.wait_result.return_value = {"status": 1, "request": "token-abc"}
        client.extract_solution.return_value = {"solution": "token-abc"}

        process_captcha("task-1")

        task = self.repository.get("task-1")
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["provider_task_id"], "provider-123")
        self.assertEqual(task["result"], {"solution": "token-abc"})
        self.assertIsNone(task["error"])

    @patch("apps.captchas.tasks.build_captchaai_client")
    def test_worker_stores_structured_failure(self, build_client: Mock) -> None:
        client = build_client.return_value
        client.submit.side_effect = CaptchaAIUnsolvableError("ERROR_CAPTCHA_UNSOLVABLE")

        process_captcha("task-1")

        task = self.repository.get("task-1")
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["error"]["code"], "captchaai_unsolvable")
        self.assertEqual(task["error"]["message"], "ERROR_CAPTCHA_UNSOLVABLE")

    @patch("apps.captchas.tasks.build_captchaai_client")
    def test_completed_task_is_returned_by_api(self, build_client: Mock) -> None:
        client = build_client.return_value
        client.submit.return_value = "provider-123"
        client.wait_result.return_value = {"status": 1, "request": "token-abc"}
        client.extract_solution.return_value = {"solution": "token-abc"}
        process_captcha("task-1")

        response = Client().get(
            "/api/v1/tasks/task-1/",
            HTTP_X_API_KEY=self.api_key.api_key,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        self.assertEqual(response.json()["result"], {"solution": "token-abc"})


class CaptchaSolverTests(SimpleTestCase):
    def test_all_documented_types_build_valid_submissions(self) -> None:
        image = base64.b64encode(b"x" * 100).decode()
        cases = {
            "normal": ({"body": image}, "post"),
            "grid": (
                {
                    "body": image,
                    "grid_size": "3x3",
                    "img_type": "recaptcha",
                    "instructions": "bicycles",
                },
                "post",
            ),
            "recaptcha_v2": (
                {"googlekey": "key", "pageurl": "https://example.test"},
                "userrecaptcha",
            ),
            "recaptcha_v2_invisible": (
                {"googlekey": "key", "pageurl": "https://example.test"},
                "userrecaptcha",
            ),
            "recaptcha_v2_callback": (
                {"googlekey": "key", "pageurl": "https://example.test"},
                "userrecaptcha",
            ),
            "recaptcha_v2_enterprise": (
                {"googlekey": "key", "pageurl": "https://example.test"},
                "userrecaptcha",
            ),
            "recaptcha_v3": (
                {
                    "googlekey": "key",
                    "pageurl": "https://example.test",
                    "action": "login",
                },
                "userrecaptcha",
            ),
            "recaptcha_v3_enterprise": (
                {
                    "googlekey": "key",
                    "pageurl": "https://example.test",
                    "action": "login",
                },
                "userrecaptcha",
            ),
            "geetest_v3": (
                {
                    "gt": "gt",
                    "challenge": "challenge",
                    "pageurl": "https://example.test",
                },
                "geetest",
            ),
            "turnstile": (
                {"sitekey": "key", "pageurl": "https://example.test"},
                "turnstile",
            ),
            "cloudflare_challenge": (
                {"pageurl": "https://example.test"},
                "cloudflare_challenge",
            ),
            "bls": (
                {
                    "instructions": "664",
                    "images": ["data:image/png;base64,eA=="] * 9,
                },
                "bls",
            ),
            "captchafox": (
                {"sitekey": "key", "pageurl": "https://example.test"},
                "captchafox",
            ),
            "friendly_captcha": (
                {"sitekey": "key", "pageurl": "https://example.test"},
                "friendly_captcha",
            ),
            "lemin": (
                {"captcha_id": "captcha-id", "pageurl": "https://example.test"},
                "lemin",
            ),
        }

        self.assertEqual(set(cases), set(SOLVERS))
        for captcha_type, (data, expected_method) in cases.items():
            with self.subTest(captcha_type=captcha_type):
                submission = get_solver(captcha_type).build_submission(data)
                self.assertEqual(submission.payload["method"], expected_method)

    def test_solver_specific_flags_are_applied(self) -> None:
        common = {"googlekey": "key", "pageurl": "https://example.test"}

        invisible = get_solver("recaptcha_v2_invisible").build_submission(common)
        v2_enterprise = get_solver("recaptcha_v2_enterprise").build_submission(common)
        v3_enterprise = get_solver("recaptcha_v3_enterprise").build_submission(
            {**common, "action": "login"}
        )

        self.assertEqual(invisible.payload["invisible"], 1)
        self.assertEqual(v2_enterprise.payload["enterprise"], 1)
        self.assertEqual(v3_enterprise.payload["version"], "v3")
        self.assertEqual(v3_enterprise.payload["enterprise"], 1)

    def test_grid_and_geetest_results_are_parsed(self) -> None:
        grid = get_solver("grid").parse_result({"status": 1, "request": "[1, 3, 9]"})
        geetest = get_solver("geetest_v3").parse_result(
            {
                "status": 1,
                "request": ('{"challenge":"c","validate":"v","seccode":"s"}'),
            }
        )

        self.assertEqual(grid, {"solution": [1, 3, 9]})
        self.assertEqual(
            geetest,
            {
                "solution": {
                    "challenge": "c",
                    "validate": "v",
                    "seccode": "s",
                }
            },
        )

    @patch("apps.captchas.services.captchaai.client.urlopen")
    def test_image_submission_uses_multipart(self, urlopen: Mock) -> None:
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"status":1,"request":"provider-id"}'
        image = base64.b64encode(b"x" * 100).decode()
        submission = get_solver("normal").build_submission({"body": image})

        provider_id = CaptchaAIClient("api-key").submit(
            submission.payload,
            files=submission.files,
        )

        self.assertEqual(provider_id, "provider-id")
        request = urlopen.call_args.args[0]
        self.assertTrue(
            request.headers["Content-type"].startswith("multipart/form-data")
        )
        self.assertIn(b'name="file"; filename="captcha.png"', request.data)
