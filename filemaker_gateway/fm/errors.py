"""FileMaker Data API error types."""


class FMDataError(Exception):
    """Base exception for FileMaker Data API errors.

    Attributes:
        code: The FileMaker error code (e.g. 401, 404, 400).
        message: Human-readable error description.
    """

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[FMDataError {code}] {message}")


class FMAuthError(FMDataError):
    """Authentication failed (HTTP 401 / FM error 212)."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(401, message)


class FMNotFoundError(FMDataError):
    """Resource not found (HTTP 404 / FM error 101)."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(404, message)


class FMValidationError(FMDataError):
    """Field validation error (HTTP 400 / FM error 102)."""

    def __init__(self, message: str = "Validation failed") -> None:
        super().__init__(400, message)
