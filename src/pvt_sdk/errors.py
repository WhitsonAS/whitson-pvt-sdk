class SDKError(Exception):
    """Base error for all SDK errors."""


class NotFoundError(SDKError):
    """A requested resource was not found."""


class AuthError(SDKError):
    """Authentication failed."""


class ValidationError(SDKError):
    """Request validation failed."""


class APIError(SDKError):
    """The upstream API returned an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)
