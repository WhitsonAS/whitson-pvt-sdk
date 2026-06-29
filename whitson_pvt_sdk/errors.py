class SDKError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class HTTPStatusError(SDKError):
    """The upstream API returned an unsuccessful HTTP response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        response_body: object | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.response_body = response_body
        self.request_id = request_id
        super().__init__(message)


class NotFoundError(HTTPStatusError):
    """A requested resource was not found."""


class AuthError(HTTPStatusError):
    """Authentication failed."""


class ValidationError(HTTPStatusError):
    """Request validation failed."""


class APIError(HTTPStatusError):
    """The upstream API returned an error."""


class RateLimitError(HTTPStatusError):
    """The upstream API rejected the request due to rate limiting."""

    def __init__(
        self,
        message: str,
        status_code: int | None = 429,
        *,
        response_body: object | None = None,
        request_id: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            message,
            status_code=status_code,
            response_body=response_body,
            request_id=request_id,
        )


class CalculationError(SDKError):
    """A calculation endpoint returned a failed calculation result."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        sample_id: int | None = None,
        input_index: int | None = None,
        error: object | None = None,
    ) -> None:
        self.code = code
        self.sample_id = sample_id
        self.input_index = input_index
        self.error = error
        super().__init__(message)
