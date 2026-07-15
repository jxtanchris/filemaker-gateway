"""FileMaker Data API client module."""

from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.errors import FMAuthError, FMDataError, FMNotFoundError, FMValidationError

__all__ = [
    "FMDataClient",
    "FMDataError",
    "FMAuthError",
    "FMNotFoundError",
    "FMValidationError",
]
