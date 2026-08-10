class CaptchaAIError(Exception):
    code = "captchaai_error"


class CaptchaAIConfigurationError(CaptchaAIError):
    code = "captchaai_configuration_error"


class CaptchaAITaskNotReady(CaptchaAIError):
    code = "captchaai_task_not_ready"


class CaptchaAITemporaryError(CaptchaAIError):
    code = "captchaai_temporary_error"


class CaptchaAIUnsolvableError(CaptchaAIError):
    code = "captchaai_unsolvable"


class CaptchaAITimeoutError(CaptchaAIError):
    code = "captchaai_timeout"


class CaptchaAIHTTPError(CaptchaAIError):
    code = "captchaai_http_error"


class CaptchaAIInvalidResponseError(CaptchaAIError):
    code = "captchaai_invalid_response"


class CaptchaAIProviderError(CaptchaAIError):
    code = "captchaai_provider_error"

    def __init__(self, provider_code: str) -> None:
        self.provider_code = provider_code
        super().__init__(provider_code)
